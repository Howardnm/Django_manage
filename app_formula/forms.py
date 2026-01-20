from django import forms
from django.forms import inlineformset_factory
from common_utils.filters import TablerFilterMixin
from .models import LabFormula, FormulaBOM, FormulaTestResult
from app_process.models import ProcessProfile
from app_repository.models import MaterialLibrary, TestConfig
from app_raw_material.models import RawMaterial

class TablerFormMixin:
    """
    混入类：自动给字段添加 Tabler 样式
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            attrs = field.widget.attrs
            existing_class = attrs.get('class', '')
            if isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                if 'form-select' not in existing_class:
                    existing_class += ' form-select'
                attrs['class'] = existing_class.strip()
            elif isinstance(field.widget, forms.CheckboxInput):
                if 'form-check-input' not in existing_class:
                    attrs['class'] = f"{existing_class} form-check-input".strip()
            else:
                if not isinstance(field.widget, forms.HiddenInput):
                    if 'form-control' not in existing_class:
                        attrs['class'] = f"{existing_class} form-control".strip()

# 1. 配方主表单
class LabFormulaForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = LabFormula
        exclude = ['creator', 'created_at', 'cost_predicted']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'material_type': forms.Select(attrs={'class': 'form-select'}),
            'process': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'process'}),
            'related_materials': forms.SelectMultiple(attrs={'class': 'form-select remote-search', 'data-model': 'material'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if not self.data:
            instance = kwargs.get('instance')
            initial = kwargs.get('initial', {})
            
            # 1. 工艺方案
            if instance and instance.process_id:
                self.fields['process'].queryset = ProcessProfile.objects.filter(pk=instance.process_id)
            else:
                self.fields['process'].queryset = ProcessProfile.objects.none()
                
            # 2. 关联成品 (多对多)
            # 【修复】同时考虑 instance 和 initial
            qs = MaterialLibrary.objects.none()
            
            if instance and instance.pk:
                qs = instance.related_materials.all()
            
            # 如果 initial 中有预设值 (例如从材料详情页跳转过来)
            if 'related_materials' in initial:
                ids = initial['related_materials']
                if ids:
                    qs = qs | MaterialLibrary.objects.filter(pk__in=ids)
            
            self.fields['related_materials'].queryset = qs


# 2. BOM 明细表单
class FormulaBOMForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = FormulaBOM
        fields = ['feeding_port', 'raw_material', 'percentage', 'is_tail', 'is_pre_mix', 'pre_mix_order', 'pre_mix_time']
        widgets = {
            'feeding_port': forms.Select(attrs={'class': 'form-select'}),
            'raw_material': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'raw_material'}),
            'percentage': forms.NumberInput(attrs={'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if not self.data:
            instance = kwargs.get('instance')
            if instance and instance.pk and instance.raw_material_id:
                self.fields['raw_material'].queryset = RawMaterial.objects.filter(pk=instance.raw_material_id)
            else:
                self.fields['raw_material'].queryset = RawMaterial.objects.none()


# 3. 测试结果表单
class FormulaTestResultForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = FormulaTestResult
        fields = ['test_config', 'value', 'test_date', 'remark']
        widgets = {
            'test_config': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'test_config'}),
            # 【修改】允许3位小数
            'value': forms.NumberInput(attrs={'step': '0.001'}),
            'test_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if not self.data:
            instance = kwargs.get('instance')
            if instance and instance.pk and instance.test_config_id:
                self.fields['test_config'].queryset = TestConfig.objects.filter(pk=instance.test_config_id)
            else:
                self.fields['test_config'].queryset = TestConfig.objects.none()

# 定义 FormSet
FormulaBOMFormSet = inlineformset_factory(
    LabFormula,
    FormulaBOM,
    form=FormulaBOMForm,
    extra=0,
    can_delete=True
)

FormulaTestResultFormSet = inlineformset_factory(
    LabFormula,
    FormulaTestResult,
    form=FormulaTestResultForm,
    extra=0,
    can_delete=True
)
