from django import forms
from django.forms import BaseModelFormSet, modelformset_factory, ValidationError
from common_utils.filters import TablerFormMixin
from app_process.models import AbstractExtrusionParams, ProcessProfile
from .models import (
    ProductionOrder, ExtrusionTask, OrderProcessParams,
)
from app_mold_injection.models import MoldRequirement


def _process_profile_widget():
    return forms.HiddenInput(attrs={'class': 'search-picker-value'})


def _coerce_pk(value):
    if value in (None, ''):
        return None
    if hasattr(value, 'pk'):
        value = value.pk
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class _ProcessProfileRemoteMixin:
    """工艺方案必填。弹窗写入隐藏域，GET 只保留当前选中项供校验显示名称。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields['process_profile']
        field.required = True
        field.widget.use_required_attribute = lambda initial: False

        if self.data:
            selected_id = _coerce_pk(self.data.get(self.add_prefix('process_profile')))
        else:
            selected_id = _coerce_pk(getattr(self.instance, 'process_profile_id', None))
            if not selected_id and self.initial:
                selected_id = _coerce_pk(self.initial.get('process_profile'))
            if selected_id:
                field.queryset = ProcessProfile.objects.filter(pk=selected_id)
            else:
                field.queryset = ProcessProfile.objects.none()

        self.selected_profile = None
        if selected_id:
            self.selected_profile = (
                ProcessProfile.objects.select_related('machine', 'screw_combination')
                .filter(pk=selected_id)
                .first()
            )


class ProductionOrderForm(_ProcessProfileRemoteMixin, TablerFormMixin, forms.ModelForm):
    """创建生产工单表单"""
    class Meta:
        model = ProductionOrder
        fields = [
            'quantity_planned', 'sap_material_code', 'process_profile',
            'drying_temperature', 'drying_duration', 'inner_bag_sealing',
            'injection_temperature', 'injection_pretreatment',
            'packaging_desc', 'storage_location', 'remark',
        ]
        widgets = {
            'quantity_planned': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'sap_material_code': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': '自动从成品材料预填'}),
            'process_profile': _process_profile_widget(),
            'drying_temperature': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': '如：80'}),
            'drying_duration': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.5', 'placeholder': '如：2'}),
            'inner_bag_sealing': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'injection_temperature': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': '如：230'}),
            'injection_pretreatment': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 1, 'placeholder': '如：80℃烘干2小时'}),
            'packaging_desc': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': '如：25kg/袋'}),
            'storage_location': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': '如：A区货架3层'}),
            'remark': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 1}),
        }


class ProductionOrderUpdateForm(_ProcessProfileRemoteMixin, TablerFormMixin, forms.ModelForm):
    """编辑生产工单"""
    class Meta:
        model = ProductionOrder
        fields = [
            'sap_material_code', 'process_profile',
            'drying_temperature', 'drying_duration', 'inner_bag_sealing',
            'injection_temperature', 'injection_pretreatment',
            'packaging_desc', 'storage_location', 'remark',
        ]
        widgets = {
            'sap_material_code': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': '自动从成品材料预填'}),
            'process_profile': _process_profile_widget(),
            'drying_temperature': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': '如：80'}),
            'drying_duration': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.5', 'placeholder': '如：2'}),
            'inner_bag_sealing': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'injection_temperature': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': '如：230'}),
            'injection_pretreatment': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 1, 'placeholder': '如：80℃烘干2小时'}),
            'packaging_desc': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': '如：25kg/袋'}),
            'storage_location': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': '如：A区货架3层'}),
            'remark': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 1}),
        }


# ---- 挤出任务 ----

class OrderProcessParamsForm(TablerFormMixin, forms.ModelForm):
    """工单工艺参数 — 创建/编辑时填写，挤出任务只读。

    未提交的项用模型默认值，避免只改了几个温区时其余必填数字把整单拦住。
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False

    def clean(self):
        cleaned = super().clean()
        for name in self.fields:
            if cleaned.get(name) not in (None, ''):
                continue
            model_field = self._meta.model._meta.get_field(name)
            if model_field.has_default():
                cleaned[name] = model_field.get_default()
        return cleaned

    class Meta:
        model = OrderProcessParams
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
        ]
        widgets = {
            **{f: forms.NumberInput(attrs={'class': 'form-control form-control-sm'})
               for f in AbstractExtrusionParams.TEMP_FIELDS},
            'screw_speed': forms.NumberInput(attrs={'class': 'form-control form-control-sm'}),
            'torque': forms.NumberInput(attrs={'class': 'form-control form-control-sm'}),
            'current': forms.NumberInput(attrs={'class': 'form-control form-control-sm'}),
            'melt_pressure': forms.NumberInput(attrs={'class': 'form-control form-control-sm'}),
            'melt_temp': forms.NumberInput(attrs={'class': 'form-control form-control-sm'}),
            'vacuum': forms.NumberInput(attrs={'class': 'form-control form-control-sm'}),
            'main_feeder_speed': forms.NumberInput(attrs={'class': 'form-control form-control-sm'}),
            'side_feeder_speed': forms.NumberInput(attrs={'class': 'form-control form-control-sm'}),
            'liquid_pump_speed': forms.NumberInput(attrs={'class': 'form-control form-control-sm'}),
            'throughput': forms.NumberInput(attrs={'class': 'form-control form-control-sm'}),
            'cooling_method': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'strand_count': forms.NumberInput(attrs={'class': 'form-control form-control-sm'}),
            'water_temp': forms.NumberInput(attrs={'class': 'form-control form-control-sm'}),
            'water_bath_length': forms.NumberInput(attrs={'class': 'form-control form-control-sm'}),
            'air_knife_pressure': forms.NumberInput(attrs={'class': 'form-control form-control-sm'}),
            'pelletizing_speed': forms.NumberInput(attrs={'class': 'form-control form-control-sm'}),
            'screen_mesh': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
        }


# 注塑/模具表单已迁移至 app_mold_injection.forms
# 色粉 BOM 表单已迁移至 app_color_center.forms
# 测试结果表单已迁移至 app_material_testing.forms

# ---- 样品库存 ----

class VersionModelChoiceField(forms.ModelChoiceField):
    """配方版本选择 — 下拉仅显示版本号"""

    def label_from_instance(self, obj):
        return f'v{obj.version}'


class PelletSplitForm(TablerFormMixin, forms.Form):
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


class MoldWithCavitySelect(forms.Select):
    """模具下拉选择控件：在每个 <option> 上附加 data-cavity 属性，供前端 JS 动态显示穴数。"""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if value:
            cavity_map = getattr(self, 'cavity_map', {})
            option['attrs']['data-cavity'] = str(cavity_map.get(str(value), '1'))
        return option


class MoldRequirementRowForm(TablerFormMixin, forms.ModelForm):
    """一行对应一个模具。变体列（各配方版本注塑次数）由模板裸 <input> 渲染，不走 Django form 字段"""

    class Meta:
        model = MoldRequirement
        fields = ['mold']
        widgets = {
            'mold': MoldWithCavitySelect(attrs={'class': 'form-select mold-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['mold'].required = True
        # 将 queryset 中各模具的穴数注入 widget，使每个 <option> 带上 data-cavity 属性
        mold_field = self.fields['mold']
        if hasattr(mold_field, 'queryset'):
            mold_field.widget.cavity_map = {
                str(m.pk): m.cavity_count
                for m in mold_field.queryset
            }


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




