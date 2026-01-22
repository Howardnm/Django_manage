from django import forms
from django.forms import inlineformset_factory
from .models import Supplier, RawMaterialType, RawMaterial, RawMaterialProperty
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
                if 'form-select-search' not in existing_class:
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
    class Meta:
        model = RawMaterialProperty
        fields = ['test_config', 'value', 'test_date', 'remark']
        widgets = {
            'test_config': forms.Select(attrs={'class': 'form-select form-select-search'}),
            # 【修改】允许3位小数
            'value': forms.NumberInput(attrs={'step': '0.001'}),
            'test_date': forms.DateInput(attrs={'type': 'date'}),
            'remark': forms.TextInput(attrs={'placeholder': '备注'}),
        }

# 定义 FormSet
RawMaterialPropertyFormSet = inlineformset_factory(
    RawMaterial,
    RawMaterialProperty,
    form=RawMaterialPropertyForm,
    extra=0,
    can_delete=True
)
