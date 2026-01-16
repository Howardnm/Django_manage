from django import forms
from .models import Customer, MaterialLibrary, ProjectRepository, MaterialType, ApplicationScenario, ProjectFile, OEM, Salesperson


class TablerFormMixin:
    """
    混入类：
    1. 自动给普通字段添加 form-control
    2. 自动给 Checkbox 添加 form-check-input
    3. 自动给 Select 添加 form-select 和 form-select-search (启用 Tom Select)
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field_name, field in self.fields.items():
            # 获取该字段原本可能已经在 widgets 里定义的 class，避免覆盖
            attrs = field.widget.attrs
            existing_class = attrs.get('class', '')
            # -----------------------------------------------------------
            # 情况 1: 下拉选择框 (Select / SelectMultiple)
            # -----------------------------------------------------------
            if isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                # Tabler 标准样式是 form-select，而不是 form-control
                # 追加 form-select-search 以启用我们刚才写的 Tom Select JS
                # 使用 strip() 去除可能产生的多余空格
                if 'form-select' not in existing_class:
                    existing_class += ' form-select'
                if 'form-select-search' not in existing_class:
                    existing_class += ' form-select-search'
                attrs['class'] = existing_class.strip()
            # -----------------------------------------------------------
            # 情况 2: 复选框 (Checkbox)
            # -----------------------------------------------------------
            elif isinstance(field.widget, forms.CheckboxInput):
                if 'form-check-input' not in existing_class:
                    attrs['class'] = f"{existing_class} form-check-input".strip()
            # -----------------------------------------------------------
            # 情况 3: 其他输入框 (Text, Number, Email, Date, File, Password...)
            # -----------------------------------------------------------
            else:
                # 排除 HiddenInput，不需要样式
                if not isinstance(field.widget, forms.HiddenInput):
                    if 'form-control' not in existing_class:
                        attrs['class'] = f"{existing_class} form-control".strip()


# ==============================================================================
# 1. 客户表单
# ==============================================================================
class CustomerForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = '__all__'


# ==============================================================================
# 2. 材料表单
# ==============================================================================
class MaterialForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = MaterialLibrary
        fields = '__all__'
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4, 'placeholder': '请输入材料特性描述...'}),
            'scenario': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'flammability': forms.Select(attrs={'class': 'form-select'}),
        }


# ==============================================================================
# 3. 项目档案表单 (主表)
# ==============================================================================

class ProjectRepositoryForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ProjectRepository
        exclude = ['project', 'updated_at']


# 4. 【新增】项目文件上传表单
class ProjectFileForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ProjectFile
        fields = ['file_type', 'file', 'description']
        widgets = {
            'file_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.TextInput(attrs={'placeholder': '例如：V1.0版本图纸'}),
        }


# 【新增】业务员管理表单
class SalespersonForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = Salesperson
        fields = ['name', 'phone', 'email']


# 6. 主机厂表单
class OEMForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = OEM
        fields = ['name', 'short_name', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': '备注信息...'}),
        }


# ==============================================================================
# 4. 材料类型表单
# ==============================================================================
class MaterialTypeForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = MaterialType
        fields = ['name', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


# ==============================================================================
# 5. 应用场景表单
# ==============================================================================
class ApplicationScenarioForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ApplicationScenario
        fields = ['name', 'requirements']
        widgets = {
            'requirements': forms.Textarea(attrs={'rows': 3, 'placeholder': '例如：耐高温、抗冲击...'}),
        }
