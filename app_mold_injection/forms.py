from django import forms
from common_utils.filters import TablerFormMixin
from app_mold_injection.models import InjectionTask, MoldRequirement, MoldType


# ---- 注塑任务 ----

class MoldRequirementForm(TablerFormMixin, forms.ModelForm):
    """模具需求明细 — 仅选择模具，各配方版本注塑次数由模板裸 <input> 渲染"""
    class Meta:
        model = MoldRequirement
        fields = ['mold']
        widgets = {
            'mold': forms.Select(attrs={'class': 'form-select'}),
        }


MoldRequirementFormSet = forms.inlineformset_factory(
    InjectionTask, MoldRequirement,
    form=MoldRequirementForm,
    extra=3, can_delete=True
)


class InjectionTaskForm(TablerFormMixin, forms.ModelForm):
    """注塑任务表单"""
    class Meta:
        model = InjectionTask
        fields = ['injection_params_note', 'operator']
        widgets = {
            'injection_params_note': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'operator': forms.Select(attrs={'class': 'form-select'}),
        }


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
