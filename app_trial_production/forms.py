from django import forms
from django.forms import BaseModelFormSet, modelformset_factory, ValidationError
from common_utils.filters import TablerFormMixin
from .models import (
    ProductionOrder, ExtrusionTask,
    SampleInventory,
)
from app_mold_injection.models import MoldRequirement


class ProductionOrderForm(TablerFormMixin, forms.ModelForm):
    """创建生产工单表单"""
    class Meta:
        model = ProductionOrder
        fields = ['quantity_planned', 'process_profile', 'packaging_desc', 'storage_location', 'remark']
        widgets = {
            'quantity_planned': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'process_profile': forms.Select(attrs={'class': 'form-select'}),
            'packaging_desc': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '如：25kg/袋'}),
            'storage_location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '如：A区货架3层'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class ProductionOrderUpdateForm(TablerFormMixin, forms.ModelForm):
    """编辑生产工单"""
    class Meta:
        model = ProductionOrder
        fields = ['process_profile', 'packaging_desc', 'storage_location', 'remark']
        widgets = {
            'process_profile': forms.Select(attrs={'class': 'form-select'}),
            'packaging_desc': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '如：25kg/袋'}),
            'storage_location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '如：A区货架3层'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
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
            # 备注
            'remark',
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
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


# 注塑/模具表单已迁移至 app_mold_injection.forms
# 色粉 BOM 表单已迁移至 app_color_center.forms
# 测试结果表单已迁移至 app_material_testing.forms

# ---- 样品库存 ----

class VersionModelChoiceField(forms.ModelChoiceField):
    """配方版本选择 — 下拉仅显示版本号"""

    def label_from_instance(self, obj):
        return f'v{obj.version}'


class PelletSplitForm(forms.Form):
    """颗粒分拨表单（非 ModelForm，由 Service 层处理入库）"""
    formula = VersionModelChoiceField(
        queryset=None, required=False,
        widget=forms.Select(attrs={'class': 'form-select'}))
    sub_type = forms.ChoiceField(
        choices=[('FINISHED', '颗粒成品'), ('FOR_INJECTION', '待打样颗粒')],
        widget=forms.Select(attrs={'class': 'form-select'}))
    quantity = forms.DecimalField(
        max_digits=10, decimal_places=2, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}))


PelletSplitFormSet = forms.formset_factory(
    PelletSplitForm, extra=4, can_delete=True
)


# ---- 工单模具计划 ----
# 一行 = 一个模具，各配方版本的注塑次数由模板裸 <input name="variant_qty_{row}_{formulaPk}"> 渲染
# 后端通过 BaseMoldRequirementRowFormSet.get_variant_qtys(row_idx) 从 POST 原始数据读取


class MoldRequirementRowForm(forms.ModelForm):
    """一行对应一个模具。变体列（各配方版本注塑次数）由模板裸 <input> 渲染，不走 Django form 字段"""

    class Meta:
        model = MoldRequirement
        fields = ['mold']
        widgets = {
            'mold': forms.Select(attrs={'class': 'form-select mold-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['mold'].required = True


class BaseMoldRequirementRowFormSet(BaseModelFormSet):
    """模具矩阵 FormSet：注入 formula_pks + 校验重复/空值 + 从 POST 裸数据提取变体列值"""

    def __init__(self, *args, formula_pks=None, **kwargs):
        self.formula_pks = list(formula_pks) if formula_pks else []
        super().__init__(*args, **kwargs)

    def clean(self):
        if any(self.errors):
            return
        molds_seen = set()
        for i, form in enumerate(self.forms):
            if form.cleaned_data.get('DELETE'):
                continue
            mold = form.cleaned_data.get('mold')
            if not mold:
                continue
            if mold.pk in molds_seen:
                raise ValidationError(f'模具 "{mold.name}" 重复选择，请检查')
            molds_seen.add(mold.pk)
            # 注意：不要求每行必须有非零数量，_save_mold_matrix 会自动跳过空行

    def get_variant_qtys(self, row_idx):
        """从 POST 裸数据提取变体列值 → {formula_pk: quantity}（仅返回 quantity > 0 的项）"""
        result = {}
        for pk in self.formula_pks:
            key = f'variant_qty_{row_idx}_{pk}'
            val = self.data.get(key, '0')
            try:
                qty = int(val)
            except (ValueError, TypeError):
                qty = 0
            if qty > 0:
                result[int(pk)] = qty
        return result

    def _get_variant_qty(self, row_idx, formula_pk):
        key = f'variant_qty_{row_idx}_{formula_pk}'
        try:
            return int(self.data.get(key, '0'))
        except (ValueError, TypeError):
            return 0


MoldRequirementRowFormSet = modelformset_factory(
    MoldRequirement,
    form=MoldRequirementRowForm,
    formset=BaseMoldRequirementRowFormSet,
    extra=0,
    can_delete=True,
)


class SapEntryForm(TablerFormMixin, forms.ModelForm):
    """SAP 入库表单 — 单样品/批量通用，字段非必填（由 Service 层处理实际保存）"""
    class Meta:
        model = SampleInventory
        fields = ['sap_material_code', 'sap_batch_number',
                  'sap_warehouse_date', 'sap_storage_location']
        widgets = {
            'sap_material_code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'SAP物料编码',
            }),
            'sap_batch_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'SAP批次号',
            }),
            'sap_warehouse_date': forms.DateInput(attrs={
                'class': 'form-control', 'type': 'date',
            }),
            'sap_storage_location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '如: WH-A-03',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.required = False


class StandaloneSampleForm(TablerFormMixin, forms.ModelForm):
    """独立样品创建表单 — 不关联工单，用于样品库手动新增"""

    class Meta:
        model = SampleInventory
        fields = [
            'type', 'sub_type', 'formula', 'trial_code',
            'quantity', 'specimen_count', 'specimen_qualified',
            'storage_location', 'packaging_desc', 'mold', 'batch_label',
        ]
        widgets = {
            'type': forms.Select(attrs={'class': 'form-select'}),
            'sub_type': forms.Select(attrs={'class': 'form-select'}),
            'formula': forms.Select(attrs={
                'class': 'form-select remote-search',
                'data-model': 'formula',
            }),
            'trial_code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '实验单号（可选）',
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01',
                'placeholder': '重量(kg)',
            }),
            'specimen_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '样条数量（条）',
            }),
            'specimen_qualified': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '合格数量（条）',
            }),
            'storage_location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '如：A区货架3层',
            }),
            'packaging_desc': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '如：25kg/袋',
            }),
            'mold': forms.Select(attrs={'class': 'form-select'}),
            'batch_label': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '批次标签',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['type'].required = True
        self.fields['sub_type'].required = True
        self.fields['formula'].required = False
        self.fields['trial_code'].required = False
        self.fields['quantity'].required = False
        self.fields['specimen_count'].required = False
        self.fields['specimen_qualified'].required = False
        self.fields['mold'].required = False
        self.fields['batch_label'].required = False
        self.fields['storage_location'].required = False
        self.fields['packaging_desc'].required = False

    def clean(self):
        cleaned = super().clean()
        sample_type = cleaned.get('type')
        if sample_type == 'PELLET':
            qty = cleaned.get('quantity')
            if qty is None or float(qty) <= 0:
                raise ValidationError('颗粒样品必须填写数量(kg)')
        elif sample_type == 'SPECIMEN':
            cnt = cleaned.get('specimen_count')
            if cnt is None or int(cnt) <= 0:
                raise ValidationError('样条样品必须填写样条数量')
        return cleaned
