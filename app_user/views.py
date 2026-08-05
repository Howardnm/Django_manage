"""认证视图模块。处理登录、注册、个人资料、密码重置、验证码生成和浏览器验证。

导出: CustomLoginView, RegisterView, ProfileView, PasswordResetView, ChangePasswordView, captcha_view, verify_browser, send_email_code。"""
import json
from django.shortcuts import render
from django.contrib.auth.views import LoginView
from django.views.decorators.http import require_GET
from django.views.generic import CreateView, TemplateView, FormView
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.conf import settings
from django.core.cache import cache
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .forms import UserLoginForm, UserRegisterForm, PasswordResetForm, PasswordChangeForm
from .services.identity_service import IdentityService
from .utils import generate_captcha, send_verification_email, send_register_success_email
from app_panel.mixins import HomeAccessMixin

User = get_user_model()

class CustomLoginView(LoginView):
    """登录视图。校验用户为 INTERNAL_STAFF 角色，处理"记住我"和锁定消息。"""
    template_name = 'apps/app_user/login.html'
    authentication_form = UserLoginForm
    redirect_authenticated_user = True  # 如果已登录，直接跳走

    def get_context_data(self, **kwargs):
        """向模板注入锁定提示。Returns: 上下文字典。"""
        context = super().get_context_data(**kwargs)
        # 检查是否被锁定 (通过 URL 参数)
        if self.request.GET.get('locked'):
            # 计算锁定时间（分钟）
            cooloff_time = getattr(settings, 'AXES_COOLOFF_TIME', 1)
            cooloff_minutes = int(cooloff_time * 60)
            context['locked_message'] = f"登录失败次数过多，账号已被锁定 {cooloff_minutes} 分钟，请稍后再试。"
        return context

    def form_valid(self, form):
        """验证用户身份后执行 INTERNAL_STAFF 角色检查，处理 session 过期策略。Args: form: UserLoginForm。Returns: HttpResponse。"""
        # --- 核心拦截：只允许内部成员用户登录此管理系统 ---
        user = form.get_user()
        # 外部角色 (CUSTOMER, OEM) 禁止登录此后台管理系统
        # 他们应该前往电子手册系统 (app_catalog)
        allowed_roles = IdentityService.get_internal_role_codes()
        
        if not user.is_superuser and user.user_type not in allowed_roles:
            messages.error(self.request, "您的账号身份不属于内部成员，无法访问管理系统。")
            return self.form_invalid(form)

        # 处理 "保持登录" 逻辑
        remember_me = form.cleaned_data.get('remember_me')
        if not remember_me:
            # 如果未勾选，设置 session 在浏览器关闭时失效
            self.request.session.set_expiry(0)
        else:
            # 如果勾选，使用 settings.SESSION_COOKIE_AGE (默认10小时)
            self.request.session.set_expiry(settings.SESSION_COOKIE_AGE)

        return super().form_valid(form)


# 生成图形验证码视图
@require_GET
def captcha_view(request):
    """生成 CAPTCHA 图片并将验证码存入 session。Returns: image/png 类型的 HttpResponse。"""
    image_data, code = generate_captcha()
    request.session['captcha_code'] = code
    return HttpResponse(image_data, content_type="image/png")

# 获取客户端IP
def get_client_ip(request):
    """从请求中提取客户端 IP，优先取 X-Forwarded-For。Args: request: HttpRequest。Returns: IP 地址字符串。"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

# 浏览器验证接口 (带后端轨迹和Nonce验证)
def verify_browser(request):
    """浏览器滑动验证端点。校验轨迹点数量、耗时、Y 轴变化和 X 轴单调性。Returns: JsonResponse。"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': '请求方法错误'}, status=405)

    try:
        data = json.loads(request.body)
        trajectory = data.get('trajectory', [])
        received_nonce = data.get('nonce')
        session_nonce = request.session.get('shield_nonce')

        # 1. Nonce (一次性令牌) 验证
        if not received_nonce or not session_nonce or received_nonce != session_nonce:
            return JsonResponse({'status': 'fail', 'message': '验证令牌无效或已过期，请刷新页面'}, status=403)

        # 2. 轨迹点数量验证
        if len(trajectory) < 10:
            return JsonResponse({'status': 'fail', 'message': '验证异常，请刷新页面重试'}, status=400)

        # 3. 滑动时间验证
        start_time = trajectory[0]['t']
        end_time = trajectory[-1]['t']
        duration = end_time - start_time
        if duration < 100:  # 必须超过100毫秒
            return JsonResponse({'status': 'fail', 'message': '滑动过快，请刷新页面重试'}, status=400)

        # 4. Y轴变化验证
        y_coords = {point['y'] for point in trajectory}
        if len(y_coords) < 3: # 至少有3个不同的Y坐标，允许轻微的直线抖动
            return JsonResponse({'status': 'fail', 'message': '验证异常，请刷新页面重试'}, status=400)

        # 5. X轴非线性验证 (简易版)
        # 检查x坐标是否是单调递增的，防止来回拖动
        x_coords = [point['x'] for point in trajectory]
        for i in range(len(x_coords) - 1):
            if x_coords[i] > x_coords[i+1]:
                 return JsonResponse({'status': 'fail', 'message': '验证异常，请刷新页面重试'}, status=400)

        # --- 所有验证通过 ---

        # 关键步骤：立即销毁令牌，防止重放
        if 'shield_nonce' in request.session:
            del request.session['shield_nonce']

        request.session['access_granted'] = True
        return JsonResponse({'status': 'success'})

    except (json.JSONDecodeError, KeyError, IndexError):
        return JsonResponse({'status': 'error', 'message': '请求数据格式错误'}, status=400)


