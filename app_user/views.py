# apps/app_user/views.py
import json
import uuid
from django.shortcuts import render, redirect
from django.contrib.auth.views import LoginView, LogoutView
from django.views.generic import CreateView, View, TemplateView, FormView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.models import User
from django.conf import settings
from django.core.cache import cache
from .forms import UserLoginForm, UserRegisterForm, UserUpdateForm, ProfileUpdateForm, PasswordResetForm
from .utils import generate_captcha, send_verification_email, send_register_success_email


# 1. 登录 (直接继承内置视图)
class CustomLoginView(LoginView):
    template_name = 'apps/app_user/login.html'
    authentication_form = UserLoginForm
    redirect_authenticated_user = True  # 如果已登录，直接跳走

    # 验证码校验逻辑已移至 UserLoginForm.clean 方法中
    # 这里不需要再重写 form_valid 进行校验，因为 form.is_valid() 会调用 clean 方法
    # 如果 clean 方法抛出 ValidationError，form_valid 就不会被执行，而是执行 form_invalid

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 检查是否被锁定 (通过 URL 参数)
        if self.request.GET.get('locked'):
            # 计算锁定时间（分钟）
            cooloff_time = getattr(settings, 'AXES_COOLOFF_TIME', 1)
            cooloff_minutes = int(cooloff_time * 60)
            context['locked_message'] = f"登录失败次数过多，账号已被锁定 {cooloff_minutes} 分钟，请稍后再试。"
        return context

    def form_valid(self, form):
        # 处理 "保持登录" 逻辑
        remember_me = form.cleaned_data.get('remember_me')
        if not remember_me:
            # 如果未勾选，设置 session 在浏览器关闭时失效
            self.request.session.set_expiry(0)
        else:
            # 如果勾选，使用 settings.SESSION_COOKIE_AGE (默认10小时)
            self.request.session.set_expiry(settings.SESSION_COOKIE_AGE)
            
        return super().form_valid(form)

    def form_invalid(self, form):
        # 检查是否被 axes 锁定
        response = super().form_invalid(form)
        return response


# 生成图形验证码视图
def captcha_view(request):
    image_data, code = generate_captcha()
    request.session['captcha_code'] = code
    return HttpResponse(image_data, content_type="image/png")

# 获取客户端IP
def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

# 浏览器验证接口 (带后端轨迹和Nonce验证)
def verify_browser(request):
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
        if len(trajectory) < 20:
            return JsonResponse({'status': 'fail', 'message': '验证异常，请刷新页面重试'}, status=400)

        # 3. 滑动时间验证
        start_time = trajectory[0]['t']
        end_time = trajectory[-1]['t']
        duration = end_time - start_time
        if duration < 250:  # 必须超过100毫秒
            return JsonResponse({'status': 'fail', 'message': '滑动过快，请刷新页面重试'}, status=400)

        # 4. Y轴变化验证
        y_coords = {point['y'] for point in trajectory}
        if len(y_coords) < 5: # 至少有3个不同的Y坐标，允许轻微的直线抖动
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
    
    if cache.get(cache_key_ip) or cache.get(cache_key_email):
        return JsonResponse({'status': 'error', 'msg': '发送过于频繁，请稍后再试'})

    user_exists = User.objects.filter(email=email).exists()

    if action_type == 'register':
        # 注册时，邮箱不能存在
        if user_exists:
            return JsonResponse({'status': 'error', 'msg': '该邮箱已被注册'})
    elif action_type == 'reset_password':
        # 重置密码时，邮箱必须存在
        if not user_exists:
            return JsonResponse({'status': 'error', 'msg': '该邮箱未注册'})

    # 4. 发送验证码
    code, success, error_msg = send_verification_email(email)
    
    if not success:
        return JsonResponse({'status': 'error', 'msg': f'邮件发送失败: {error_msg}'})
    
    # 设置缓存，限制频率 (60秒)
    cache.set(cache_key_ip, True, 60)
    cache.set(cache_key_email, True, 60)
    
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
    template_name = 'apps/app_user/register.html'
    form_class = UserRegisterForm
    success_url = reverse_lazy('register_success')  # 注册成功跳到成功页

    def dispatch(self, request, *args, **kwargs):
        # 如果未配置邀请码，禁止访问注册页面
        if not getattr(settings, 'REGISTER_INVITE_CODE', None):
            return render(request, 'apps/app_user/register_closed.html')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
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
        
        # 发送注册成功邮件
        # self.object 是刚刚创建的 User 对象
        send_register_success_email(self.object, self.request)
        
        return response


# 注册成功页面
class RegisterSuccessView(TemplateView):
    template_name = 'apps/app_user/register_success.html'


# 3. 个人中心 (查看 + 修改)
class ProfileView(LoginRequiredMixin, View):
    template_name = 'apps/app_user/profile.html'

    def get(self, request):
        user_form = UserUpdateForm(instance=request.user)
        profile_form = ProfileUpdateForm(instance=request.user.profile)

        context = {
            'user_form': user_form,
            'profile_form': profile_form
        }
        return render(request, self.template_name, context)

    def post(self, request):
        user_form = UserUpdateForm(request.POST, instance=request.user)
        profile_form = ProfileUpdateForm(request.POST, instance=request.user.profile)

        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, "个人资料已更新！")
            return redirect('user_profile')

        context = {
            'user_form': user_form,
            'profile_form': profile_form
        }
        return render(request, self.template_name, context)

# 4. 密码重置视图
class PasswordResetView(FormView):
    template_name = 'apps/app_user/password_reset.html'
    form_class = PasswordResetForm
    success_url = reverse_lazy('login')

    def form_valid(self, form):
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
            user.set_password(new_password)
            user.save()
            messages.success(self.request, "密码重置成功，请使用新密码登录")
            
            # 清除 session
            del self.request.session['reset_email_code']
            del self.request.session['reset_email']
            
        except User.DoesNotExist:
            form.add_error('email', "该邮箱未注册用户")
            return self.form_invalid(form)

        return super().form_valid(form)