from django import forms
from .models import Project, ProjectNode
from django.contrib.auth.models import User


# ========================================================
# 1. 定义 Tabler 样式混入类
# (建议以后将其移动到专门的 utils.py 或 common 应用中实现复用)
# ========================================================
class TablerFormMixin:
    """
    混入类：自动给字段添加 Tabler/Bootstrap 样式类
    1. Select -> form-select (支持 Tom Select)
    2. Checkbox -> form-check-input
    3. Input/Textarea -> form-control
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
                # 如果你想让项目表单的下拉框也支持搜索，加上这个
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


class ProjectNodeUpdateForm(forms.ModelForm):
    class Meta:
        model = ProjectNode
        fields = ['status', 'remark']
        widgets = {
            'status_choices': forms.Select(attrs={'class': 'form-select'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 12, 'placeholder': '填写备注信息...'}),
        }
