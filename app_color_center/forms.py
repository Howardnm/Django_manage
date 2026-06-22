from django import forms
from common_utils.filters import TablerFormMixin
from app_formula.models import ColorPowderBOM, ColorPowderBOMEntry
from app_raw_material.models import RawMaterial


# ---- 色粉 BOM ----

class ColorPowderBOMForm(TablerFormMixin, forms.ModelForm):
    """色粉配比主表"""
    class Meta:
        model = ColorPowderBOM
        fields = ['remark']
        widgets = {
            'remark': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
            }),
        }


class ColorPowderBOMEntryForm(TablerFormMixin, forms.ModelForm):
    """色粉配比明细"""
    class Meta:
        model = ColorPowderBOMEntry
        fields = ['feeding_port', 'raw_material', 'percentage',
                  'is_pre_mix', 'pre_mix_order', 'pre_mix_time',
                  'weighing_scale']
        widgets = {
            'raw_material': forms.Select(attrs={
                'class': 'form-select remote-search',
                'data-model': 'raw_material',
            }),
            'percentage': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.001',
            }),
            'feeding_port': forms.Select(attrs={
                'class': 'form-select form-select-search',
            }),
            'weighing_scale': forms.Select(attrs={
                'class': 'form-select form-select-search',
            }),
            'is_pre_mix': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'pre_mix_order': forms.NumberInput(attrs={
                'class': 'form-control',
            }),
            'pre_mix_time': forms.NumberInput(attrs={
                'class': 'form-control',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['weighing_scale'].initial = 'D'
        self.fields['is_pre_mix'].initial = True
        if self.instance and self.instance.pk:
            self.fields['raw_material'].queryset = RawMaterial.objects.filter(
                pk=self.instance.raw_material_id
            )
            if self.data:
                raw_id = self.data.get(self.add_prefix('raw_material'))
                if raw_id and str(raw_id) != str(self.instance.raw_material_id):
                    self.fields['raw_material'].queryset = (
                        self.fields['raw_material'].queryset |
                        RawMaterial.objects.filter(pk=raw_id)
                    )
        elif self.data:
            raw_id = self.data.get(self.add_prefix('raw_material'))
            if raw_id:
                self.fields['raw_material'].queryset = RawMaterial.objects.filter(pk=raw_id)
            else:
                self.fields['raw_material'].queryset = RawMaterial.objects.none()
        else:
            self.fields['raw_material'].queryset = RawMaterial.objects.none()


ColorPowderBOMEntryFormSet = forms.inlineformset_factory(
    ColorPowderBOM, ColorPowderBOMEntry,
    form=ColorPowderBOMEntryForm,
    extra=5, can_delete=True
)
