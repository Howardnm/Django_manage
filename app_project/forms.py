from django import forms
from .models import Project, ProjectNode

class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name', 'description']
        # 样式美化，适配 Tabler
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '输入项目名称'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 13}),
        }

class ProjectNodeUpdateForm(forms.ModelForm):
    class Meta:
        model = ProjectNode
        fields = ['status', 'remark']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 12, 'placeholder': '填写备注信息...'}),
        }