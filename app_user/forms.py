# apps/app_user/forms.py
from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, SetPasswordForm
from django.contrib.auth.models import User
from django.conf import settings
from .models import UserProfile


# 1. 登录表单
class UserLoginForm(AuthenticationForm):
    remember_me = forms.BooleanField(label="在此设备上保持登录", required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))

    def __init__(self, request=None, *args, **kwargs):
        # 接收 request 参数，以便在 clean 方法中访问 session
        self.request = request
        super().__init__(request, *args, **kwargs)
        for field in self.fields.values():
            if field.widget.attrs.get('class') != 'form-check-input':
                field.widget.attrs.update({'class': 'form-control'})

    def clean(self):
        # 1. 先校验验证码
        if self.request:
            captcha = self.request.POST.get('captcha', '')
            session_captcha = self.request.session.get('captcha_code', '')
            
            if not captcha:
                raise forms.ValidationError("请输入图形验证码")
            
            if not session_captcha or session_captcha.lower() != captcha.lower():
                raise forms.ValidationError("图形验证码错误")

        # 2. 再调用父类的 clean 方法校验用户名和密码
        # 如果验证码错误，上面的 raise 会中断执行，从而跳过账号密码校验
        return super().clean()


# 2. 注册表单
class UserRegisterForm(UserCreationForm):
    invite_code = forms.CharField(label="邀请码", required=True, help_text="请输入管理员提供的邀请码")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('email',)  # 注册时多填个邮箱

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})

    def clean_invite_code(self):
        code = self.cleaned_data.get('invite_code')
        correct_code = getattr(settings, 'REGISTER_INVITE_CODE', None)
        if correct_code and code != correct_code:
            raise forms.ValidationError("邀请码错误，请联系管理员获取")
        return code


# 3. 个人资料修改表单 (User部分)
class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']  # 允许改这几项

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})


# 4. 个人资料修改表单 (Profile部分)
class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['department', 'phone']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})

# 5. 密码重置表单
class PasswordResetForm(forms.Form):
    email = forms.EmailField(label="邮箱地址", required=True)
    new_password = forms.CharField(label="新密码", widget=forms.PasswordInput, required=True)
    confirm_password = forms.CharField(label="确认密码", widget=forms.PasswordInput, required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get("new_password")
        confirm_password = cleaned_data.get("confirm_password")

        if new_password and confirm_password and new_password != confirm_password:
            raise forms.ValidationError("两次输入的密码不一致")
        return cleaned_data