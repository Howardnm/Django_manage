"""认证表单模块。定义登录、注册和密码重置的表单类。

导出: UserLoginForm, UserRegisterForm, PasswordResetForm, PasswordChangeForm。"""
from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth import get_user_model, authenticate
from django.conf import settings

User = get_user_model()


# 1. 登录表单
class UserLoginForm(AuthenticationForm):
    """登录表单。以工号作为账号，包含"记住我"复选框和 CAPTCHA 校验。"""
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "工号或密码错误",
    }
    employee_no = forms.CharField(
        label="工号",
        max_length=32,
        widget=forms.TextInput(attrs={"placeholder": "请输入工号", "autocomplete": "username"}),
        error_messages={"required": "工号或密码错误"},
    )
    remember_me = forms.BooleanField(label="在此设备上保持登录", required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))

    def __init__(self, request=None, *args, **kwargs):
        """移除继承的 username 字段，为所有非复选框字段添加 form-control CSS 类。"""
        self.request = request
        super().__init__(request, *args, **kwargs)
        # 彻底移除 AuthenticationForm 继承的 username 字段，仅保留工号登录
        self.fields.pop('username', None)
        for field in self.fields.values():
            if field.widget.attrs.get('class') != 'form-check-input':
                field.widget.attrs.update({'class': 'form-control'})

    def clean(self):
        """校验图形验证码，并用工号完成认证。Raises: ValidationError。Returns: cleaned_data。"""
        if self.request:
            captcha = self.request.POST.get('captcha', '')
            session_captcha = self.request.session.get('captcha_code', '')
            if not captcha:
                raise forms.ValidationError("请输入图形验证码")
            if not session_captcha or session_captcha.lower() != captcha.lower():
                raise forms.ValidationError("图形验证码错误")
        # 父类 AuthenticationForm.clean() 只读取 username，故此处自行调用 authenticate，
        # 参数直接传给 EmployeeNoBackend 的 employee_no 形参
        employee_no = self.cleaned_data.get('employee_no')
        password = self.cleaned_data.get('password')
        if employee_no and password:
            self.user_cache = authenticate(self.request, employee_no=employee_no, password=password)
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            else:
                self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data


# 2. 注册表单
class UserRegisterForm(UserCreationForm):
    """注册表单。包含邀请码、邮箱、密码和确认密码字段。"""
    invite_code = forms.CharField(label="邀请码", required=True, help_text="请输入管理员提供的邀请码")
    email = forms.EmailField(label="邮箱", required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('email',)

    def __init__(self, *args, **kwargs):
        """为所有字段添加 form-control CSS 类。"""
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})

    def clean_invite_code(self):
        """校验邀请码与 settings.REGISTER_INVITE_CODE 匹配。Raises: ValidationError。Returns: 清理后的邀请码。"""
        code = self.cleaned_data.get('invite_code')
        correct_code = getattr(settings, 'REGISTER_INVITE_CODE', None)
        if correct_code and code != correct_code:
            raise forms.ValidationError("邀请码错误，请联系管理员获取")
        return code

    def clean_email(self):
        """邮箱转小写并校验唯一性。Raises: ValidationError。Returns: 归一化后的邮箱。"""
        email = (self.cleaned_data.get('email') or '').strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("该邮箱已被注册")
        return email


# 4. 密码重置表单
class PasswordResetForm(forms.Form):
    """密码重置表单。包含邮箱、新密码和确认密码字段。"""
    email = forms.EmailField(label="邮箱地址", required=True)
    new_password = forms.CharField(label="新密码", widget=forms.PasswordInput, required=True)
    confirm_password = forms.CharField(label="确认密码", widget=forms.PasswordInput, required=True)

    def __init__(self, *args, **kwargs):
        """为所有字段添加 form-control CSS 类。"""
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})

    def clean(self):
        """校验两次输入的密码一致。Raises: ValidationError。Returns: cleaned_data。"""
        cleaned_data = super().clean()
        new_password = cleaned_data.get("new_password")
        confirm_password = cleaned_data.get("confirm_password")
        if new_password and confirm_password and new_password != confirm_password:
            raise forms.ValidationError("两次输入的密码不一致")
        return cleaned_data


# 5. 修改密码表单（已登录用户）
class PasswordChangeForm(forms.Form):
    """修改密码表单。旧密码 + 新密码 + 确认密码 + 图形验证码。

    构造时需通过 kwargs 传入 user（用于校验旧密码）与 request（用于读取 session 中的图形验证码）。
    """
    old_password = forms.CharField(label="旧密码", widget=forms.PasswordInput, required=True)
    new_password = forms.CharField(label="新密码", widget=forms.PasswordInput, required=True)
    confirm_password = forms.CharField(label="确认新密码", widget=forms.PasswordInput, required=True)
    captcha = forms.CharField(label="图形验证码", required=True)

    def __init__(self, *args, **kwargs):
        """接收 user/request，并为所有字段注入 form-control CSS 类。"""
        self.user = kwargs.pop('user', None)
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})

    def clean_old_password(self):
        """校验旧密码是否正确。Raises: ValidationError。Returns: old_password。"""
        old_password = self.cleaned_data.get("old_password")
        if old_password and self.user and not self.user.check_password(old_password):
            raise forms.ValidationError("旧密码错误")
        return old_password

    def clean_captcha(self):
        """校验图形验证码（与 session 中 captcha_code 比对，大小写不敏感）。Raises: ValidationError。Returns: captcha。"""
        captcha = self.cleaned_data.get("captcha")
        session_captcha = self.request.session.get('captcha_code', '') if self.request else ''
        if not captcha:
            raise forms.ValidationError("请输入图形验证码")
        if not session_captcha or session_captcha.lower() != captcha.lower():
            raise forms.ValidationError("图形验证码错误")
        return captcha

    def clean(self):
        """校验新密码与旧密码不同、两次输入的新密码一致。Raises: ValidationError。Returns: cleaned_data。"""
        cleaned_data = super().clean()
        old_password = cleaned_data.get("old_password")
        new_password = cleaned_data.get("new_password")
        confirm_password = cleaned_data.get("confirm_password")
        if new_password and confirm_password and new_password != confirm_password:
            raise forms.ValidationError("两次输入的新密码不一致")
        if old_password and new_password and old_password == new_password:
            raise forms.ValidationError("新密码不能与旧密码相同")
        return cleaned_data
