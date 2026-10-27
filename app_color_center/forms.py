from django import forms
from django.core.validators import DecimalValidator
from django.forms.models import BaseInlineFormSet
from common_utils.filters import TablerFormMixin
from app_formula.models import ColorPowderBOM, ColorPowderBOMEntry
from app_raw_material.models import RawMaterial

from app_color_center.units import (
    GRAM_DECIMAL_PLACES,
    GRAM_MAX_DIGITS,
    grams_to_percentage,
    percentage_to_grams,
)


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
                'class': 'form-control', 'step': 'any',
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
        # 模型是 6 位小数的份数。这里收的是克，最多 3 位，除以 250 后仍能原样存回。
        field = self.fields['percentage']
        field.label = 'G/25KG'
        field.max_digits = GRAM_MAX_DIGITS
        field.decimal_places = GRAM_DECIMAL_PLACES
        field.validators = [
            v for v in field.validators if not isinstance(v, DecimalValidator)
        ]
        field.validators.append(DecimalValidator(GRAM_MAX_DIGITS, GRAM_DECIMAL_PLACES))
        if (
            not self.is_bound
            and self.instance.pk
            and self.instance.percentage is not None
        ):
            self.initial['percentage'] = percentage_to_grams(self.instance.percentage)
        self.fields['weighing_scale'].initial = 'D'
        self.fields['is_pre_mix'].initial = True
        # remote-search 只渲染当前选中项；不收窄的话每个下拉都会遍历整张原材料表。
        selected = RawMaterial.objects.select_related('category')
        if self.instance and self.instance.pk and self.instance.raw_material_id:
            qs = selected.filter(pk=self.instance.raw_material_id)
            if self.data:
                raw_id = self.data.get(self.add_prefix('raw_material'))
                if raw_id and str(raw_id) != str(self.instance.raw_material_id):
                    qs = qs | selected.filter(pk=raw_id)
            self.fields['raw_material'].queryset = qs
        elif self.data:
            raw_id = self.data.get(self.add_prefix('raw_material'))
            if raw_id:
                self.fields['raw_material'].queryset = selected.filter(pk=raw_id)
            else:
                self.fields['raw_material'].queryset = RawMaterial.objects.none()
        else:
            self.fields['raw_material'].queryset = RawMaterial.objects.none()

    def clean_percentage(self):
        """页面填的是每 25 kg 的克数，库存仍是份数。"""
        grams = self.cleaned_data.get('percentage')
        if grams in (None, ''):
            return grams
        return grams_to_percentage(grams)


class BaseColorPowderBOMEntryFormSet(BaseInlineFormSet):
    """色粉配比明细 formset — 校验至少填写一行有效明细（以 raw_material 为准）。"""

    def get_queryset(self):
        if not hasattr(self, '_queryset'):
            self._queryset = (
                super().get_queryset()
                .select_related('raw_material__category')
            )
        return self._queryset

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
