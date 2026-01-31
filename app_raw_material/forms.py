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
                
                if 'value-select' not in existing_class and 'form-select-search' not in existing_class:
                    existing_class += ' form-select-search'
                    
                attrs['class'] = existing_class.strip()
            elif isinstance(field.widget, forms.CheckboxInput):
                if 'form-check-input' not in existing_class:
                    attrs['class'] = f"{existing_class} form-check-input".strip()
            elif isinstance(field.widget, forms.DateInput):
                # TablerFormMixin 应该始终为 DateInput 添加 form-control class
                if 'form-control' not in existing_class:
                    attrs['class'] = f"{existing_class} form-control".strip()
                # TablerFormMixin 应该始终为 DateInput 添加 type='date'
                attrs['type'] = 'date'
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
        exclude = ['updated_at']
        widgets = {
            'usage_method': forms.Textarea(attrs={'rows': 3}),
            'purchase_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'suitable_materials': forms.SelectMultiple(attrs={'class': 'form-select'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].label_from_instance = lambda obj: f"{obj.name} ({Truncator(obj.description).chars(22)})" if obj.description else obj.name


# 4. 原材料性能指标行表单
class RawMaterialPropertyForm(TablerFormMixin, forms.ModelForm):
    value_select = forms.ChoiceField(choices=[], required=False, widget=forms.Select(attrs={'class': 'form-select value-select', 'style': 'display:none;'}))

    class Meta:
        model = RawMaterialProperty
        fields = ['test_config', 'value', 'value_text', 'test_date', 'remark']
        widgets = {
            'test_config': forms.Select(attrs={'class': 'form-select form-select-search', 'onchange': 'toggleValueInput(this)'}),
            'value': forms.NumberInput(attrs={'step': '0.001', 'class': 'form-control value-number'}),
            'value_text': forms.TextInput(attrs={'class': 'form-control value-text', 'style': 'display:none;'}),
            # 【修复】为 test_date 明确指定 format 和 type
            'test_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'remark': forms.TextInput(attrs={'placeholder': '备注'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['test_config'].queryset = TestConfig.objects.select_related('category').order_by('category__order', 'order')
        
        if self.instance and self.instance.pk:
            dtype = self.instance.test_config.data_type
            if dtype == 'TEXT':
                self.fields['value'].widget.attrs['style'] = 'display:none;'
                self.fields['value_text'].widget.attrs['style'] = 'display:block;'
            elif dtype == 'SELECT':
                self.fields['value'].widget.attrs['style'] = 'display:none;'
                self.fields['value_text'].widget.attrs['style'] = 'display:none;'
                self.fields['value_select'].widget.attrs['style'] = 'display:block;'
                
                options = self.instance.test_config.get_options_list()
                self.fields['value_select'].choices = [(opt, opt) for opt in options]
                self.fields['value_select'].initial = self.instance.value_text
                self.fields['value_select'].widget.attrs['data-current-value'] = self.instance.value_text
        
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
