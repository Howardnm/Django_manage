from django import forms
from .models import ResearchProject, ResearchProjectNode, ResearchProjectFile


# ========================================================
# 1. 定义 Tabler 样式混入类
# ========================================================
class TablerFormMixin:
    """
    混入类：自动给字段添加 Tabler/Bootstrap 样式类
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field_name, field in self.fields.items():
            attrs = field.widget.attrs
            existing_class = attrs.get('class', '')

            # 下拉框
            if isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                if 'form-select' not in existing_class:
                    existing_class += ' form-select'
                if 'form-select-search' not in existing_class:
                    existing_class += ' form-select-search'
                attrs['class'] = existing_class.strip()

            # 复选框
            elif isinstance(field.widget, forms.CheckboxInput):
                if 'form-check-input' not in existing_class:
                    attrs['class'] = f"{existing_class} form-check-input".strip()

            # 普通输入框
            else:
                if not isinstance(field.widget, forms.HiddenInput):
                    if 'form-control' not in existing_class:
                        attrs['class'] = f"{existing_class} form-control".strip()


class ResearchProjectForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ResearchProject
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': '请输入预研项目名称'}),
            'description': forms.Textarea(attrs={'rows': 5, 'placeholder': '请输入项目背景、目标等详细描述...'}),
        }


class ResearchProjectNodeUpdateForm(forms.ModelForm):
    class Meta:
        model = ResearchProjectNode
        fields = ['status', 'remark']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 12, 'placeholder': '填写备注信息...'}),
        }


class ResearchProjectFileForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ResearchProjectFile
        fields = ['file', 'name', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': '文件描述...'}),
        }
