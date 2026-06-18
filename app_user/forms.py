"""认证表单模块。定义登录、注册、个人资料编辑和密码重置的表单类。

导出: UserLoginForm, UserRegisterForm, UserUpdateForm, PasswordResetForm。"""
from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth import get_user_model
from django.conf import settings

User = get_user_model()

# 1. 登录表单
class UserLoginForm(AuthenticationForm):
    """登录表单。包含"记住我"复选框和 CAPTCHA 校验。"""
    remember_me = forms.BooleanField(label="在此设备上保持登录", required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))

    def __init__(self, request=None, *args, **kwargs):
        """为所有非复选框字段添加 form-control CSS 类。"""
        self.request = request
        super().__init__(request, *args, **kwargs)
        for field in self.fields.values():
            if field.widget.attrs.get('class') != 'form-check-input':
                field.widget.attrs.update({'class': 'form-control'})

    def clean(self):
        """校验图形验证码与 session 中的一致。Raises: ValidationError。Returns: cleaned_data。"""
        if self.request:
            captcha = self.request.POST.get('captcha', '')
            session_captcha = self.request.session.get('captcha_code', '')
            if not captcha:
                raise forms.ValidationError("请输入图形验证码")
            if not session_captcha or session_captcha.lower() != captcha.lower():
                raise forms.ValidationError("图形验证码错误")
        return super().clean()


# 2. 注册表单
class UserRegisterForm(UserCreationForm):
    """注册表单。包含邀请码、邮箱、密码和确认密码字段。"""
    invite_code = forms.CharField(label="邀请码", required=True, help_text="请输入管理员提供的邀请码")

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


# 3. 个人资料修改表单
class UserUpdateForm(forms.ModelForm):
    """个人资料编辑表单。扩展 User 模型字段。"""
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'email', 
            'phone', 'job_title', 'address', 'description',
            'associated_customer', 'associated_oem' # 增加公司归属关联
        ]
        widgets = {
            'associated_customer': forms.Select(attrs={'class': 'form-select'}),
            'associated_oem': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        """为没有 CSS 类的字段添加 form-control。"""
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not field.widget.attrs.get('class'):
                field.widget.attrs.update({'class': 'form-control'})


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
