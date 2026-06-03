from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet
from common_utils.filters import TablerFormMixin
from .models import LabFormula, FormulaBOM, FormulaTestResult
from app_process.models import ProcessProfile
from app_material.models import TestConfig
from app_raw_material.models import RawMaterial
from app_basic_research.models import ResearchProject
from app_project.models import Project, ProjectNode


class _IsInvalidMixin:
    """在 _post_clean 中给有错误的字段添加 is-invalid CSS 类"""
    def _post_clean(self):
        super()._post_clean()
        for field_name in self.errors:
            if field_name in self.fields:
                field = self.fields[field_name]
                cls = field.widget.attrs.get('class', '')
                if 'is-invalid' not in cls:
                    field.widget.attrs['class'] = f'{cls} is-invalid'.strip()


# 1. 配方主表单
class LabFormulaForm(_IsInvalidMixin, TablerFormMixin, forms.ModelForm):
    class Meta:
        model = LabFormula
        fields = ['code', 'name', 'material_type', 'process', 'project', 'project_node', 'research_projects', 'cost_actual', 'is_mature', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'material_type': forms.Select(attrs={'class': 'form-select'}),
            'process': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'process'}),
            'project': forms.Select(attrs={'class': 'form-select'}),
            'project_node': forms.Select(attrs={'class': 'form-select'}),
            'research_projects': forms.SelectMultiple(attrs={'class': 'form-select remote-search', 'data-model': 'research_project'}),
            'is_mature': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # code 字段设为非必填(自动生成)
        self.fields['code'].required = False

        # 关联商业项目 & 阶段节点：锁定不可编辑，由项目进度流程控制
        self.fields['project'].disabled = True
        self.fields['project'].required = False
        self.fields['project_node'].disabled = True
        self.fields['project_node'].required = False

        if not self.data:
            instance = kwargs.get('instance')
            initial = kwargs.get('initial', {})

            # 1. 工艺方案
            if instance and instance.process_id:
                self.fields['process'].queryset = ProcessProfile.objects.filter(pk=instance.process_id)
            else:
                self.fields['process'].queryset = ProcessProfile.objects.none()

            # 2. 关联商业项目
            if instance and instance.project_id:
                self.fields['project'].queryset = Project.objects.filter(pk=instance.project_id)
            elif 'project' in initial and initial['project']:
                self.fields['project'].queryset = Project.objects.filter(pk=initial['project'])
            else:
                self.fields['project'].queryset = Project.objects.none()

            # 3. 关联项目节点 (按 project 过滤)
            project_id = None
            if instance and instance.project_id:
                project_id = instance.project_id
            elif 'project' in initial and initial['project']:
                project_id = initial['project']

            if instance and instance.project_node_id:
                self.fields['project_node'].queryset = ProjectNode.objects.filter(pk=instance.project_node_id).select_related('project')
            elif project_id:
                self.fields['project_node'].queryset = ProjectNode.objects.filter(
                    project_id=project_id,
                    stage__in=ProjectNode.FORMULA_STAGES
                ).select_related('project')
            else:
                self.fields['project_node'].queryset = ProjectNode.objects.none()

            # 4. 关联预研项目 (多对多)
            qs_projects = ResearchProject.objects.none()

            if instance and instance.pk:
                qs_projects = instance.research_projects.all()

            if 'research_projects' in initial:
                ids = initial['research_projects']
                if ids:
                    qs_projects = qs_projects | ResearchProject.objects.filter(pk__in=ids)

            self.fields['research_projects'].queryset = qs_projects

            # 6. 仅量产阶段可标记为成熟配方
            node = None
            if instance and instance.pk and instance.project_node_id:
                node = instance.project_node
            elif 'project_node' in initial:
                node_id = initial['project_node']
                if node_id:
                    try:
                        node = ProjectNode.objects.only('stage').get(pk=node_id)
                    except ProjectNode.DoesNotExist:
                        pass

            if node and not node.can_be_mature:
                self.fields['is_mature'].disabled = True
                self.fields['is_mature'].help_text = '仅量产下单阶段可标记为成熟配方'

    def clean_is_mature(self):
        is_mature = self.cleaned_data.get('is_mature')
        project_node = self.cleaned_data.get('project_node')
        if is_mature and project_node and not project_node.can_be_mature:
            raise forms.ValidationError('仅量产下单阶段可标记为成熟配方，请修改项目阶段节点后再勾选。')
        return is_mature


# 2. BOM 明细表单
class FormulaBOMForm(_IsInvalidMixin, TablerFormMixin, forms.ModelForm):
    class Meta:
        model = FormulaBOM
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
class FormulaTestResultForm(_IsInvalidMixin, TablerFormMixin, forms.ModelForm):
    value_select = forms.ChoiceField(choices=[], required=False, widget=forms.Select(attrs={'class': 'form-select value-select', 'style': 'display:none;'}))

    class Meta:
        model = FormulaTestResult
        fields = ['test_config', 'value', 'value_text', 'test_date', 'remark']
        widgets = {
            'test_config': forms.Select(attrs={'class': 'form-select form-select-search', 'onchange': 'toggleValueInput(this)'}),
            'value': forms.NumberInput(attrs={'step': '0.001', 'class': 'form-control value-number'}),
            'value_text': forms.TextInput(attrs={'class': 'form-control value-text', 'style': 'display:none;'}),
            'test_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
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

class BaseFormulaTestResultFormSet(BaseInlineFormSet):
    def get_queryset(self):
        if not hasattr(self, '_queryset'):
            qs = super().get_queryset()
            if qs.model == FormulaTestResult:
                self._queryset = qs.select_related('test_config', 'test_config__category').order_by(
                    'test_config__category__order',
                    'test_config__order'
                )
            else:
                self._queryset = qs
        return self._queryset

    def _is_form_deleted(self, form):
        """判断 form 是否被标记为删除"""
        # 优先从 cleaned_data 读取
        try:
            return bool(form.cleaned_data.get('DELETE'))
        except AttributeError:
            pass
        # 兜底：直接从原始 POST 数据检查
        try:
            return bool(form.data.get(form.add_prefix('DELETE')))
        except Exception:
            return False

    def clean(self):
        super().clean()
        if any(self.errors):
            return

        # 补充检查：新增行是否与数据库中已有记录重复
        # Django 的 validate_unique 只检查 formset 内部，不检查与 DB 的冲突
        if self.instance and self.instance.pk:
            deleting_ids = {
                form.instance.pk
                for form in self.forms
                if self.can_delete and self._is_form_deleted(form)
                if form.instance and form.instance.pk
            }
            existing_tc_ids = set(
                FormulaTestResult.objects
                .filter(formula=self.instance)
                .exclude(pk__in=deleting_ids)
                .values_list('test_config_id', flat=True)
            )
            if existing_tc_ids:
                for form in self.forms:
                    if self._is_form_deleted(form):
                        continue
                    if form.instance and form.instance.pk:
                        continue
                    tc = form.cleaned_data.get('test_config')
                    if tc and tc.pk in existing_tc_ids:
                        raise forms.ValidationError(
                            '测试项目"%s"已存在于此配方中，请勿重复添加。' % tc.name
                        )

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
    formset=BaseFormulaTestResultFormSet,
    extra=0,
    can_delete=True
)