# 发送邮箱验证码视图
def send_email_code(request):
    """发送邮箱验证码（注册/密码重置）。含图形验证码校验和频率限制。Returns: JsonResponse。"""
    # 检查是否允许注册 (是否有邀请码)
    # 注意：密码重置也可能用到这个接口，如果密码重置不需要邀请码限制，这里需要区分场景
    # 我们可以通过 request.GET.get('type') 来区分是注册还是重置

    action_type = request.GET.get('type', 'register')

    if action_type == 'register':
        if not getattr(settings, 'REGISTER_INVITE_CODE', None):
            return JsonResponse({'status': 'error', 'msg': '系统暂未开放注册'})

    email = request.GET.get('email')
    captcha = request.GET.get('captcha')

    # 1. 校验图形验证码
    if not captcha:
        return JsonResponse({'status': 'error', 'msg': '请输入图形验证码'})

    if request.session.get('captcha_code', '').lower() != captcha.lower():
        return JsonResponse({'status': 'error', 'msg': '图形验证码错误'})

    # 2. 校验邮箱
    if not email:
        return JsonResponse({'status': 'error', 'msg': '请输入邮箱'})

    # 3. 频率限制 (Rate Limiting)
    # 限制规则：同一个IP或同一个邮箱，60秒内只能发送一次
    client_ip = get_client_ip(request)
    cache_key_ip = f"email_code_limit_ip_{client_ip}"
    cache_key_email = f"email_code_limit_email_{email}"

    # 使用原子操作 cache.add() 避免竞态条件：
    # cache.add() 仅在 key 不存在时设置并返回 True，key 已存在时返回 False
    if not cache.add(cache_key_ip, True, 60):
        return JsonResponse({'status': 'error', 'msg': '发送过于频繁，请稍后再试'})
    if not cache.add(cache_key_email, True, 60):
        # 回滚刚才设置的 IP 缓存，避免 IP 被限但 email 未被限的不一致状态
        cache.delete(cache_key_ip)
        return JsonResponse({'status': 'error', 'msg': '发送过于频繁，请稍后再试'})

    user_exists = User.objects.filter(email=email).exists()

    if action_type == 'register':
        # 注册时，邮箱不能存在
        if user_exists:
            return JsonResponse({'status': 'error', 'msg': '该邮箱已被注册'})
    elif action_type == 'reset_password':
        # 密码重置不暴露邮箱是否已注册，统一返回成功提示
        # 后续在 PasswordResetView.form_valid() 中再检查邮箱是否存在
        if not user_exists:
            return JsonResponse({'status': 'success', 'msg': '如果该邮箱已注册，验证码已发送'})

    # 4. 发送验证码
    code, success, error_msg = send_verification_email(email)

    if not success:
        return JsonResponse({'status': 'error', 'msg': f'邮件发送失败: {error_msg}'})

    # 频率限制已通过前面的 cache.add() 原子操作完成，无需再次 set

    # 使用不同的 session key 区分注册和重置
    if action_type == 'register':
        request.session['register_email_code'] = code
        request.session['register_email'] = email
    else:
        request.session['reset_email_code'] = code
        request.session['reset_email'] = email

    return JsonResponse({'status': 'success', 'msg': '验证码已发送'})


