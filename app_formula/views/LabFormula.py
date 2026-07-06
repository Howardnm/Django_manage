from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, get_object_or_404
from django.core.exceptions import PermissionDenied
from django.db.models import Subquery, OuterRef, DecimalField, Q

from app_formula.models import LabFormula, FormulaBOM, FormulaTestResult
from app_formula.forms import LabFormulaForm, FormulaBOMFormSet, FormulaTestResultFormSet
from app_formula.utils.filters import LabFormulaFilter
from app_formula.mixins import FormulaAccessMixin
from app_project.mixins import ProjectAccessMixin
from app_project.models import Project
from app_formula.utils.search_picker_config import for_formula_import
from django.utils.safestring import mark_safe


def _build_integrity_error_message(e):
    """将 IntegrityError（唯一约束冲突）转为用户友好的错误信息"""
    err_str = str(e)
    if 'uq_test_manual' in err_str:
        return '测试项目重复：同一配方中已存在相同的测试项目，请检查并删除重复的测试行。'
    if 'uq_test_per_order' in err_str:
        return '该工单回写的测试结果已存在，请勿重复录入。'
    return '保存失败，数据违反唯一性约束，请检查输入是否重复。'


def _build_formula_error_message(form, bom_formset=None, test_formset=None):
    """构建详细的字段错误信息（主表单 + BOM明细 + 测试结果）"""
    lines = ['<strong>保存失败，请修正以下问题：</strong>']
    found = False

    for field_name, errs in form.errors.items():
        for e in errs:
            if field_name == '__all__':
                lines.append(f'• {e}')
            else:
                label = form[field_name].label if field_name in form.fields else field_name
                lines.append(f'• {label}: {e}')
            found = True

    for label, formset in [('BOM明细', bom_formset), ('测试结果', test_formset)]:
        if not formset:
            continue
        for e in formset.non_form_errors():
            lines.append(f'• {label}: {e}')
            found = True
        for i, sf in enumerate(formset):
            if not sf.errors:
                continue
            for field_name, errs in sf.errors.items():
                for e in errs:
                    if field_name == '__all__':
                        lines.append(f'• {label} 第{i+1}行: {e}')
                    else:
                        flabel = sf[field_name].label if field_name in sf.fields else field_name
                        lines.append(f'• {label} 第{i+1}行 {flabel}: {e}')
                    found = True

    if not found:
        lines.append('• 请检查各字段的错误提示信息。')

    return mark_safe('<br>'.join(lines))


class FormulaPrepareView(ProjectAccessMixin, View):
    """从项目节点中转：校验项目权限，存储关联信息到 session，跳转配方新增页"""
    permission_required = 'app_project.view_project'

    def post(self, request):
        project_id = request.POST.get('project_id')
        project_node_id = request.POST.get('project_node_id')
        name = request.POST.get('name', '')

        if project_id:
            project = get_object_or_404(Project.objects.select_related('manager'), pk=project_id)
            self.check_object_permission(project)

            if not project.material:
                messages.error(request, f'项目"{project.name}"尚未关联成品材料，请先在项目详情中关联材料后再创建配方。')
                return redirect(reverse('project_detail', kwargs={'pk': project_id}))

        request.session['formula_prepare'] = {
            'project_id': project_id,
            'project_node_id': project_node_id,
            'name': name,
        }
        return redirect(reverse('formula_add'))


class FormulaStartFreshView(FormulaAccessMixin, View):
    """从配方列表页新增配方：清理 session 中残留的 project 关联"""
    permission_required = 'app_formula.view_labformula'

    def get(self, request):
        request.session.pop('formula_prepare', None)
        return redirect('formula_add')


class FormulaImportPrepareView(FormulaAccessMixin, View):
    """将待导入的实验单 code 存入 session，跳转新增页以预填充 formsets（合并该实验单下所有版本的 BOM）"""
    permission_required = 'app_formula.add_labformula'

    def post(self, request):
        experiment_code = request.POST.get('experiment_code')
        if not experiment_code:
            messages.error(request, '请选择要导入的实验单')
            return redirect(reverse('formula_add'))
        # 验证该实验单下至少有一个配方版本，且用户有权限访问
        formulas = LabFormula.objects.filter(code=experiment_code)
        if not formulas.exists():
            messages.error(request, f'实验单「{experiment_code}」不存在')
            return redirect(reverse('formula_add'))
        # 对每个版本的 formula 做权限校验
        for f in formulas:
            self.check_object_permission(f)

        session_data = request.session.get('formula_prepare', {})
        session_data['import_experiment_code'] = experiment_code
        request.session['formula_prepare'] = session_data
        version_count = formulas.count()
        messages.success(request, f'已从实验单「{experiment_code}」（{version_count}个版本）加载 BOM 和测试项目数据，请确认后保存。')
        return redirect(reverse('formula_add'))


class LabFormulaListView(FormulaAccessMixin, ListView):
    """
    实验配方列表：
    - 准入：app_formula.view_labformula + 研发/管理员身份。
    - 隔离：仅限本部门配方。
    """
    permission_required = 'app_formula.view_labformula'
    model = LabFormula
    template_name = 'apps/app_formula/list.html'
    context_object_name = 'formulas'
    paginate_by = 20

    def get_queryset(self):
        # 1. 调用 Mixin 自动执行部门隔离过滤
        base_qs = super().get_queryset().select_related(
            'material_type', 'creator', 'process',
            'project__material', 'project_node__project__material'
        ).prefetch_related('research_projects')
        
        # 2. 动态指标排序逻辑 (保持原有功能)
        sort_params = self.request.GET.getlist('sort')
        metric_map = {
            'density': ('密度', 'val_density'),
            'ash': ('灰分', 'val_ash'),
            'melt_index': ('熔融', 'val_melt'),
            'tensile': ('拉伸强度', 'val_tensile'),
            'flex_strength': ('弯曲强度', 'val_flex_strength'),
            'flex_modulus': ('弯曲模量', 'val_flex_modulus'),
            'impact': ('冲击', 'val_impact'),
            'hdt': ('热变形', 'val_hdt'),
        }

        # 4. 动态 Annotate
        if sort_params:
            std = self.request.GET.get('std', 'ISO')
            for param in sort_params:
                clean_sort = param.lstrip('-')
                if clean_sort in metric_map:
                    keyword, field_name = metric_map[clean_sort]
                    base_qs = base_qs.annotate(**{
                        field_name: Subquery(
                            FormulaTestResult.objects.filter(
                                formula=OuterRef('pk'),
                                test_config__name__icontains=keyword,
                                test_config__standard__icontains=std,
                                production_order__isnull=True,
                            ).values('value')[:1],
                            output_field=DecimalField()
                        )
                    })

        self.filterset = LabFormulaFilter(self.request.GET, queryset=base_qs, request=self.request)
        return self.filterset.qs.order_by('-created_at') if not sort_params else self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 性能优化：批量加载测试结果 (逻辑保持不变)
        current_std = self.request.GET.get('std', 'ISO')
        std_keywords = ['ASTM'] if current_std == 'ASTM' else ['ISO', 'GB', 'DIN', 'IEC']

        # 1. 获取当前页的所有配方 ID
        page_formulas = context['formulas'] # 这是一个 list 或 QuerySet
        formula_ids = [f.pk for f in page_formulas]
        
        std_query = Q()
        for k in std_keywords: std_query |= Q(test_config__standard__icontains=k)
        
        results = FormulaTestResult.objects.filter(
            formula_id__in=formula_ids,
            production_order__isnull=True,
        ).filter(
            std_query,
            test_config__name__regex=r'(密度|灰分|熔融|拉伸|弯曲|冲击|热变形)'
        ).select_related('test_config')
        
        data_map = {}
        for res in results:
            fid = res.formula_id
            if fid not in data_map: data_map[fid] = {}
            name = res.test_config.name
            if '密度' in name: data_map[fid]['val_density'] = res.value
            elif '灰分' in name: data_map[fid]['val_ash'] = res.value
            elif '熔融' in name: data_map[fid]['val_melt'] = res.value
            elif '拉伸' in name: data_map[fid]['val_tensile'] = res.value
            elif '弯曲强度' in name: data_map[fid]['val_flex_strength'] = res.value
            elif '弯曲模量' in name: data_map[fid]['val_flex_modulus'] = res.value
            elif '冲击' in name: data_map[fid]['val_impact'] = res.value
            elif '热变形' in name: data_map[fid]['val_hdt'] = res.value

        # 4. 将数据挂载到配方对象上
        for f in page_formulas:
            if f.pk in data_map:
                for key, val in data_map[f.pk].items(): setattr(f, key, val)

        context.update({
            'cart_formula_ids': self.request.session.get('cart_formulas_v2', []),
            'filter': self.filterset,
            'current_std': current_std,
            'current_sort': self.request.GET.get('sort', ''),
        })
        return context


