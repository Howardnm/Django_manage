from django import forms
from .models import Project, ProjectNode
from django.contrib.auth.models import User
from common_utils.filters import TablerFormMixin # 从 common_utils 导入通用的 TablerFormMixin


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


class ProjectForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': '请输入项目名称'}),
            'description': forms.Textarea(attrs={'rows': 5, 'placeholder': '请输入项目背景、目标等详细描述...'}),
        }


# 确保 ProjectNodeUpdateForm 也继承 TablerFormMixin
class ProjectNodeUpdateForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ProjectNode
        fields = ['status', 'remark']
        widgets = {
            # status 字段会通过 TablerFormMixin 自动获得 form-select 样式
            'status': forms.Select(), 
            'remark': forms.Textarea(attrs={'rows': 12, 'placeholder': '填写备注信息...'}),
        }
