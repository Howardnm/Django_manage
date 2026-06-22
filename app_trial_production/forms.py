from django import forms
from common_utils.filters import TablerFormMixin
from .models import (
    ProductionOrder, ExtrusionTask,
    SampleInventory,
)


class ProductionOrderForm(TablerFormMixin, forms.ModelForm):
    """创建生产工单表单"""
    class Meta:
        model = ProductionOrder
        fields = ['quantity_planned', 'process_profile', 'remark']
        widgets = {
            'quantity_planned': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'process_profile': forms.Select(attrs={'class': 'form-select'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class ProductionOrderUpdateForm(TablerFormMixin, forms.ModelForm):
    """编辑生产工单"""
    class Meta:
        model = ProductionOrder
        fields = ['remark']
        widgets = {
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


# ---- 挤出任务 ----

class ExtrusionRecordForm(TablerFormMixin, forms.ModelForm):
    """挤出生产记录表单"""
    class Meta:
        model = ExtrusionTask
        fields = [
            # 温度参数
            'temp_zone_1', 'temp_zone_2', 'temp_zone_3', 'temp_zone_4',
            'temp_zone_5', 'temp_zone_6', 'temp_zone_7', 'temp_zone_8',
            'temp_zone_9', 'temp_zone_10', 'temp_zone_11', 'temp_zone_12',
            'temp_head',
            # 主机参数
            'screw_speed', 'torque', 'current', 'melt_pressure', 'melt_temp', 'vacuum',
            # 喂料参数
            'main_feeder_speed', 'side_feeder_speed', 'liquid_pump_speed',
            # 后处理参数
            'throughput', 'cooling_method', 'strand_count', 'water_temp',
            'water_bath_length', 'air_knife_pressure', 'pelletizing_speed', 'screen_mesh',
            # 产出与备注
            'total_output', 'remark',
        ]
        widgets = {
            **{f: forms.NumberInput(attrs={'class': 'form-control'})
               for f in ExtrusionTask.TEMP_FIELDS},
            'screw_speed': forms.NumberInput(attrs={'class': 'form-control'}),
            'torque': forms.NumberInput(attrs={'class': 'form-control'}),
            'current': forms.NumberInput(attrs={'class': 'form-control'}),
            'melt_pressure': forms.NumberInput(attrs={'class': 'form-control'}),
            'melt_temp': forms.NumberInput(attrs={'class': 'form-control'}),
            'vacuum': forms.NumberInput(attrs={'class': 'form-control'}),
            'main_feeder_speed': forms.NumberInput(attrs={'class': 'form-control'}),
            'side_feeder_speed': forms.NumberInput(attrs={'class': 'form-control'}),
            'liquid_pump_speed': forms.NumberInput(attrs={'class': 'form-control'}),
            'throughput': forms.NumberInput(attrs={'class': 'form-control'}),
            'cooling_method': forms.Select(attrs={'class': 'form-select'}),
            'strand_count': forms.NumberInput(attrs={'class': 'form-control'}),
            'water_temp': forms.NumberInput(attrs={'class': 'form-control'}),
            'water_bath_length': forms.NumberInput(attrs={'class': 'form-control'}),
            'air_knife_pressure': forms.NumberInput(attrs={'class': 'form-control'}),
            'pelletizing_speed': forms.NumberInput(attrs={'class': 'form-control'}),
            'screen_mesh': forms.TextInput(attrs={'class': 'form-control'}),
            'total_output': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


# 注塑/模具表单已迁移至 app_mold_injection.forms
# 色粉 BOM 表单已迁移至 app_color_center.forms
# 测试结果表单已迁移至 app_material_testing.forms

# ---- 样品库存 ----

class PelletSplitForm(forms.Form):
    """颗粒分拨表单（非 ModelForm，由 Service 层处理入库）"""
    formula = forms.ModelChoiceField(
        queryset=None, required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
    sub_type = forms.ChoiceField(
        choices=[('FINISHED', '颗粒成品'), ('FOR_INJECTION', '待打样颗粒')],
        widget=forms.Select(attrs={'class': 'form-select'}))
    quantity = forms.DecimalField(
        max_digits=10, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}))
    packaging_desc = forms.CharField(
        required=False, max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control'}))
    storage_location = forms.CharField(
        required=False, max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control'}))


PelletSplitFormSet = forms.formset_factory(
    PelletSplitForm, extra=4, can_delete=True
)


class SapEntryForm(TablerFormMixin, forms.ModelForm):
    """SAP 入库表单"""
    class Meta:
        model = SampleInventory
        fields = ['sap_material_code', 'sap_batch_number',
                  'sap_warehouse_date', 'sap_storage_location']
        widgets = {
            'sap_material_code': forms.TextInput(attrs={'class': 'form-control'}),
            'sap_batch_number': forms.TextInput(attrs={'class': 'form-control'}),
            'sap_warehouse_date': forms.DateInput(attrs={
                'class': 'form-control', 'type': 'date'}),
            'sap_storage_location': forms.TextInput(attrs={'class': 'form-control'}),
        }


class SapEntryFormForSpecimen(forms.Form):
    """样条样品的 SAP 入库表单（样条不涉及 SAP 物料号，仅记录位置）"""
    sap_storage_location = forms.CharField(
        required=False, max_length=50, label="SAP库位",
        widget=forms.TextInput(attrs={'class': 'form-control'}))
