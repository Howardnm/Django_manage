from django import forms
from .models import Customer, MaterialLibrary, ProjectRepository, MaterialType, ApplicationScenario


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


# 1. 客户表单
class CustomerForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = '__all__'


# 2. 材料表单
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


# 3. 项目档案表单 (核心)
class ProjectRepositoryForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ProjectRepository
        # 排除不需要用户填写的字段
        # 注意：因为 models.py 里已经删除了 scenario 字段，这里不需要特意排除它，它自动就不存在了
        exclude = ['project', 'updated_at']

        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'material': forms.Select(attrs={'class': 'form-select'}),
        }

# 4. 材料类型表单
class MaterialTypeForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = MaterialType
        fields = ['name', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

# 5. 应用场景表单
class ApplicationScenarioForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ApplicationScenario
        fields = ['name', 'requirements']
        widgets = {
            'requirements': forms.Textarea(attrs={'rows': 3, 'placeholder': '例如：耐高温、抗冲击...'}),
        }