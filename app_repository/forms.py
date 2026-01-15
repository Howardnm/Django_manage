from django import forms
from .models import Customer, MaterialLibrary, ProjectRepository, MaterialType, ApplicationScenario, ProjectFile, OEM, Salesperson


class TablerFormMixin:
    """混入类：自动给所有字段添加 Tabler 样式类"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            # Checkbox 需要特殊的 class
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-check-input'})
            # FileInput 需要 form-control (Tabler 支持)
            else:
                field.widget.attrs.update({'class': 'form-control'})

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
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'oem': forms.Select(attrs={'class': 'form-select'}), # 新增 OEM
            'material': forms.Select(attrs={'class': 'form-select'}),
            # 价格字段不需要特殊 widget，TablerFormMixin 会加上 form-control
        }

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