# 2. 注册
class RegisterView(CreateView):
    """用户注册视图。需有效的邀请码和邮箱验证码。"""
    template_name = 'apps/app_user/register.html'
    form_class = UserRegisterForm
    success_url = reverse_lazy('register_success')  # 注册成功跳到成功页

    def dispatch(self, request, *args, **kwargs):
        # 如果未配置邀请码，禁止访问注册页面
        if not getattr(settings, 'REGISTER_INVITE_CODE', None):
            return render(request, 'apps/app_user/register_closed.html')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        """校验邮箱验证码，创建用户，清理 session 并发送欢迎邮件。Args: form: UserRegisterForm。Returns: HttpResponse。"""
        # 校验邮箱验证码
        email = form.cleaned_data.get('email')
        email_code = self.request.POST.get('email_code')

        if not email_code:
            form.add_error('email', "请输入邮箱验证码")
            return self.form_invalid(form)

        if self.request.session.get('register_email_code') != email_code:
            form.add_error('email', "邮箱验证码错误")
            return self.form_invalid(form)

        if self.request.session.get('register_email') != email:
            form.add_error('email', "验证邮箱与提交邮箱不一致")
            return self.form_invalid(form)

        # 保存用户
        response = super().form_valid(form)

        # 清理 session 中的注册验证信息
        if 'register_email_code' in self.request.session:
            del self.request.session['register_email_code']
        if 'register_email' in self.request.session:
            del self.request.session['register_email']

        # 发送注册成功邮件
        # self.object 是刚刚创建的 User 对象
        send_register_success_email(self.object, self.request)

        return response


# 注册成功页面
class RegisterSuccessView(TemplateView):
    """注册成功提示页。"""
    template_name = 'apps/app_user/register_success.html'


# 3. 个人中心 (只读展示)
class ProfileView(HomeAccessMixin, TemplateView):
    """个人资料只读展示视图。不提供编辑表单，基础信息由管理员维护。

    L1/L2: HomeAccessMixin (module_code='home') 从 DB 读取 — 与首页权限一致。
    L3: 显式声明 [] — 纯只读展示页，无适用 L3 权限码。
    """
    permission_required = []  # 纯只读展示页，零数据查询
    template_name = 'apps/app_user/profile.html'

# 4. 密码重置视图
class PasswordResetView(FormView):
    """密码重置视图。通过邮箱验证码 + 密码强度校验完成重置。"""
    template_name = 'apps/app_user/password_reset.html'
    form_class = PasswordResetForm
    success_url = reverse_lazy('login')

    def form_valid(self, form):
        """校验验证码，验证密码强度，更新密码，清理 session。Args: form: PasswordResetForm。Returns: HttpResponse。Raises: ValidationError: 密码不符合 AUTH_PASSWORD_VALIDATORS 策略。"""
        email = form.cleaned_data.get('email')
        new_password = form.cleaned_data.get('new_password')
        email_code = self.request.POST.get('email_code')

        # 校验验证码
        if not email_code:
            form.add_error('email', "请输入邮箱验证码")
            return self.form_invalid(form)

        if self.request.session.get('reset_email_code') != email_code:
            form.add_error('email', "邮箱验证码错误")
            return self.form_invalid(form)

        if self.request.session.get('reset_email') != email:
            form.add_error('email', "验证邮箱与提交邮箱不一致")
            return self.form_invalid(form)

        # 修改密码
        try:
            user = User.objects.get(email=email)
            validate_password(new_password, user)
            user.set_password(new_password)
            user.save()
            messages.success(self.request, "密码重置成功，请使用新密码登录")

            if 'reset_email_code' in self.request.session:
                del self.request.session['reset_email_code']
            if 'reset_email' in self.request.session:
                del self.request.session['reset_email']

        except User.DoesNotExist:
            form.add_error('email', "该邮箱未注册用户")
            return self.form_invalid(form)
        except ValidationError as e:
            for msg in e.messages:
                form.add_error('new_password', msg)
            return self.form_invalid(form)

        return super().form_valid(form)


# 5. 修改密码视图（已登录用户）
class ChangePasswordView(HomeAccessMixin, FormView):
    """修改密码视图。已登录用户通过旧密码 + 图形验证码修改密码。

    L1/L2: 继承 HomeAccessMixin (module_code='home')，与 ProfileView 权限完全一致，
           未登录/无权限用户在前置准入即被拦截，防止穿透访问。
    L3: 显式声明 [] — 纯表单页，无数据查询。
    """
    permission_required = []  # 纯表单页，无适用 L3 权限码
    template_name = 'apps/app_user/change_password.html'
    form_class = PasswordChangeForm
    success_url = reverse_lazy('user_profile')

    def get_form_kwargs(self):
        """将当前用户与请求注入表单，供旧密码校验与图形验证码校验使用。"""
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        """密码强度校验 + 更新密码。改密后保持登录并跳回个人中心。"""
        user = self.request.user
        new_password = form.cleaned_data['new_password']

        try:
            validate_password(new_password, user)
        except ValidationError as e:
            for msg in e.messages:
                form.add_error('new_password', msg)
            return self.form_invalid(form)

        user.set_password(new_password)
        user.save()
        # 更新会话认证哈希，保持本次登录会话有效，避免改密后被自动登出
        update_session_auth_hash(self.request, user)
        messages.success(self.request, "密码修改成功")

        return super().form_valid(form)