class LabFormulaDetailView(FormulaAccessMixin, DetailView):
    """配方详情：需有查看权限，且仅限本部门。"""
    permission_required = 'app_formula.view_labformula'
    model = LabFormula
    template_name = 'apps/app_formula/detail.html'
    context_object_name = 'formula'

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def get_queryset(self):
        return super().get_queryset().select_related(
            'material_type', 'creator', 'process',
            'project', 'project__material',
            'project_node', 'project_node__project__material'
        ).prefetch_related(
            'bom_lines__raw_material__category',
            'test_results__test_config',
            'research_projects'
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sorted_results = self.object.test_results.filter(production_order__isnull=True).select_related('test_config', 'test_config__category').order_by(
            'test_config__category__order', 'test_config__order'
        )
        context['sorted_test_results'] = sorted_results
        return context


class LabFormulaCreateView(FormulaAccessMixin, CreateView):
    """创建配方：需有增加权限，且通常仅限研发。"""
    permission_required = 'app_formula.add_labformula'
    model = LabFormula
    form_class = LabFormulaForm
    template_name = 'apps/app_formula/form.html'

    def get(self, request, *args, **kwargs):
        """鉴权通过后，校验项目材料是否已关联"""
        session_data = request.session.get('formula_prepare', {})
        project_id = session_data.get('project_id')
        if project_id:
            from app_project.models import Project
            project = get_object_or_404(Project.objects.only('name', 'material'), pk=project_id)
            if not project.material:
                from django.contrib import messages
                from django.urls import reverse
                messages.error(request, f'项目"{project.name}"尚未关联成品材料，请先在项目详情中关联材料后再创建配方。')
                return redirect(reverse('project_detail', kwargs={'pk': project_id}))
        return super().get(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        session_data = self.request.session.get('formula_prepare', {})
        if session_data.get('project_id'):
            initial['project'] = session_data['project_id']
        if session_data.get('project_node_id'):
            initial['project_node'] = session_data['project_node_id']
        if session_data.get('name'):
            initial['name'] = session_data['name']

        # 根据项目关联的成品材料预填基材类型和颜色字段
        if session_data.get('project_id'):
            try:
                project = Project.objects.select_related('material').only(
                    'material__category_id',
                    'material__material_color_name',
                    'material__pantone_code',
                    'material__rgb_value',
                ).get(pk=session_data['project_id'])
                if project.material:
                    initial['material_type'] = initial.get('material_type') or project.material.category_id
                    initial['material_color_name'] = initial.get('material_color_name') or project.material.material_color_name
                    initial['pantone_code'] = initial.get('pantone_code') or project.material.pantone_code
                    initial['rgb_value'] = initial.get('rgb_value') or project.material.rgb_value
            except Project.DoesNotExist:
                pass

        # 从导入实验单预填充基础信息（取版本号最大的配方）
        import_experiment_code = session_data.get('import_experiment_code')
        if import_experiment_code:
            try:
                source = LabFormula.objects.filter(code=import_experiment_code).order_by('-version').only(
                    'name', 'material_type_id', 'process_id', 'description',
                    'material_color_name', 'pantone_code', 'rgb_value',
                ).first()
                if source:
                    # 基础信息：全量导入（不含关联信息）
                    initial['name'] = initial.get('name') or source.name
                    initial['material_type'] = initial.get('material_type') or source.material_type_id
                    initial['process'] = initial.get('process') or source.process_id
                    initial['description'] = initial.get('description') or source.description
                    initial['material_color_name'] = initial.get('material_color_name') or source.material_color_name
                    initial['pantone_code'] = initial.get('pantone_code') or source.pantone_code
                    initial['rgb_value'] = initial.get('rgb_value') or source.rgb_value
                    # 关联信息不导入：project / project_node / research_projects 保持原样
            except LabFormula.DoesNotExist:
                pass

        return initial

    def _get_session_data(self):
        return self.request.session.get('formula_prepare', {})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增实验配方'
        context['show_import_button'] = True
        context['enable_multi_column'] = True
        context['search_picker'] = for_formula_import()
        session_data = self._get_session_data()
        project_node_id = session_data.get('project_node_id')
        project_id = session_data.get('project_id')

        # 验证用户对项目的访问权限，同时缓存项目对象以复用
        project = None
        if project_id:
            from app_project.models import Project
            from app_trial_production.mixins import RndAccessMixin
            try:
                project = Project.objects.select_related('manager').only(
                    'name', 'manager_id', 'manager__department'
                ).get(pk=project_id)
                RndAccessMixin.check_project_ownership(project, self.request.user)
            except (Project.DoesNotExist, PermissionDenied):
                project = None

        # 获取项目节点阶段，用于控制 is_mature 勾选
        if project_node_id and project:
            try:
                from app_project.models import ProjectNode
                node = ProjectNode.objects.only('stage', 'round', 'project__name', 'project_id').get(
                    pk=project_node_id, project=project
                )
                context['project_node_stage'] = node.stage
                context['can_be_mature'] = node.can_be_mature
                context['project_node_display'] = str(node)
            except ProjectNode.DoesNotExist:
                context['project_node_stage'] = None
                context['project_node_display'] = None
        else:
            context['project_node_stage'] = None
            context['project_node_display'] = None
            # 清除失效的 session 数据
            if project_node_id and not project:
                session_data.pop('project_node_id', None)
                self.request.session['formula_prepare'] = session_data

        # 锁定显示：项目名
        if project:
            context['project_name'] = project.name
        else:
            context['project_name'] = None
            if project_id:
                session_data.pop('project_id', None)
                self.request.session['formula_prepare'] = session_data
        if self.request.POST:
            context['bom_formset'] = FormulaBOMFormSet(self.request.POST, prefix='bom')
            context['test_formset'] = FormulaTestResultFormSet(self.request.POST, prefix='test')
        else:
            import_experiment_code = session_data.get('import_experiment_code')
            if import_experiment_code:
                try:
                    source_formulas = list(LabFormula.objects.filter(
                        code=import_experiment_code
                    ).prefetch_related(
                        'bom_lines__raw_material__category',
                        'test_results__test_config__category',
                    ).order_by('version'))
                    if not source_formulas:
                        raise LabFormula.DoesNotExist()

                    source_count = len(source_formulas)

                    if source_count > 1:
                        # 多版本 → 多列模式：每个源版本一列，用户可调整各列百分比
                        from collections import OrderedDict

                        # 构建 BOM 并集 (按 raw_material_id + feeding_port 去重)
                        bom_union = OrderedDict()
                        bom_index_map = {}
                        for f in source_formulas:
                            for b in f.bom_lines.all():
                                key = (b.raw_material_id, b.feeding_port)
                                if key not in bom_union:
                                    bom_index_map[key] = len(bom_union)
                                    bom_union[key] = {
                                        'feeding_port': b.feeding_port,
                                        'weighing_scale': b.weighing_scale,
                                        'raw_material': b.raw_material,
                                        'is_tail': b.is_tail,
                                        'is_pre_mix': b.is_pre_mix,
                                        'pre_mix_order': b.pre_mix_order,
                                        'pre_mix_time': b.pre_mix_time,
                                        'percentage': Decimal('0'),
                                    }

                        # column 0 = 第一个源版本的 percentage
                        primary = source_formulas[0]
                        for b in primary.bom_lines.all():
                            key = (b.raw_material_id, b.feeding_port)
                            if key in bom_union:
                                bom_union[key]['percentage'] = b.percentage

                        FormulaBOMFormSet.extra = max(len(bom_union), 1)
                        context['bom_formset'] = FormulaBOMFormSet(prefix='bom', initial=list(bom_union.values()))
                        context['bom_index_map'] = bom_index_map

                        # 构建测试并集 (按 test_config_id 去重)
                        test_union = OrderedDict()
                        test_index_map = {}
                        for f in source_formulas:
                            for t in f.test_results.filter(production_order__isnull=True):
                                if t.test_config_id not in test_union:
                                    test_index_map[t.test_config_id] = len(test_union)
                                    test_union[t.test_config_id] = {
                                        'test_config': t.test_config,
                                        'test_date': t.test_date,
                                        'remark': t.remark,
                                    }
                        # column 0 = 第一个源版本的测试值
                        for t in primary.test_results.filter(production_order__isnull=True):
                            if t.test_config_id in test_union:
                                if t.test_config.data_type == 'NUMBER':
                                    test_union[t.test_config_id]['value'] = t.value
                                elif t.test_config.data_type == 'SELECT':
                                    test_union[t.test_config_id]['value_text'] = t.value_text
                                    test_union[t.test_config_id]['value_select'] = t.value_text
                                else:
                                    test_union[t.test_config_id]['value_text'] = t.value_text

                        FormulaTestResultFormSet.extra = max(len(test_union), 1)
                        context['test_formset'] = FormulaTestResultFormSet(prefix='test', initial=list(test_union.values()))
                        context['test_index_map'] = test_index_map

                        # 构建 variant_data (非 column 0 的百分比和测试数值)
                        variant_map = {}
                        for col_idx, f in enumerate(source_formulas):
                            if col_idx == 0:
                                continue
                            for b in f.bom_lines.all():
                                key = (b.raw_material_id, b.feeding_port)
                                if key in bom_index_map:
                                    idx = bom_index_map[key]
                                    variant_map[f'bom-{idx}-percentage_col{col_idx}'] = str(b.percentage)
                            for t in f.test_results.filter(production_order__isnull=True):
                                if t.test_config_id in test_index_map:
                                    idx = test_index_map[t.test_config_id]
                                    if t.test_config.data_type == 'NUMBER' and t.value is not None:
                                        variant_map[f'test-{idx}-value_col{col_idx}'] = str(t.value)
                                    elif t.value_text:
                                        variant_map[f'test-{idx}-value_text_col{col_idx}'] = t.value_text

                        context['variant_data'] = variant_map
                        context['enable_multi_column'] = True
                        context['num_columns'] = source_count
                        context['formula_columns'] = source_formulas
                        # 设置列标签（显示源版本号）
                        context['column_labels'] = [f'v{f.version}' for f in source_formulas]
                    else:
                        # 只有一个版本 → 单列，直接展示其 BOM
                        bom_initial = [{
                            'feeding_port': b.feeding_port, 'weighing_scale': b.weighing_scale,
                            'raw_material': b.raw_material, 'percentage': b.percentage,
                            'is_tail': b.is_tail, 'is_pre_mix': b.is_pre_mix,
                            'pre_mix_order': b.pre_mix_order, 'pre_mix_time': b.pre_mix_time,
                        } for b in source_formulas[0].bom_lines.all()]
                        context['bom_formset'] = FormulaBOMFormSet(prefix='bom', initial=bom_initial)
                        context['bom_formset'].extra = max(len(bom_initial), 1)
                        test_initial = [{'test_config': r.test_config} for r in source_formulas[0].test_results.filter(production_order__isnull=True)]
                        context['test_formset'] = FormulaTestResultFormSet(prefix='test', initial=test_initial)
                        context['test_formset'].extra = max(len(test_initial), 1)
                        context['num_columns'] = 1

                except LabFormula.DoesNotExist:
                    FormulaBOMFormSet.extra = 6
                    FormulaTestResultFormSet.extra = 9
                    context['bom_formset'] = FormulaBOMFormSet(prefix='bom', queryset=LabFormula.objects.none())
                    context['test_formset'] = FormulaTestResultFormSet(prefix='test', queryset=LabFormula.objects.none())
                    context['num_columns'] = 1
            else:
                FormulaBOMFormSet.extra = 6
                FormulaTestResultFormSet.extra = 9
                context['bom_formset'] = FormulaBOMFormSet(prefix='bom', queryset=LabFormula.objects.none())
                context['test_formset'] = FormulaTestResultFormSet(prefix='test', queryset=LabFormula.objects.none())
                context['num_columns'] = 1
        if self.request.POST:
            # 只有当没有导入多版本实验单时，才用 POST 中的 num_columns 覆盖
            if 'num_columns' not in context or context['num_columns'] == 1:
                context['num_columns'] = int(self.request.POST.get('num_columns', 1))
            if 'variant_data' not in context:
                context['variant_data'] = {k: v for k, v in self.request.POST.items() if '_col' in k}
        else:
            # 只有在没有导入数据时，才将 num_columns 重置为 1
            if 'num_columns' not in context:
                context['num_columns'] = 1
        context['next_url'] = self.request.GET.get(
            'next', self.request.META.get('HTTP_REFERER', '')
        )
        return context

    @staticmethod
    def _column_has_data(col_idx, bom_rows, test_rows, post_data):
        """检查变体列 col_idx 是否有任何非空数据"""
        for row in bom_rows:
            pct = post_data.get(f"bom-{row['form_idx']}-percentage_col{col_idx}", '').strip()
            if pct:
                return True
        for row in test_rows:
            for suffix in ('value', 'value_text', 'value_select'):
                val = post_data.get(f"test-{row['form_idx']}-{suffix}_col{col_idx}", '').strip()
                if val:
                    return True
        return False

    def _create_formula_variants(self, form, bom_formset, test_formset):
        """多列批量创建配方，返回 created_formulas 列表"""
        num_columns = int(self.request.POST.get('num_columns', 1))
        project = form.cleaned_data.get('project')
        project_node = form.cleaned_data.get('project_node')

        bom_rows = []
        for i, bom_form in enumerate(bom_formset):
            if (not bom_form.cleaned_data) or bom_form.cleaned_data.get('DELETE'):
                continue
            bom_rows.append({
                'feeding_port': bom_form.cleaned_data['feeding_port'],
                'weighing_scale': bom_form.cleaned_data['weighing_scale'],
                'raw_material': bom_form.cleaned_data['raw_material'],
                'is_tail': bom_form.cleaned_data.get('is_tail', False),
                'is_pre_mix': bom_form.cleaned_data.get('is_pre_mix', False),
                'pre_mix_order': bom_form.cleaned_data.get('pre_mix_order', 0),
                'pre_mix_time': bom_form.cleaned_data.get('pre_mix_time', 0),
                'form_idx': i,
            })

        test_rows = []
        for j, test_form in enumerate(test_formset):
            if (not test_form.cleaned_data) or test_form.cleaned_data.get('DELETE'):
                continue
            test_rows.append({
                'test_config': test_form.cleaned_data['test_config'],
                'test_date': test_form.cleaned_data.get('test_date'),
                'remark': test_form.cleaned_data.get('remark', ''),
                'form_idx': j,
            })

        post_data = self.request.POST
        created = []
        # 生成批次共享实验单号
        from django.utils import timezone
        today_str = timezone.now().strftime('%Y%m%d')
        prefix = f"L{today_str}"
        last_formula = LabFormula.objects.filter(code__startswith=prefix).order_by('code').last()
        if last_formula:
            try:
                last_seq = int(last_formula.code.split('-')[-1])
                new_seq = last_seq + 1
            except (ValueError, IndexError):
                new_seq = 1
        else:
            new_seq = 1
        shared_code = f"{prefix}-{new_seq:02d}"
        with transaction.atomic():
            versions = list(range(1, num_columns + 1))

            for col_idx in range(num_columns):
                if col_idx > 0 and not self._column_has_data(col_idx, bom_rows, test_rows, post_data):
                    break

                formula = LabFormula(
                    name=form.cleaned_data['name'],
                    material_type=form.cleaned_data['material_type'],
                    process=form.cleaned_data.get('process'),
                    project=project,
                    project_node=project_node,
                    is_mature=form.cleaned_data.get('is_mature', False),
                    description=form.cleaned_data.get('description', ''),
                    material_color_name=form.cleaned_data.get('material_color_name', ''),
                    pantone_code=form.cleaned_data.get('pantone_code', ''),
                    rgb_value=form.cleaned_data.get('rgb_value', ''),
                    creator=self.request.user,
                    version=versions[col_idx],
                    code=shared_code,
                )
                formula.save()

                for row in bom_rows:
                    if col_idx == 0:
                        percentage = bom_formset.forms[row['form_idx']].cleaned_data['percentage']
                    else:
                        pct_str = post_data.get(f"bom-{row['form_idx']}-percentage_col{col_idx}", '')
                        try:
                            percentage = Decimal(pct_str) if pct_str else Decimal('0')
                        except (InvalidOperation, ValueError):
                            percentage = Decimal('0')
                    if percentage == 0:
                        continue
                    FormulaBOM.objects.create(
                        formula=formula,
                        feeding_port=row['feeding_port'],
                        weighing_scale=row['weighing_scale'],
                        raw_material=row['raw_material'],
                        percentage=percentage,
                        is_tail=row['is_tail'],
                        is_pre_mix=row['is_pre_mix'],
                        pre_mix_order=row['pre_mix_order'],
                        pre_mix_time=row['pre_mix_time'],
                    )

                for row in test_rows:
                    test_config = row['test_config']
                    if col_idx == 0:
                        tf = test_formset.forms[row['form_idx']]
                        value = tf.cleaned_data.get('value')
                        value_text = tf.cleaned_data.get('value_text', '')
                        value_select = tf.cleaned_data.get('value_select', '')
                        if test_config.data_type == 'SELECT':
                            value_text = value_select or value_text
                    else:
                        val_str = post_data.get(f"test-{row['form_idx']}-value_col{col_idx}", '')
                        text_str = post_data.get(f"test-{row['form_idx']}-value_text_col{col_idx}", '')
                        select_str = post_data.get(f"test-{row['form_idx']}-value_select_col{col_idx}", '')
                        try:
                            value = Decimal(val_str) if val_str else None
                        except (InvalidOperation, ValueError):
                            value = None
                        if test_config.data_type == 'SELECT':
                            value_text = select_str or text_str
                        elif test_config.data_type == 'TEXT':
                            value_text = text_str
                        else:
                            value_text = ''
                    if value is not None or value_text:
                        FormulaTestResult.objects.create(
                            formula=formula,
                            test_config=test_config,
                            value=value,
                            value_text=value_text,
                            test_date=row['test_date'],
                            remark=row['remark'],
                        )

                formula.research_projects.set(form.cleaned_data.get('research_projects', []))
                formula.calculate_cost()
                created.append(formula)

        return created

    def form_invalid(self, form):
        messages.error(self.request, _build_formula_error_message(form))
        return super().form_invalid(form)

    def form_valid(self, form):
        self.request.session.pop('formula_prepare', None)
        context = self.get_context_data()
        bom_formset = context['bom_formset']
        test_formset = context['test_formset']
        if not (bom_formset.is_valid() and test_formset.is_valid()):
            messages.error(self.request, _build_formula_error_message(form, bom_formset, test_formset))
            return self.render_to_response(self.get_context_data(form=form))
        try:
            created = self._create_formula_variants(form, bom_formset, test_formset)
        except IntegrityError as e:
            messages.error(self.request, _build_integrity_error_message(e))
            return self.render_to_response(self.get_context_data(form=form))
        self.object = created[0]
        count = len(created)
        if count == 1:
            messages.success(self.request, "配方已创建")
        else:
            messages.success(self.request,
                f"已创建 {count} 个配方变体 (版本 {created[0].version} ~ {created[-1].version})")
        return redirect(self.get_success_url())

    def get_success_url(self):
        next_url = self.request.POST.get('next', '')
        if next_url:
            return next_url
        return reverse('formula_detail', kwargs={'pk': self.object.pk})


class LabFormulaUpdateView(FormulaAccessMixin, UpdateView):
    """编辑配方：需有修改权限，且仅限本部门。"""
    permission_required = 'app_formula.change_labformula'
    model = LabFormula
    form_class = LabFormulaForm
    template_name = 'apps/app_formula/form.html'

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '编辑实验配方'
        context['show_import_button'] = True
        context['search_picker'] = for_formula_import()
        context['project_node_stage'] = self.object.project_node.stage if self.object.project_node else None
        context['can_be_mature'] = self.object.project_node.can_be_mature if self.object.project_node else True
        context['project_name'] = self.object.project.name if self.object.project else None
        context['project_node_display'] = str(self.object.project_node) if self.object.project_node else None

        # 检测同 code 的兄弟配方，决定是否进入批量编辑模式
        if not self.request.POST:
            siblings = LabFormula.objects.filter(code=self.object.code).prefetch_related(
                'bom_lines__raw_material__category',
                'test_results__test_config__category',
            ).order_by('version')
            if siblings.count() > 1:
                all_formulas = list(siblings)
                context['enable_multi_column'] = True
                context['batch_edit_mode'] = True
                context['num_columns'] = len(all_formulas)
                context['formula_columns'] = all_formulas

                # 构建 BOM 并集 (按 raw_material_id + feeding_port 去重)
                from collections import OrderedDict
                bom_union = OrderedDict()
                bom_index_map = {}
                for f in all_formulas:
                    for b in f.bom_lines.all():
                        key = (b.raw_material_id, b.feeding_port)
                        if key not in bom_union:
                            bom_index_map[key] = len(bom_union)
                            bom_union[key] = {
                                'feeding_port': b.feeding_port,
                                'weighing_scale': b.weighing_scale,
                                'raw_material': b.raw_material,
                                'is_tail': b.is_tail,
                                'is_pre_mix': b.is_pre_mix,
                                'pre_mix_order': b.pre_mix_order,
                                'pre_mix_time': b.pre_mix_time,
                                'percentage': Decimal('0'),
                            }

                # column 0 用主配方的实际 percentage
                primary = all_formulas[0]
                for b in primary.bom_lines.all():
                    key = (b.raw_material_id, b.feeding_port)
                    if key in bom_union:
                        bom_union[key]['percentage'] = b.percentage

                FormulaBOMFormSet.extra = max(len(bom_union), 1)
                context['bom_formset'] = FormulaBOMFormSet(prefix='bom', initial=list(bom_union.values()))
                context['bom_index_map'] = bom_index_map

                # 构建测试并集 (按 test_config_id 去重)
                test_union = OrderedDict()
                test_index_map = {}
                for f in all_formulas:
                    for t in f.test_results.filter(production_order__isnull=True):
                        if t.test_config_id not in test_union:
                            test_index_map[t.test_config_id] = len(test_union)
                            test_union[t.test_config_id] = {
                                'test_config': t.test_config,
                                'test_date': t.test_date,
                                'remark': t.remark,
                            }

                # column 0 用主配方的实际测试值
                for t in primary.test_results.filter(production_order__isnull=True):
                    if t.test_config_id in test_union:
                        if t.test_config.data_type == 'NUMBER':
                            test_union[t.test_config_id]['value'] = t.value
                        elif t.test_config.data_type == 'SELECT':
                            test_union[t.test_config_id]['value_text'] = t.value_text
                            test_union[t.test_config_id]['value_select'] = t.value_text
                        else:
                            test_union[t.test_config_id]['value_text'] = t.value_text

                FormulaTestResultFormSet.extra = max(len(test_union), 1)
                context['test_formset'] = FormulaTestResultFormSet(prefix='test', initial=list(test_union.values()))
                context['test_index_map'] = test_index_map

                # 构建 variant_data (非 column 0 的百分比和测试数值)
                variant_map = {}
                for col_idx, f in enumerate(all_formulas):
                    if col_idx == 0:
                        continue
                    for b in f.bom_lines.all():
                        key = (b.raw_material_id, b.feeding_port)
                        if key in bom_index_map:
                            idx = bom_index_map[key]
                            variant_map[f"bom-{idx}-percentage_col{col_idx}"] = str(b.percentage)
                    for t in f.test_results.filter(production_order__isnull=True):
                        if t.test_config_id in test_index_map:
                            idx = test_index_map[t.test_config_id]
                            if t.test_config.data_type == 'NUMBER' and t.value is not None:
                                variant_map[f"test-{idx}-value_col{col_idx}"] = str(t.value)
                            elif t.value_text:
                                variant_map[f"test-{idx}-value_text_col{col_idx}"] = t.value_text

                context['variant_data'] = variant_map
            else:
                context['enable_multi_column'] = False
                context['num_columns'] = 1
                FormulaBOMFormSet.extra = 1
                FormulaTestResultFormSet.extra = 1
                context['bom_formset'] = FormulaBOMFormSet(instance=self.object, prefix='bom')
                context['test_formset'] = FormulaTestResultFormSet(instance=self.object, prefix='test')
        else:
            # POST 请求
            formula_ids = self.request.POST.getlist('formula_ids')
            if formula_ids:
                context['enable_multi_column'] = True
                context['batch_edit_mode'] = True
                context['num_columns'] = len(formula_ids)
                context['bom_formset'] = FormulaBOMFormSet(self.request.POST, prefix='bom')
                context['test_formset'] = FormulaTestResultFormSet(self.request.POST, prefix='test')
                context['variant_data'] = {k: v for k, v in self.request.POST.items() if '_col' in k}
                context['formula_columns'] = LabFormula.objects.filter(
                    pk__in=formula_ids
                ).order_by('version')
            else:
                context['enable_multi_column'] = False
                context['num_columns'] = 1
                context['bom_formset'] = FormulaBOMFormSet(self.request.POST, instance=self.object, prefix='bom')
                context['test_formset'] = FormulaTestResultFormSet(self.request.POST, instance=self.object, prefix='test')

        context['next_url'] = self.request.GET.get(
            'next', self.request.META.get('HTTP_REFERER', '')
        )
        return context

    def _update_formula_variants(self, form, bom_formset, test_formset):
        """批量更新：共享字段来自 column 0，variant 数据来自各列"""
        formula_ids = [int(x) for x in self.request.POST.getlist('formula_ids')]
        post_data = self.request.POST

        bom_rows = []
        for i, bf in enumerate(bom_formset):
            if (not bf.cleaned_data) or bf.cleaned_data.get('DELETE'):
                continue
            bom_rows.append({
                'feeding_port': bf.cleaned_data['feeding_port'],
                'weighing_scale': bf.cleaned_data['weighing_scale'],
                'raw_material': bf.cleaned_data['raw_material'],
                'is_tail': bf.cleaned_data.get('is_tail', False),
                'is_pre_mix': bf.cleaned_data.get('is_pre_mix', False),
                'pre_mix_order': bf.cleaned_data.get('pre_mix_order', 0),
                'pre_mix_time': bf.cleaned_data.get('pre_mix_time', 0),
                'form_idx': i,
            })

        test_rows = []
        for j, tf in enumerate(test_formset):
            if (not tf.cleaned_data) or tf.cleaned_data.get('DELETE'):
                continue
            test_rows.append({
                'test_config': tf.cleaned_data['test_config'],
                'test_date': tf.cleaned_data.get('test_date'),
                'remark': tf.cleaned_data.get('remark', ''),
                'form_idx': j,
            })

        updated = []
        formula_map = {
            f.pk: f for f in LabFormula.objects.filter(pk__in=formula_ids).prefetch_related('test_results', 'bom_lines')
        }
        with transaction.atomic():
            for col_idx, formula_id in enumerate(formula_ids):
                formula = formula_map[formula_id]

                formula.name = form.cleaned_data['name']
                formula.material_type = form.cleaned_data['material_type']
                formula.process = form.cleaned_data.get('process')
                formula.is_mature = form.cleaned_data.get('is_mature', False)
                formula.description = form.cleaned_data.get('description', '')
                formula.material_color_name = form.cleaned_data.get('material_color_name', '')
                formula.pantone_code = form.cleaned_data.get('pantone_code', '')
                formula.rgb_value = form.cleaned_data.get('rgb_value', '')
                formula.save()

                # 从 Attachment 表获取旧测试报告
                from django.contrib.contenttypes.models import ContentType
                from app_attachment.models import Attachment
                ct = ContentType.objects.get_for_model(FormulaTestResult)
                old_reports = {}
                for t in formula.test_results.filter(production_order__isnull=True):
                    att = Attachment.objects.filter(
                        content_type=ct, object_id=t.pk,
                        category='REPORT', is_deleted=False,
                    ).first()
                    if att:
                        old_reports[t.test_config_id] = att.file
                formula.bom_lines.all().delete()
                formula.test_results.filter(production_order__isnull=True).delete()

                for row in bom_rows:
                    if col_idx == 0:
                        pct = bom_formset.forms[row['form_idx']].cleaned_data['percentage']
                    else:
                        pct_str = post_data.get(f"bom-{row['form_idx']}-percentage_col{col_idx}", '')
                        try:
                            pct = Decimal(pct_str) if pct_str else Decimal('0')
                        except InvalidOperation:
                            pct = Decimal('0')
                    if pct == 0:
                        continue
                    FormulaBOM.objects.create(
                        formula=formula,
                        feeding_port=row['feeding_port'],
                        weighing_scale=row['weighing_scale'],
                        raw_material=row['raw_material'],
                        percentage=pct,
                        is_tail=row['is_tail'],
                        is_pre_mix=row['is_pre_mix'],
                        pre_mix_order=row['pre_mix_order'],
                        pre_mix_time=row['pre_mix_time'],
                    )

                for row in test_rows:
                    tc = row['test_config']
                    if col_idx == 0:
                        tf = test_formset.forms[row['form_idx']]
                        value = tf.cleaned_data.get('value')
                        value_text = tf.cleaned_data.get('value_text', '')
                        value_select = tf.cleaned_data.get('value_select', '')
                        if tc.data_type == 'SELECT':
                            value_text = value_select or value_text
                    else:
                        val_str = post_data.get(f"test-{row['form_idx']}-value_col{col_idx}", '')
                        text_str = post_data.get(f"test-{row['form_idx']}-value_text_col{col_idx}", '')
                        select_str = post_data.get(f"test-{row['form_idx']}-value_select_col{col_idx}", '')
                        try:
                            value = Decimal(val_str) if val_str else None
                        except InvalidOperation:
                            value = None
                        if tc.data_type == 'SELECT':
                            value_text = select_str or text_str
                        elif tc.data_type == 'TEXT':
                            value_text = text_str
                        else:
                            value_text = ''
                    if value is not None or value_text:
                        new_result = FormulaTestResult.objects.create(
                            formula=formula,
                            test_config=tc,
                            value=value,
                            value_text=value_text,
                            test_date=row['test_date'],
                            remark=row['remark'],
                        )
                        # 复制旧的测试报告附件到新记录
                        if tc.pk in old_reports:
                            Attachment.objects.create(
                                content_type=ct, object_id=new_result.pk,
                                category='REPORT', file=old_reports[tc.pk],
                                display_name=f'测试报告_{new_result.pk}',
                            )

                formula.research_projects.set(form.cleaned_data.get('research_projects', []))
                formula.calculate_cost()
                updated.append(formula)

        return updated

    def form_invalid(self, form):
        messages.error(self.request, _build_formula_error_message(form))
        return super().form_invalid(form)

    def form_valid(self, form):
        context = self.get_context_data()
        bom_formset = context['bom_formset']
        test_formset = context['test_formset']
        if not (bom_formset.is_valid() and test_formset.is_valid()):
            messages.error(self.request, _build_formula_error_message(form, bom_formset, test_formset))
            return self.render_to_response(self.get_context_data(form=form))

        try:
            if context.get('batch_edit_mode'):
                updated = self._update_formula_variants(form, bom_formset, test_formset)
                self.object = updated[0]
                messages.success(self.request, f"已更新 {len(updated)} 个配方")
            else:
                with transaction.atomic():
                    self.object = form.save()
                    bom_formset.save()
                    test_formset.save()
                    self.object.calculate_cost()
                messages.success(self.request, "配方已更新")
        except IntegrityError as e:
            messages.error(self.request, _build_integrity_error_message(e))
            return self.render_to_response(self.get_context_data(form=form))

        return redirect(self.get_success_url())

    def get_success_url(self):
        next_url = self.request.POST.get('next', '')
        if next_url:
            return next_url
        return reverse('formula_detail', kwargs={'pk': self.object.pk})


class LabFormulaDuplicateView(FormulaAccessMixin, UpdateView):
    """
    复制配方：
    - 逻辑：基于现有配方内容创建一个新对象。
    - 权限：需具备 add 权限，且基于原部门配方进行复制。
    """
    permission_required = 'app_formula.add_labformula'
    model = LabFormula
    form_class = LabFormulaForm
    template_name = 'apps/app_formula/form.html'

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    # 重新实现为 CreateView 逻辑
    @property
    def original_formula(self):
        """鉴权后懒加载原配方对象"""
        if not hasattr(self, '_original_formula'):
            self._original_formula = self.get_object()
        return self._original_formula

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '复制配方'
        context['enable_multi_column'] = True
        context['project_node_stage'] = self.original_formula.project_node.stage if self.original_formula.project_node else None
        context['can_be_mature'] = self.original_formula.project_node.can_be_mature if self.original_formula.project_node else True
        context['project_name'] = self.original_formula.project.name if self.original_formula.project else None
        context['project_node_display'] = str(self.original_formula.project_node) if self.original_formula.project_node else None

        # 如果是 GET 请求，预填充 FormSet 数据
        if not self.request.POST:
            bom_initial = [{
                'feeding_port': bom.feeding_port, 'weighing_scale': bom.weighing_scale,
                'raw_material': bom.raw_material, 'percentage': bom.percentage,
                'is_tail': bom.is_tail, 'is_pre_mix': bom.is_pre_mix,
                'pre_mix_order': bom.pre_mix_order, 'pre_mix_time': bom.pre_mix_time,
            } for bom in self.original_formula.bom_lines.all()]
            context['bom_formset'] = FormulaBOMFormSet(prefix='bom', initial=bom_initial)
            # 关键：设置 extra 为列表长度，以显示所有初始数据
            context['bom_formset'].extra = len(bom_initial)
            
            test_initial = [{
                'test_config': res.test_config, 'value': res.value,
                'test_date': res.test_date, 'remark': res.remark,
            } for res in self.original_formula.test_results.filter(production_order__isnull=True)]
            context['test_formset'] = FormulaTestResultFormSet(prefix='test', initial=test_initial)
            context['test_formset'].extra = len(test_initial)
        else:
            context['bom_formset'] = FormulaBOMFormSet(self.request.POST, prefix='bom')
            context['test_formset'] = FormulaTestResultFormSet(self.request.POST, prefix='test')
        if self.request.POST:
            context['num_columns'] = int(self.request.POST.get('num_columns', 1))
            context['variant_data'] = {k: v for k, v in self.request.POST.items() if '_col' in k}
        else:
            context['num_columns'] = 1
        context['next_url'] = self.request.GET.get(
            'next', self.request.META.get('HTTP_REFERER', '')
        )
        return context

    def get_initial(self):
        initial = super().get_initial()
        initial.update({
            'name': f"{self.original_formula.name} (副本)",
            'material_type': self.original_formula.material_type,
            'process': self.original_formula.process,
            'description': self.original_formula.description,
            'material_color_name': self.original_formula.material_color_name,
            'pantone_code': self.original_formula.pantone_code,
            'rgb_value': self.original_formula.rgb_value,
            'research_projects': self.original_formula.research_projects.all(),
            'is_mature': False,
        })
        return initial

    @staticmethod
    def _column_has_data(col_idx, bom_rows, test_rows, post_data):
        """检查变体列 col_idx 是否有任何非空数据"""
        for row in bom_rows:
            pct = post_data.get(f"bom-{row['form_idx']}-percentage_col{col_idx}", '').strip()
            if pct:
                return True
        for row in test_rows:
            for suffix in ('value', 'value_text', 'value_select'):
                val = post_data.get(f"test-{row['form_idx']}-{suffix}_col{col_idx}", '').strip()
                if val:
                    return True
        return False

    def _create_formula_variants(self, form, bom_formset, test_formset):
        """多列批量创建配方，返回 created_formulas 列表"""
        num_columns = int(self.request.POST.get('num_columns', 1))
        project = form.cleaned_data.get('project')
        project_node = form.cleaned_data.get('project_node')

        bom_rows = []
        for i, bom_form in enumerate(bom_formset):
            if (not bom_form.cleaned_data) or bom_form.cleaned_data.get('DELETE'):
                continue
            bom_rows.append({
                'feeding_port': bom_form.cleaned_data['feeding_port'],
                'weighing_scale': bom_form.cleaned_data['weighing_scale'],
                'raw_material': bom_form.cleaned_data['raw_material'],
                'is_tail': bom_form.cleaned_data.get('is_tail', False),
                'is_pre_mix': bom_form.cleaned_data.get('is_pre_mix', False),
                'pre_mix_order': bom_form.cleaned_data.get('pre_mix_order', 0),
                'pre_mix_time': bom_form.cleaned_data.get('pre_mix_time', 0),
                'form_idx': i,
            })

        test_rows = []
        for j, test_form in enumerate(test_formset):
            if (not test_form.cleaned_data) or test_form.cleaned_data.get('DELETE'):
                continue
            test_rows.append({
                'test_config': test_form.cleaned_data['test_config'],
                'test_date': test_form.cleaned_data.get('test_date'),
                'remark': test_form.cleaned_data.get('remark', ''),
                'form_idx': j,
            })

        post_data = self.request.POST
        created = []
        # 生成批次共享实验单号
        from django.utils import timezone
        today_str = timezone.now().strftime('%Y%m%d')
        prefix = f"L{today_str}"
        last_formula = LabFormula.objects.filter(code__startswith=prefix).order_by('code').last()
        if last_formula:
            try:
                last_seq = int(last_formula.code.split('-')[-1])
                new_seq = last_seq + 1
            except (ValueError, IndexError):
                new_seq = 1
        else:
            new_seq = 1
        shared_code = f"{prefix}-{new_seq:02d}"
        with transaction.atomic():
            versions = list(range(1, num_columns + 1))

            for col_idx in range(num_columns):
                if col_idx > 0 and not self._column_has_data(col_idx, bom_rows, test_rows, post_data):
                    break

                formula = LabFormula(
                    name=form.cleaned_data['name'],
                    material_type=form.cleaned_data['material_type'],
                    process=form.cleaned_data.get('process'),
                    project=project,
                    project_node=project_node,
                    is_mature=form.cleaned_data.get('is_mature', False),
                    description=form.cleaned_data.get('description', ''),
                    material_color_name=form.cleaned_data.get('material_color_name', ''),
                    pantone_code=form.cleaned_data.get('pantone_code', ''),
                    rgb_value=form.cleaned_data.get('rgb_value', ''),
                    creator=self.request.user,
                    version=versions[col_idx],
                    code=shared_code,
                )
                formula.save()

                for row in bom_rows:
                    if col_idx == 0:
                        percentage = bom_formset.forms[row['form_idx']].cleaned_data['percentage']
                    else:
                        pct_str = post_data.get(f"bom-{row['form_idx']}-percentage_col{col_idx}", '')
                        try:
                            percentage = Decimal(pct_str) if pct_str else Decimal('0')
                        except (InvalidOperation, ValueError):
                            percentage = Decimal('0')
                    if percentage == 0:
                        continue
                    FormulaBOM.objects.create(
                        formula=formula,
                        feeding_port=row['feeding_port'],
                        weighing_scale=row['weighing_scale'],
                        raw_material=row['raw_material'],
                        percentage=percentage,
                        is_tail=row['is_tail'],
                        is_pre_mix=row['is_pre_mix'],
                        pre_mix_order=row['pre_mix_order'],
                        pre_mix_time=row['pre_mix_time'],
                    )

                for row in test_rows:
                    test_config = row['test_config']
                    if col_idx == 0:
                        tf = test_formset.forms[row['form_idx']]
                        value = tf.cleaned_data.get('value')
                        value_text = tf.cleaned_data.get('value_text', '')
                        value_select = tf.cleaned_data.get('value_select', '')
                        if test_config.data_type == 'SELECT':
                            value_text = value_select or value_text
                    else:
                        val_str = post_data.get(f"test-{row['form_idx']}-value_col{col_idx}", '')
                        text_str = post_data.get(f"test-{row['form_idx']}-value_text_col{col_idx}", '')
                        select_str = post_data.get(f"test-{row['form_idx']}-value_select_col{col_idx}", '')
                        try:
                            value = Decimal(val_str) if val_str else None
                        except (InvalidOperation, ValueError):
                            value = None
                        if test_config.data_type == 'SELECT':
                            value_text = select_str or text_str
                        elif test_config.data_type == 'TEXT':
                            value_text = text_str
                        else:
                            value_text = ''
                    if value is not None or value_text:
                        FormulaTestResult.objects.create(
                            formula=formula,
                            test_config=test_config,
                            value=value,
                            value_text=value_text,
                            test_date=row['test_date'],
                            remark=row['remark'],
                        )

                formula.research_projects.set(form.cleaned_data.get('research_projects', []))
                formula.calculate_cost()
                created.append(formula)

        return created

    def form_invalid(self, form):
        messages.error(self.request, _build_formula_error_message(form))
        return super().form_invalid(form)

    def form_valid(self, form):
        context = self.get_context_data()
        bom_formset = context['bom_formset']
        test_formset = context['test_formset']
        if not (bom_formset.is_valid() and test_formset.is_valid()):
            messages.error(self.request, _build_formula_error_message(form, bom_formset, test_formset))
            return self.render_to_response(self.get_context_data(form=form))
        form.instance.pk = None
        form.instance.code = None
        try:
            created = self._create_formula_variants(form, bom_formset, test_formset)
        except IntegrityError as e:
            messages.error(self.request, _build_integrity_error_message(e))
            return self.render_to_response(self.get_context_data(form=form))
        self.object = created[0]
        count = len(created)
        if count == 1:
            messages.success(self.request, "配方已复制并创建")
        else:
            messages.success(self.request,
                f"已创建 {count} 个配方变体 (版本 {created[0].version} ~ {created[-1].version})")
        return redirect(self.get_success_url())

    def get_success_url(self):
        next_url = self.request.POST.get('next', '')
        if next_url:
            return next_url
        return reverse('formula_detail', kwargs={'pk': self.object.pk})


class FormulaImportFromView(FormulaAccessMixin, View):
    """从指定实验单导入（合并所有版本）到目标实验单的所有配方版本：基础信息 + BOM 明细(合并去重) + 测试项目(仅配置，不含结果)；关联信息/测试结果不导入"""
    permission_required = 'app_formula.change_labformula'

    def post(self, request, pk):
        target = get_object_or_404(LabFormula, pk=pk)
        self.check_object_permission(target)

        experiment_code = request.POST.get('experiment_code')
        if not experiment_code:
            messages.error(request, '请选择要导入的实验单')
            return redirect(reverse('formula_edit', kwargs={'pk': pk}))

        # 源：被选中的实验单下所有版本
        source_formulas = list(LabFormula.objects.filter(code=experiment_code).prefetch_related('bom_lines', 'test_results'))
        if not source_formulas:
            messages.error(request, f'实验单「{experiment_code}」不存在')
            return redirect(reverse('formula_edit', kwargs={'pk': pk}))
        for f in source_formulas:
            self.check_object_permission(f)

        # 目标：与当前编辑配方同 code 的所有版本（批量编辑模式下的兄弟配方）
        targets = list(LabFormula.objects.filter(code=target.code).order_by('version'))
        for t in targets:
            self.check_object_permission(t)

        # 取源实验单中版本号最大的配方作为基础信息模板
        source = max(source_formulas, key=lambda f: f.version)

        # BOM 明细合并去重（所有源版本合并，按 key 去重，percentage 取均值）
        bom_merged = {}  # key: (feeding_port, weighing_scale, raw_material_id)
        for f in source_formulas:
            for bom in f.bom_lines.all():
                key = (bom.feeding_port, bom.weighing_scale, bom.raw_material_id)
                if key in bom_merged:
                    existing = bom_merged[key]
                    existing['percentage_sum'] += bom.percentage
                    existing['count'] += 1
                else:
                    bom_merged[key] = {
                        'feeding_port': bom.feeding_port,
                        'weighing_scale': bom.weighing_scale,
                        'raw_material': bom.raw_material,
                        'percentage_sum': bom.percentage,
                        'count': 1,
                        'is_tail': bom.is_tail,
                        'is_pre_mix': bom.is_pre_mix,
                        'pre_mix_order': bom.pre_mix_order,
                        'pre_mix_time': bom.pre_mix_time,
                    }

        # 测试项目合并去重（所有源版本按 test_config 去重）
        seen_test_configs = set()
        test_configs = []
        for f in source_formulas:
            for test in f.test_results.filter(production_order__isnull=True):
                if test.test_config_id not in seen_test_configs:
                    seen_test_configs.add(test.test_config_id)
                    test_configs.append(test.test_config)

        total_bom = 0
        total_tests = 0
        target_count = 0

        with transaction.atomic():
            for target_formula in targets:
                # 基础信息全量导入（不含关联信息，取源最新版本）
                target_formula.name = source.name
                target_formula.material_type = source.material_type
                target_formula.process = source.process
                target_formula.description = source.description
                target_formula.material_color_name = source.material_color_name
                target_formula.pantone_code = source.pantone_code
                target_formula.rgb_value = source.rgb_value
                target_formula.save(update_fields=[
                    'name', 'material_type', 'process', 'description',
                    'material_color_name', 'pantone_code', 'rgb_value',
                ])

                # 清除旧 BOM 和旧测试项目（手动录入部分），再导入新数据
                target_formula.bom_lines.all().delete()
                target_formula.test_results.filter(production_order__isnull=True).delete()

                for data in bom_merged.values():
                    avg_pct = data['percentage_sum'] / data['count']
                    FormulaBOM.objects.create(
                        formula=target_formula,
                        feeding_port=data['feeding_port'],
                        weighing_scale=data['weighing_scale'],
                        raw_material=data['raw_material'],
                        percentage=avg_pct,
                        is_tail=data['is_tail'],
                        is_pre_mix=data['is_pre_mix'],
                        pre_mix_order=data['pre_mix_order'],
                        pre_mix_time=data['pre_mix_time'],
                    )

                for tc in test_configs:
                    FormulaTestResult.objects.create(
                        formula=target_formula,
                        test_config=tc,
                    )

                target_formula.calculate_cost()
                total_bom += len(bom_merged)
                total_tests += len(test_configs)
                target_count += 1

        source_version_count = len(source_formulas)
        messages.success(
            request,
            f'已从实验单「{experiment_code}」（{source_version_count}个版本）'
            f'导入到 {target_count} 个目标配方（{target.code}），'
            f'共 {len(bom_merged)} 项 BOM（去重后）、{len(test_configs)} 个测试项目'
        )
        return redirect(reverse('formula_edit', kwargs={'pk': pk}))
