from django import forms
from .models import Project, ProjectNode
from django.contrib.auth.models import User


class RegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, label='密码')
    confirm_password = forms.CharField(widget=forms.PasswordInput, label='确认密码')

    class Meta:
        model = User
        fields = ['username', 'password', 'confirm_password']

    # 自定义表单级别的验证方法，名称必须是clean
    def clean(self):
        cleaned_data = super().clean()  # 调用父类的clean方法，获取清理后的数据
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password != confirm_password:
            raise forms.ValidationError("密码和确认密码不匹配。")
        return cleaned_data


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name', 'description']
        # 样式美化，适配 Tabler
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '输入项目名称'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
        }


class ProjectNodeUpdateForm(forms.ModelForm):
    class Meta:
        model = ProjectNode
        fields = ['status', 'remark']
        widgets = {
            'status_choices': forms.Select(attrs={'class': 'form-select'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 12, 'placeholder': '填写备注信息...'}),
        }
