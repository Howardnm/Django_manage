from django import forms
from common_utils.filters import TablerFilterMixin
from .models import ProcessType, MachineModel, ScrewCombination, ProcessProfile

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
            else:
                if not isinstance(field.widget, forms.HiddenInput):
                    if 'form-control' not in existing_class:
                        attrs['class'] = f"{existing_class} form-control".strip()

# 1. 工艺类型表单
class ProcessTypeForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ProcessType
        fields = '__all__'
        widgets = {
            'material_types': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

# 2. 机台型号表单
class MachineModelForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = MachineModel
        fields = '__all__'
        widgets = {
            'suitable_materials': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

# 3. 螺杆组合表单
class ScrewCombinationForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ScrewCombination
        fields = '__all__'
        widgets = {
            'machines': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'suitable_materials': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

# 4. 工艺方案表单
class ProcessProfileForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ProcessProfile
        fields = '__all__'
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'qc_check_points': forms.Textarea(attrs={'rows': 3}),
            'screw_configuration': forms.Textarea(attrs={'rows': 3}),
            'process_type': forms.Select(attrs={'class': 'form-select'}),
            'machine': forms.Select(attrs={'class': 'form-select'}),
            'screw_combination': forms.Select(attrs={'class': 'form-select'}),
            'cooling_method': forms.Select(attrs={'class': 'form-select'}),
        }
