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
                
                # 【修复】如果字段明确指定了不需要搜索 (no-search)，则不添加 form-select-search
                # 或者反过来，只对默认情况添加。
                # 这里我们简单判断：如果 widget attrs 里没有明确禁止，就添加。
                # 但更简单的做法是：在 MaterialDataPointForm 中手动移除该类。
                # 不过为了通用性，我们可以在这里加一个判断：
                # 如果 widget 已经有了 'value-select' 类 (我们在 MaterialDataPointForm 里加的)，就不加 search
                if 'value-select' not in existing_class and 'form-select-search' not in existing_class:
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
    # 动态添加的选择字段，用于 data_type='SELECT' 的情况
    # 注意：这里不要加 form-select-search，否则会被 Tom Select 初始化
    # TablerFormMixin 会自动加 form-select-search，除非我们在 Mixin 里做了排除，或者在这里覆盖 class
    value_select = forms.ChoiceField(choices=[], required=False, widget=forms.Select(attrs={'class': 'form-select value-select', 'style': 'display:none;'}))

    class Meta:
        model = MaterialDataPoint
        fields = ['test_config', 'value', 'value_text', 'remark'] # 增加 value_text
        widgets = {
            # 开启搜索功能，方便快速查找 "ISO 527"
            'test_config': forms.Select(attrs={'class': 'form-select form-select-search', 'onchange': 'toggleValueInput(this)'}),
            # 【修改】允许3位小数
            'value': forms.NumberInput(attrs={'step': '0.001', 'class': 'form-control value-number'}),
            'value_text': forms.TextInput(attrs={'class': 'form-control value-text', 'style': 'display:none;'}), # 默认隐藏
            'remark': forms.TextInput(attrs={'placeholder': '备注'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 【性能优化】预加载 TestConfig，避免 N+1 查询
        # 并且按分类排序，方便选择
        self.fields['test_config'].queryset = TestConfig.objects.select_related('category').order_by('category__order', 'order')
        
        # 如果是编辑状态，且当前数据是文本类型，则显示文本框，隐藏数字框
        if self.instance and self.instance.pk:
            dtype = self.instance.test_config.data_type
            if dtype == 'TEXT':
                self.fields['value'].widget.attrs['style'] = 'display:none;'
                self.fields['value_text'].widget.attrs['style'] = 'display:block;'
            elif dtype == 'SELECT':
                self.fields['value'].widget.attrs['style'] = 'display:none;'
                self.fields['value_text'].widget.attrs['style'] = 'display:none;'
                self.fields['value_select'].widget.attrs['style'] = 'display:block;'
                
                # 动态填充选项
                options = self.instance.test_config.get_options_list()
                self.fields['value_select'].choices = [(opt, opt) for opt in options]
                # 设置初始值
                self.fields['value_select'].initial = self.instance.value_text
                # 将当前值存入 data-current-value 属性，方便前端 JS 读取
                self.fields['value_select'].widget.attrs['data-current-value'] = self.instance.value_text
        
        # 【关键修复】如果是 POST 请求，必须重新填充 choices，否则 Django 验证会失败
        # 因为 ChoiceField 默认验证提交的值必须在 choices 中
        if self.data:
            # 尝试从 POST 数据中获取 test_config ID
            # 字段名格式通常是: properties-0-test_config
            prefix = self.prefix or ''
            test_config_key = f"{prefix}-test_config" if prefix else "test_config"
            test_config_id = self.data.get(test_config_key)
            
            if test_config_id:
                try:
                    config = TestConfig.objects.get(pk=test_config_id)
                    if config.data_type == 'SELECT':
                        options = config.get_options_list()
                        self.fields['value_select'].choices = [(opt, opt) for opt in options]
                except (TestConfig.DoesNotExist, ValueError):
                    pass

    def clean(self):
        cleaned_data = super().clean()
        test_config = cleaned_data.get('test_config')
        value_select = cleaned_data.get('value_select')
        
        # 如果是选择类型，将选择的值赋给 value_text
        if test_config and test_config.data_type == 'SELECT':
            # 修复：即使 value_select 为空字符串，也要赋值给 value_text，以便清空
            cleaned_data['value_text'] = value_select
            
        return cleaned_data

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

        # 自定义 OEM 字段的显示逻辑：名称 (简称)
        self.fields['oem'].label_from_instance = lambda obj: f"{obj.name} ({obj.short_name})" if obj.short_name else obj.name

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
        fields = ['name', 'classification', 'description']
        widgets = {
            'classification': forms.Select(attrs={'class': 'form-select'}),
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
        fields = ['category', 'name', 'standard', 'condition', 'unit', 'order', 'data_type', 'options_config'] # 增加 options_config
        widgets = {
            'category': forms.Select(attrs={'class': 'form-select'}),
            'order': forms.NumberInput(attrs={'placeholder': '排序权重，越小越靠前'}),
            'data_type': forms.Select(attrs={'class': 'form-select'}),
            'options_config': forms.Textarea(attrs={'rows': 2, 'placeholder': '仅当类型为选择时有效，用逗号分隔，如: V-0,V-1,HB'}),
        }
