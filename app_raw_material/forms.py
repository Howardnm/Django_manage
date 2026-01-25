from django import forms
from django.forms import inlineformset_factory
from .models import Supplier, RawMaterialType, RawMaterial, RawMaterialProperty
from app_repository.models import TestConfig
from django.utils.text import Truncator

class TablerFormMixin:
    """
    混入类：自动给字段添加 Tabler 样式
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            attrs = field.widget.attrs
            existing_class = attrs.get('class', '')
            if isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                if 'form-select' not in existing_class:
                    existing_class += ' form-select'
                
                # 【修复】如果字段明确指定了不需要搜索 (no-search)，则不添加 form-select-search
                if 'value-select' not in existing_class and 'form-select-search' not in existing_class:
                    existing_class += ' form-select-search'
                    
                attrs['class'] = existing_class.strip()
            elif isinstance(field.widget, forms.CheckboxInput):
                if 'form-check-input' not in existing_class:
                    attrs['class'] = f"{existing_class} form-check-input".strip()
            elif isinstance(field.widget, forms.DateInput):
                if 'form-control' not in existing_class:
                    attrs['class'] = f"{existing_class} form-control".strip()
                attrs['type'] = 'date' # 强制日期控件
            else:
                if not isinstance(field.widget, forms.HiddenInput):
                    if 'form-control' not in existing_class:
                        attrs['class'] = f"{existing_class} form-control".strip()

# 1. 供应商表单
class SupplierForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = Supplier
        fields = '__all__'
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'product_categories': forms.SelectMultiple(attrs={'class': 'form-select'}),
        }

# 2. 原材料类型表单
class RawMaterialTypeForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = RawMaterialType
        fields = '__all__'
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

# 3. 原材料表单
class RawMaterialForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = RawMaterial
        fields = '__all__'
        exclude = ['updated_at']
        widgets = {
            'usage_method': forms.Textarea(attrs={'rows': 3}),
            'purchase_date': forms.DateInput(attrs={'type': 'date'}),
            # 【新增】适用材料类型多选框
            'suitable_materials': forms.SelectMultiple(attrs={'class': 'form-select'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 自定义 category 字段的 label_from_instance
        # 使用 Truncator 截断描述，限制为 30 个字符，并去除换行符
        self.fields['category'].label_from_instance = lambda obj: f"{obj.name} ({Truncator(obj.description).chars(22)})" if obj.description else obj.name

# 4. 原材料性能指标行表单
class RawMaterialPropertyForm(TablerFormMixin, forms.ModelForm):
    # 动态添加的选择字段，用于 data_type='SELECT' 的情况
    value_select = forms.ChoiceField(choices=[], required=False, widget=forms.Select(attrs={'class': 'form-select value-select', 'style': 'display:none;'}))

    class Meta:
        model = RawMaterialProperty
        fields = ['test_config', 'value', 'value_text', 'test_date', 'remark'] # 增加 value_text
        widgets = {
            'test_config': forms.Select(attrs={'class': 'form-select form-select-search', 'onchange': 'toggleValueInput(this)'}),
            # 【修改】允许3位小数
            'value': forms.NumberInput(attrs={'step': '0.001', 'class': 'form-control value-number'}),
            'value_text': forms.TextInput(attrs={'class': 'form-control value-text', 'style': 'display:none;'}), # 默认隐藏
            'test_date': forms.DateInput(attrs={'type': 'date'}),
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
        
        # 如果是 POST 请求，必须重新填充 choices，否则 Django 验证会失败
        if self.data:
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
            cleaned_data['value_text'] = value_select
            
        return cleaned_data

# 定义 FormSet
RawMaterialPropertyFormSet = inlineformset_factory(
    RawMaterial,
    RawMaterialProperty,
    form=RawMaterialPropertyForm,
    extra=0,
    can_delete=True
)
