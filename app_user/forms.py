"""认证表单模块。定义登录、注册和密码重置的表单类。

导出: UserLoginForm, UserRegisterForm, PasswordResetForm。"""
from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth import get_user_model, authenticate
from django.conf import settings

User = get_user_model()


class EmailSuffixWidget(forms.Widget):
    """邮箱前缀 + 后缀选择器。

    后缀来自 settings.EMAIL_DOMAINS（默认 sunwill.com.cn），并提供一个
    "自定义域名"选项以便输入其他域名。提交时组合为 前缀@后缀。

    采用与内置 widget 相同的「内联渲染」方式（render() 直接拼 HTML，不使用
    模板文件），因此不依赖表单渲染器，可放在公共 templates/ 或任何位置。
    """
    def __init__(self, domains, attrs=None):
        self.domains = list(domains or [])
        super().__init__(attrs)

    def value_from_datadict(self, data, files, name):
        """从 POST 数据组装完整邮箱：前缀 + 选择的后缀（或自定义域名）。"""
        prefix = (data.get(f'{name}_prefix') or '').strip()
        domain = (data.get(f'{name}_domain') or '').strip()
        custom = (data.get(f'{name}_custom') or '').strip()
        if domain == '__custom__':
            domain = custom
        if prefix and domain:
            return f'{prefix}@{domain}'
        return ''

    def render(self, name, value, attrs=None, renderer=None):
        """内联渲染前缀输入框 + 后缀下拉 + 自定义域名输入框。"""
        from django.utils.html import format_html, mark_safe

        prefix, domain = '', ''
        if value:
            prefix, _, domain = value.partition('@')
        custom_mode = bool(domain) and domain not in self.domains

        options = ''.join(
            f'<option value="{d}"{" selected" if domain == d else ""}>@{d}</option>'
            for d in self.domains
        )
        options += f'<option value="__custom__"{" selected" if custom_mode else ""}>自定义域名</option>'
        custom_class = '' if custom_mode else ' d-none'
        custom_value = domain if custom_mode else ''

        html = format_html(
            '<div class="input-group">'
            '<input type="text" name="{}_prefix" id="{}_prefix" class="form-control" '
            'placeholder="邮箱前缀" value="{}" autocomplete="username" required>'
            '<select name="{}_domain" id="{}_domain" class="form-select" '
            'style="max-width: 220px;">{}</select>'
            '<input type="text" name="{}_custom" id="{}_custom" class="form-control{}" '
            'placeholder="域名" value="{}" autocomplete="username">'
            '</div>',
            name, name, prefix, name, name, mark_safe(options),
            name, name, custom_class, custom_value,
        )
        # 切换"自定义域名"选项时显示/隐藏域名输入框（name 为表单字段名，非用户输入）
        script = mark_safe(
            '<script>'
            '(function(){'
            f'var s=document.getElementById("{name}_domain");'
            f'var c=document.getElementById("{name}_custom");'
            'if(!s||!c)return;'
            'function t(){'
            'if(s.value==="__custom__"){c.classList.remove("d-none");c.focus();}'
            'else{c.classList.add("d-none");}'
            '}'
            's.addEventListener("change",t);t();'
            '})();'
            '</script>'
        )
        return html + script


# 1. 登录表单
class UserLoginForm(AuthenticationForm):
    """登录表单。以邮箱作为账号，包含"记住我"复选框和 CAPTCHA 校验。"""
    email = forms.EmailField(
        label="邮箱",
        widget=EmailSuffixWidget(domains=settings.EMAIL_DOMAINS),
    )
    remember_me = forms.BooleanField(label="在此设备上保持登录", required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))

    def __init__(self, request=None, *args, **kwargs):
        """移除继承的 username 字段，为所有非复选框字段添加 form-control CSS 类。"""
        self.request = request
        super().__init__(request, *args, **kwargs)
        # 彻底移除 AuthenticationForm 继承的 username 字段，仅保留邮箱登录
        self.fields.pop('username', None)
        for field in self.fields.values():
            if field.widget.attrs.get('class') != 'form-check-input':
                field.widget.attrs.update({'class': 'form-control'})

    def clean(self):
        """校验图形验证码，并用邮箱完成认证。Raises: ValidationError。Returns: cleaned_data。"""
        if self.request:
            captcha = self.request.POST.get('captcha', '')
            session_captcha = self.request.session.get('captcha_code', '')
            if not captcha:
                raise forms.ValidationError("请输入图形验证码")
            if not session_captcha or session_captcha.lower() != captcha.lower():
                raise forms.ValidationError("图形验证码错误")
        # 邮箱认证（字段名已改为 email，父类 AuthenticationForm.clean() 只读取 username，
        # 故此处自行调用 authenticate，参数直接传给 EmailBackend 的 email 形参）
        email = self.cleaned_data.get('email')
        password = self.cleaned_data.get('password')
        if email is not None and password:
            self.user_cache = authenticate(self.request, email=email, password=password)
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
