from django import forms
from .models import Project, ProjectNode
from django.contrib.auth.models import User
from common_utils.filters import TablerFormMixin  # 从 common_utils 导入通用的 TablerFormMixin


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
