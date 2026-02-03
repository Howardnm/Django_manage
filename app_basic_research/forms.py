from django import forms
from .models import ResearchProject, ResearchProjectNode, ResearchProjectFile
from common_utils.filters import TablerFormMixin # 从 common_utils 导入通用的 TablerFormMixin


class ResearchProjectForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ResearchProject
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': '请输入预研项目名称'}),
            'description': forms.Textarea(attrs={'rows': 5, 'placeholder': '请输入项目背景、目标等详细描述...'}),
        }


# 确保 ResearchProjectNodeUpdateForm 也继承 TablerFormMixin
class ResearchProjectNodeUpdateForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ResearchProjectNode
        fields = ['status', 'remark']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 12, 'placeholder': '填写备注信息...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 【修复】如果节点状态是 FAILED，则禁止修改状态，只允许修改备注
        if self.instance and self.instance.status == 'FAILED':
            self.fields['status'].disabled = True


class ResearchProjectFileForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ResearchProjectFile
        fields = ['file', 'name', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': '文件描述...'}),
        }
