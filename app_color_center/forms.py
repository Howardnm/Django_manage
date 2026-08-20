from django import forms
from django.forms.models import BaseInlineFormSet
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


class BaseColorPowderBOMEntryFormSet(BaseInlineFormSet):
    """色粉配比明细 formset — 校验至少填写一行有效明细（以 raw_material 为准）。"""

    def _is_form_deleted(self, form):
        """判断 form 是否被标记为删除"""
        try:
            return bool(form.cleaned_data.get('DELETE'))
        except AttributeError:
            pass
        try:
            return bool(form.data.get(form.add_prefix('DELETE')))
        except Exception:
            return False

    def clean(self):
        super().clean()

        # 以「是否存在任一未删除且选定了原材料」的明细行为准；
        # 空白行即使触发 raw_material 必填校验，也应统一落到「表格为空」提示。
        has_row = any(
            not self._is_form_deleted(form)
            and form.cleaned_data.get('raw_material')
            for form in self.forms
        )
        if not has_row:
            raise forms.ValidationError('色粉配比BOM不能为空，请至少填写一行明细。')


ColorPowderBOMEntryFormSet = forms.inlineformset_factory(
    ColorPowderBOM, ColorPowderBOMEntry,
    form=ColorPowderBOMEntryForm,
    formset=BaseColorPowderBOMEntryFormSet,
    extra=5, can_delete=True
)
