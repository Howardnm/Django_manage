from django import forms
from .models import (
    ProductionOrder, MoldType, ExtrusionRecord,
    ProductionOutput, SampleSplit, SampleInventory,
    InjectionMoldingOrder, MoldRequirement, SpecimenInventory,
    TestingOrder, TrialTestResult,
)
from app_raw_material.models import RawMaterial
from app_formula.models import ColorPowderBOM, ColorPowderBOMEntry


class ProductionOrderForm(forms.ModelForm):
    """创建生产工单表单"""
    class Meta:
        model = ProductionOrder
        fields = [
            'quantity_planned', 'process_profile', 'remark',
        ]
        widgets = {
            'quantity_planned': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'process_profile': forms.Select(attrs={'class': 'form-select'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class ProductionOrderUpdateForm(forms.ModelForm):
    """编辑生产工单"""
    class Meta:
        model = ProductionOrder
        fields = ['remark']
        widgets = {
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class ExtrusionRecordForm(forms.ModelForm):
    """挤出生产记录表单"""
    class Meta:
        model = ExtrusionRecord
        exclude = ['production_order', 'recorded_by', 'created_at']
        widgets = {
            # 温度
            'temp_zone_1': forms.NumberInput(attrs={'class': 'form-control'}),
            'temp_zone_2': forms.NumberInput(attrs={'class': 'form-control'}),
            'temp_zone_3': forms.NumberInput(attrs={'class': 'form-control'}),
            'temp_zone_4': forms.NumberInput(attrs={'class': 'form-control'}),
            'temp_zone_5': forms.NumberInput(attrs={'class': 'form-control'}),
            'temp_zone_6': forms.NumberInput(attrs={'class': 'form-control'}),
            'temp_zone_7': forms.NumberInput(attrs={'class': 'form-control'}),
            'temp_zone_8': forms.NumberInput(attrs={'class': 'form-control'}),
            'temp_zone_9': forms.NumberInput(attrs={'class': 'form-control'}),
            'temp_zone_10': forms.NumberInput(attrs={'class': 'form-control'}),
            'temp_zone_11': forms.NumberInput(attrs={'class': 'form-control'}),
            'temp_zone_12': forms.NumberInput(attrs={'class': 'form-control'}),
            'temp_head': forms.NumberInput(attrs={'class': 'form-control'}),
            # 主机参数
            'screw_speed': forms.NumberInput(attrs={'class': 'form-control'}),
            'torque': forms.NumberInput(attrs={'class': 'form-control'}),
            'current': forms.NumberInput(attrs={'class': 'form-control'}),
            'melt_pressure': forms.NumberInput(attrs={'class': 'form-control'}),
            'melt_temp': forms.NumberInput(attrs={'class': 'form-control'}),
            'vacuum': forms.NumberInput(attrs={'class': 'form-control'}),
            # 喂料
            'main_feeder_speed': forms.NumberInput(attrs={'class': 'form-control'}),
            'side_feeder_speed': forms.NumberInput(attrs={'class': 'form-control'}),
            'liquid_pump_speed': forms.NumberInput(attrs={'class': 'form-control'}),
            # 产能与后处理
            'throughput': forms.NumberInput(attrs={'class': 'form-control'}),
            'cooling_method': forms.Select(attrs={'class': 'form-select'}),
            'strand_count': forms.NumberInput(attrs={'class': 'form-control'}),
            'water_temp': forms.NumberInput(attrs={'class': 'form-control'}),
            'water_bath_length': forms.NumberInput(attrs={'class': 'form-control'}),
            'air_knife_pressure': forms.NumberInput(attrs={'class': 'form-control'}),
            'pelletizing_speed': forms.NumberInput(attrs={'class': 'form-control'}),
            'screen_mesh': forms.TextInput(attrs={'class': 'form-control'}),
            # 备注
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class ProductionOutputForm(forms.ModelForm):
    """生产产出表单"""
    class Meta:
        model = ProductionOutput
        fields = ['remark']
        widgets = {
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class SampleSplitForm(forms.ModelForm):
    """样品分拨表单"""
    class Meta:
        model = SampleSplit
        fields = ['formula', 'destination', 'quantity', 'packaging_desc', 'customer_destination']
        widgets = {
            'formula': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'packaging_desc': forms.TextInput(attrs={'class': 'form-control'}),
            'customer_destination': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'destination': forms.Select(attrs={'class': 'form-select'}),
        }


SampleSplitFormSet = forms.inlineformset_factory(
    ProductionOrder, SampleSplit,
    form=SampleSplitForm,
    extra=3, can_delete=True
)


class MoldTypeForm(forms.ModelForm):
    class Meta:
        model = MoldType
        fields = ['name', 'mold_code', 'mold_type', 'standard', 'specimen_description',
                  'cavity_count', 'status', 'description']
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


class MoldRequirementForm(forms.ModelForm):
    """模具需求明细"""
    class Meta:
        model = MoldRequirement
        fields = ['mold', 'formula', 'specimen_quantity']


MoldRequirementFormSet = forms.inlineformset_factory(
    InjectionMoldingOrder, MoldRequirement,
    form=MoldRequirementForm,
    extra=3, can_delete=True
)


class InjectionMoldingOrderForm(forms.ModelForm):
    """注塑工单表单"""
    class Meta:
        model = InjectionMoldingOrder
        fields = ['sample_split', 'sample_inventory',
                  'injection_params_note', 'assigned_operator']
        widgets = {
            'injection_params_note': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class InjectionMoldingCompleteForm(forms.ModelForm):
    """注塑完成表单"""
    class Meta:
        model = InjectionMoldingOrder
        fields = ['status', 'remark']
        widgets = {
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class SpecimenInventoryForm(forms.ModelForm):
    """样条产出记录"""
    class Meta:
        model = SpecimenInventory
        fields = ['mold', 'quantity_produced', 'quantity_qualified',
                  'storage_location', 'batch_label']


SpecimenInventoryFormSet = forms.inlineformset_factory(
    InjectionMoldingOrder, SpecimenInventory,
    form=SpecimenInventoryForm,
    extra=0, can_delete=False
)


class TestingOrderForm(forms.ModelForm):
    """测试工单表单"""
    class Meta:
        model = TestingOrder
        fields = ['test_items', 'specimens', 'assigned_to']
        widgets = {
            'test_items': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'specimens': forms.SelectMultiple(attrs={'class': 'form-select'}),
        }


class TrialTestResultForm(forms.ModelForm):
    """测试结果填写"""
    class Meta:
        model = TrialTestResult
        fields = ['value', 'value_text', 'test_date', 'remark']
        widgets = {
            'value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
            'value_text': forms.TextInput(attrs={'class': 'form-control'}),
            'test_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'remark': forms.TextInput(attrs={'class': 'form-control'}),
        }


class ColorPowderBOMForm(forms.ModelForm):
    """色粉配比主表"""
    class Meta:
        model = ColorPowderBOM
        fields = ['remark']
        widgets = {
            'remark': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
            }),
        }


class ColorPowderBOMEntryForm(forms.ModelForm):
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
        # 色粉场景下的默认值
        self.fields['weighing_scale'].initial = 'D'
        self.fields['is_pre_mix'].initial = True
        # 限制 queryset 为已选中的项，避免渲染大量 option（配合 TomSelect remote-search）
        if self.instance and self.instance.pk:
            self.fields['raw_material'].queryset = RawMaterial.objects.filter(
                pk=self.instance.raw_material_id
            )
            # POST 时：如果用户通过远程搜索改了原料，需把新值也纳入 queryset 以通过验证
            if self.data:
                raw_id = self.data.get(self.add_prefix('raw_material'))
                if raw_id and str(raw_id) != str(self.instance.raw_material_id):
                    self.fields['raw_material'].queryset = (
                        self.fields['raw_material'].queryset | RawMaterial.objects.filter(pk=raw_id)
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
