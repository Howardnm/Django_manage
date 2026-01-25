from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet
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
            elif isinstance(field.widget, forms.DateInput):
                if 'form-control' not in existing_class:
                    attrs['class'] = f"{existing_class} form-control".strip()
                attrs['type'] = 'date' # 强制日期控件
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
        # 【新增】weighing_scale 字段
        fields = ['feeding_port', 'weighing_scale', 'raw_material', 'percentage', 'is_tail', 'is_pre_mix', 'pre_mix_order', 'pre_mix_time']
        widgets = {
            'feeding_port': forms.Select(attrs={'class': 'form-select'}),
            'weighing_scale': forms.Select(attrs={'class': 'form-select'}),
            'raw_material': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'raw_material'}),
            'percentage': forms.NumberInput(attrs={'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        rm_ids = set()
        
        # 1. 如果表单已绑定数据 (POST 请求)，从 POST 数据中获取 raw_material 的 ID
        if self.data:
            field_key = self.add_prefix('raw_material')
            val = self.data.get(field_key)
            if val:
                try: rm_ids.add(int(val))
                except ValueError: pass
        
        # 2. 如果表单有实例 (编辑现有 BOM 行)，从实例中获取 raw_material 的 ID
        # self.instance 是当前 BOMForm 对应的 FormulaBOM 对象
        if self.instance and self.instance.pk and self.instance.raw_material_id:
            rm_ids.add(self.instance.raw_material_id)
        
        # 3. 如果表单有初始数据 (例如从 LabFormulaDuplicateView 传入的 initial)，从 initial 中获取 raw_material 的 ID
        # kwargs['initial'] 包含了当前 FormSet 中单个 Form 的初始数据
        if 'initial' in kwargs and kwargs['initial'] and 'raw_material' in kwargs['initial']:
            raw_material_val = kwargs['initial']['raw_material']
            if raw_material_val:
                # raw_material_val 可能是 RawMaterial 对象，也可能是其 PK
                rm_ids.add(raw_material_val.pk if hasattr(raw_material_val, 'pk') else raw_material_val)

        # 设置 raw_material 字段的 queryset，确保包含所有需要的 RawMaterial 对象
        if rm_ids:
            self.fields['raw_material'].queryset = RawMaterial.objects.filter(pk__in=rm_ids)
        else:
            # 如果没有 raw_material 被选中或初始化，则 queryset 为空
            self.fields['raw_material'].queryset = RawMaterial.objects.none()


# 3. 测试结果表单
class FormulaTestResultForm(TablerFormMixin, forms.ModelForm):
    # 动态添加的选择字段，用于 data_type='SELECT' 的情况
    value_select = forms.ChoiceField(choices=[], required=False, widget=forms.Select(attrs={'class': 'form-select value-select', 'style': 'display:none;'}))

    class Meta:
        model = FormulaTestResult
        fields = ['test_config', 'value', 'value_text', 'test_date', 'remark'] # 增加 value_text
        widgets = {
            # 【修改】移除 remote-search 类，改为 form-select-search (普通搜索)
            'test_config': forms.Select(attrs={'class': 'form-select form-select-search', 'onchange': 'toggleValueInput(this)'}),
            # 【修改】允许3位小数
            'value': forms.NumberInput(attrs={'step': '0.001', 'class': 'form-control value-number'}),
            'value_text': forms.TextInput(attrs={'class': 'form-control value-text', 'style': 'display:none;'}), # 默认隐藏
            'test_date': forms.DateInput(attrs={'type': 'date'}),
            'remark': forms.TextInput(attrs={'placeholder': '备注'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 【修改】不再清空 queryset，而是加载所有 TestConfig
        # 因为字段不多，直接加载所有选项更方便
        self.fields['test_config'].queryset = TestConfig.objects.select_related('category').all().order_by('category__order', 'order')
        
        # 如果是编辑状态，且当前数据是文本类型，则显示文本框，隐藏数字框
        if self.instance and self.instance.pk:
            dtype = self.instance.test_config.data_type
            if dtype == 'TEXT':
                self.fields['value'].widget.attrs['style'] = 'display:none;'
                self.fields['value_text'].widget.attrs['style'] = 'display:block;'
            elif dtype == 'SELECT':
                self.fields['value'].widget.attrs['style'] = 'display:none;'
                self.fields['value_text'].widget.attrs['style'] = 'display:none;'
                self.fields['value_select'].widget.attrs['style'] = 'display:block;'
                
                # 动态填充选项
                options = self.instance.test_config.get_options_list()
                self.fields['value_select'].choices = [(opt, opt) for opt in options]
                # 设置初始值
                self.fields['value_select'].initial = self.instance.value_text
                # 将当前值存入 data-current-value 属性，方便前端 JS 读取
                self.fields['value_select'].widget.attrs['data-current-value'] = self.instance.value_text
        
        # 如果是 POST 请求，必须重新填充 choices，否则 Django 验证会失败
        if self.data:
            prefix = self.prefix or ''
            test_config_key = f"{prefix}-test_config" if prefix else "test_config"
            test_config_id = self.data.get(test_config_key)
            
            if test_config_id:
                try:
                    config = TestConfig.objects.get(pk=test_config_id)
                    if config.data_type == 'SELECT':
                        options = config.get_options_list()
                        self.fields['value_select'].choices = [(opt, opt) for opt in options]
                except (TestConfig.DoesNotExist, ValueError):
                    pass

    def clean(self):
        cleaned_data = super().clean()
        test_config = cleaned_data.get('test_config')
        value_select = cleaned_data.get('value_select')
        
        # 如果是选择类型，将选择的值赋给 value_text
        if test_config and test_config.data_type == 'SELECT':
            cleaned_data['value_text'] = value_select
            
        return cleaned_data

# 【新增】自定义 FormSet，用于控制查询集的排序
class BaseFormulaTestResultFormSet(BaseInlineFormSet):
    def get_queryset(self):
        # 默认的 get_queryset 不会 select_related，也不会按 TestConfig 排序
        # 这里我们重写它，确保编辑时显示的顺序是正确的
        if not hasattr(self, '_queryset'):
            # 【修复】这里不能直接调用 super().get_queryset()，因为 BaseInlineFormSet 的 get_queryset 
            # 依赖于 self.instance (即 LabFormula 对象)。
            # 如果是 CreateView，self.instance 是一个新的未保存对象，没有关联的 test_results，
            # 所以 super().get_queryset() 会返回空 QuerySet，这是正常的。
            # 但如果我们在 CreateView 中传入了 queryset=LabFormula.objects.none() (为了显示空行)，
            # 这里的逻辑可能会有问题。
            
            # 关键点：FieldError: Cannot resolve keyword 'test_config' into field.
            # 这说明我们试图对 LabFormula 进行排序，而不是 FormulaTestResult。
            # BaseInlineFormSet.get_queryset 返回的是 FormulaTestResult 的 QuerySet。
            
            qs = super().get_queryset()
            
            # 只有当 qs 是 FormulaTestResult 的 QuerySet 时，才能按 test_config 排序
            if qs.model == FormulaTestResult:
                self._queryset = qs.select_related('test_config', 'test_config__category').order_by(
                    'test_config__category__order', 
                    'test_config__order'
                )
            else:
                self._queryset = qs
                
        return self._queryset

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
    formset=BaseFormulaTestResultFormSet, # 使用自定义 FormSet
    extra=0,
    can_delete=True
)
