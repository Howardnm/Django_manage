from django import forms
from .models import Customer, ProjectRepository, MaterialType, ApplicationScenario, ProjectFile, OEM, Salesperson
from django.forms import inlineformset_factory
from .models import MaterialLibrary, MaterialDataPoint, MaterialFile, TestConfig

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
            'description': forms.Textarea(attrs={'rows': 3}),
            'scenarios': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'flammability': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
        }

# 性能数据行表单
class MaterialDataPointForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = MaterialDataPoint
        fields = ['test_config', 'value', 'remark']
        widgets = {
            # 开启搜索功能，方便快速查找 "ISO 527"
            'test_config': forms.Select(attrs={'class': 'form-select form-select-search'}),
            'value': forms.NumberInput(attrs={'step': '0.01'}),
            'remark': forms.TextInput(attrs={'placeholder': '备注'}),
        }

# 定义 FormSet
MaterialDataFormSet = inlineformset_factory(
    MaterialLibrary,
    MaterialDataPoint,
    form=MaterialDataPointForm,
    extra=0,       # 默认不显示空行，靠 JS 添加
    can_delete=True
)

# 【新增】材料附件上传表单
class MaterialFileForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = MaterialFile
        fields = ['file_type', 'file', 'description']
        widgets = {
            'file_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.TextInput(attrs={'placeholder': '例如：2024年最新UL黄卡'}),
        }

# ==============================================================================
# 3. 项目档案表单 (主表)
# ==============================================================================

class ProjectRepositoryForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ProjectRepository
        exclude = ['project', 'updated_at']
        # Widget 这里加上特殊的 class，比如 'remote-search'，方便 JS 识别
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'customer'}),
            'oem': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'oem'}),
            'material': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'material'}),
            'salesperson': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'salesperson'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 【性能核心优化】
        # 如果没有 data (说明是 GET 请求渲染页面)，则清空 QuerySet，避免渲染成千上万个 option
        # 但是，必须保留 "当前已选" 的那个值，否则页面上显示为空
        if not self.data:
            instance = kwargs.get('instance')

            # 1. 优化材料字段
            if instance and instance.material_id:
                self.fields['material'].queryset = MaterialLibrary.objects.filter(pk=instance.material_id)
            else:
                self.fields['material'].queryset = MaterialLibrary.objects.none()

            # 2. 优化客户字段
            if instance and instance.customer_id:
                self.fields['customer'].queryset = Customer.objects.filter(pk=instance.customer_id)
            else:
                self.fields['customer'].queryset = Customer.objects.none()

            # 3. 优化 OEM
            if instance and instance.oem_id:
                self.fields['oem'].queryset = OEM.objects.filter(pk=instance.oem_id)
            else:
                self.fields['oem'].queryset = OEM.objects.none()

            # 4. 优化业务员
            if instance and instance.salesperson_id:
                self.fields['salesperson'].queryset = Salesperson.objects.filter(pk=instance.salesperson_id)
            else:
                self.fields['salesperson'].queryset = Salesperson.objects.none()

        # 注意：如果是 POST 请求 (self.data 存在)，不要动 queryset
        # Django 需要用完整的 .all() (或者包含提交值的 queryset) 来验证数据有效性
        # 但因为 ModelChoiceField 默认就是 .all()，所以不需要额外写代码


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

# ==============================================================================
# 6. 测试标准配置表单
# ==============================================================================
class TestConfigForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = TestConfig
        fields = ['category', 'name', 'standard', 'condition', 'unit', 'order']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-select'}),
            'order': forms.NumberInput(attrs={'placeholder': '排序权重，越小越靠前'}),
        }
