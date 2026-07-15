from django import forms
from common_utils.filters import TablerFormMixin
from app_mold_injection.models import InjectionTask, MoldType


class InjectionCompleteForm(TablerFormMixin, forms.ModelForm):
    """注塑完成表单"""
    class Meta:
        model = InjectionTask
        fields = ['remark']
        widgets = {
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


# ---- 模具 ----

class MoldTypeForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = MoldType
        fields = ['name', 'mold_code', 'mold_type', 'standard',
                  'specimen_description', 'cavity_count', 'status', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'mold_code': forms.TextInput(attrs={'class': 'form-control'}),
            'mold_type': forms.Select(attrs={'class': 'form-select'}),
            'standard': forms.Select(attrs={'class': 'form-select'}),
            'specimen_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'cavity_count': forms.NumberInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
