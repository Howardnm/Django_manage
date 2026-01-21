from django import forms
from common_utils.filters import TablerFormMixin
from .models import MachineModel, ScrewCombination, ProcessProfile


# 1. 机台型号表单
class MachineModelForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = MachineModel
        fields = '__all__'
        widgets = {
            'suitable_materials': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }


# 2. 螺杆组合表单
class ScrewCombinationForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ScrewCombination
        fields = '__all__'
        widgets = {
            'machines': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'suitable_materials': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }


# 3. 工艺方案表单
class ProcessProfileForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ProcessProfile
        fields = '__all__'
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'qc_check_points': forms.Textarea(attrs={'rows': 3}),
            'material_types': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'machine': forms.Select(attrs={'class': 'form-select'}),
            'screw_combination': forms.Select(attrs={'class': 'form-select'}),
            'cooling_method': forms.Select(attrs={'class': 'form-select'}),
        }
