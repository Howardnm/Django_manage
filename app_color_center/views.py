import logging
from collections import OrderedDict
from itertools import groupby
from django.db.models import Count, Q
from django.views.generic import ListView, View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from app_color_center.mixins import ColorCenterAccessMixin
from app_trial_production.mixins import RndAccessMixin
from app_trial_production.models import ProductionOrder
from app_color_center.models import ColorMatchingTask
from app_project.models import Project, ProjectStage
from app_formula.models import LabFormula, ColorPowderBOM
from app_color_center.forms import ColorPowderBOMForm, ColorPowderBOMEntryFormSet
from app_color_center.services import ColorMatchingTaskService, check_order_bom_complete, batch_copy_bom
from common_utils.state_machine import InvalidStateTransition

logger = logging.getLogger(__name__)


class TaskListView(ColorCenterAccessMixin, ListView):
    """配色任务列表 — 按排产工单展示配色任务状态"""
    model = ProductionOrder
    template_name = 'apps/app_color_center/task_list.html'
    context_object_name = 'orders'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        if qs is None:
            qs = self.model.objects.all()
        qs = qs.filter(
            formula_details__needs_color_matching=True,
            status__in=[ProductionOrder.Status.EXTRUDING,
                        ProductionOrder.Status.INJECTION_MOLDING,
                        ProductionOrder.Status.TESTING],
        ).select_related('project', 'creator').distinct()
        from app_color_center.filters import ColorTaskFilter
        self.filter = ColorTaskFilter(self.request.GET, queryset=qs)
        qs = self.filter.qs
        if not self.request.GET.get('sort'):
            qs = qs.order_by('-created_at')
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filter
        context['current_sort'] = self.request.GET.get('sort', '')
        # 预计算当前页工单的配色完成进度 + 跳转参数
        context['order_stats'], context['order_redirect_params'] = \
            self._compute_order_stats(context['page_obj'])
        return context

    @staticmethod
    def _compute_order_stats(page_obj):
        order_stats = {}
        order_redirect_params = {}
        for o in page_obj:
            total = 0
            done = 0
            first_formula_id = None
            first_formula_node = None
            for fd in o.formula_details.filter(needs_color_matching=True):
                total += 1
                formula = LabFormula.objects.filter(
                    pk=fd.formula_id).select_related('project_node').first()
                bom = getattr(formula, 'color_powder_bom', None)
                if bom and bom.entries.exists():
                    done += 1
                elif first_formula_id is None and formula:
                    first_formula_id = formula.pk
                    first_formula_node = formula.project_node
            order_stats[o.pk] = {'total': total, 'done': done}
            if first_formula_id and first_formula_node:
                order_redirect_params[o.pk] = (
                    f"stage={first_formula_node.stage}"
                    f"&round={first_formula_node.round}"
                    f"&formula_id={first_formula_id}"
                )
            else:
                order_redirect_params[o.pk] = ''
        return order_stats, order_redirect_params


class ProjectListPageView(ColorCenterAccessMixin, ListView):
    """配色项目列表 — 按项目维度聚合"""
    model = Project
    template_name = 'apps/app_color_center/project_list.html'
    context_object_name = 'projects'
    paginate_by = 10

    def get_queryset(self):
        project_ids = ProductionOrder.objects.filter(
            formula_details__needs_color_matching=True,
            status__in=[ProductionOrder.Status.EXTRUDING,
                        ProductionOrder.Status.INJECTION_MOLDING,
                        ProductionOrder.Status.TESTING],
            project__isnull=False,
        ).values_list('project_id', flat=True).distinct()
        qs = Project.objects.filter(
            pk__in=project_ids,
        ).select_related('manager', 'material')
        from app_color_center.filters import ColorProjectFilter
        self.filter = ColorProjectFilter(self.request.GET, queryset=qs)
        qs = self.filter.qs.order_by('-created_at')
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filter
        context['current_sort'] = self.request.GET.get('sort', '')
        context['project_stats'] = self._compute_project_stats(context['page_obj'])
        return context

    @staticmethod
    def _compute_project_stats(page_obj):
        project_stats = {}
        for p in page_obj:
            orders = ProductionOrder.objects.filter(
                project=p,
                formula_details__needs_color_matching=True,
            ).distinct()
            total = 0
            done = 0
            for o in orders:
                for fd in o.formula_details.filter(needs_color_matching=True):
                    total += 1
                    bom = getattr(
                        LabFormula.objects.filter(pk=fd.formula_id).first(),
                        'color_powder_bom', None,
                    )
                    if bom and bom.entries.exists():
                        done += 1
            project_stats[p.pk] = {'total': total, 'done': done}
        return project_stats


class ColorTaskDetailView(ColorCenterAccessMixin, View):
    """配色任务详情"""

    def get(self, request, order_pk):
        order = get_object_or_404(
            ProductionOrder.objects.select_related('project'),
            pk=order_pk)
        if order.project:
            RndAccessMixin.check_project_ownership(order.project, request.user)
        task = getattr(order, 'color_task', None)
        return render(request, 'apps/app_color_center/detail.html', {
            'production_order': order,
            'color_task': task,
        })


class ProjectColorView(ColorCenterAccessMixin, View):
    """项目配色页 — 含配方侧边栏 + BOM 填写 + 对比模式"""
    template_name = 'apps/app_color_center/fill.html'
    STAGE_ORDER = ['RND', 'PILOT', 'MID_TEST', 'MASS_PROD']

    def _resolve_project(self):
        if not hasattr(self, '_project'):
            self._project = get_object_or_404(
                Project.objects.select_related('material'),
                pk=self.kwargs['project_pk'])
            RndAccessMixin.check_project_ownership(
                self._project, self.request.user)
        return self._project

    def _fetch_formulas(self, project, material):
        project_formulas = LabFormula.objects.filter(
            project=project, project_node__isnull=False,
        ).select_related(
            'project_node', 'material_type', 'creator', 'process', 'project',
        ).prefetch_related(
            'bom_lines__raw_material__category',
            'test_results__test_config__category',
            'color_powder_bom',
        ).order_by('version')

        material_formulas = LabFormula.objects.none()
        if material:
            material_formulas = LabFormula.objects.filter(
                project__material=material, project_node__isnull=False,
            ).exclude(
                pk__in=project_formulas.values_list('pk', flat=True),
            ).select_related(
                'project', 'project_node', 'material_type', 'creator', 'process',
            ).prefetch_related(
                'bom_lines__raw_material__category',
                'test_results__test_config__category',
                'color_powder_bom',
            ).order_by('version')

        return sorted(
            list(project_formulas) + list(material_formulas),
            key=lambda f: (f.version if f.version else 1),
        )

    def _build_color_powder_bom_matrix(self, formulas):
        if not formulas:
            return [], []
        formulas = sorted(formulas, key=lambda f: f.created_at)
        columns = [{'type': 'formula', 'obj': f} for f in formulas]
        all_raw_materials = set()
        cpbom_map = {}
        for f in formulas:
            cpbom_map[f.id] = {}
            bom = getattr(f, 'color_powder_bom', None)
            if bom:
                for entry in bom.entries.select_related('raw_material__category'):
                    all_raw_materials.add(entry.raw_material)
                    cpbom_map[f.id][entry.raw_material_id] = entry
        sorted_raw_materials = sorted(all_raw_materials, key=lambda x: (x.category.order, x.name))
        cpbom_matrix = []
        for rm in sorted_raw_materials:
            row = {'item': rm, 'values': []}
            for col in columns:
                entry = cpbom_map.get(col['obj'].id, {}).get(rm.id)
                if entry:
                    row['values'].append({
                        'percentage': entry.percentage,
                        'feeding_port': entry.get_feeding_port_display(),
                        'is_pre_mix': entry.is_pre_mix,
                        'pre_mix_order': entry.pre_mix_order,
                        'pre_mix_time': entry.pre_mix_time,
                        'weighing_scale': entry.get_weighing_scale_display(),
                        'is_empty': False,
                    })
                else:
                    row['values'].append({'is_empty': True})
            cpbom_matrix.append(row)
        return columns, cpbom_matrix

    def _build_stage_groups(self, all_formulas):
        """按阶段/轮次分组，返回 (stage_round_items, all_stage_formulas)"""
        stage_grouped = OrderedDict()
        all_stage_formulas = []
        for f in all_formulas:
            if not f.project_node:
                continue
            all_stage_formulas.append(f)
            s = f.project_node.stage
            if s not in stage_grouped:
                stage_grouped[s] = OrderedDict()
            r = f.project_node.round
            if r not in stage_grouped[s]:
                stage_grouped[s][r] = []
            stage_grouped[s][r].append(f)

        stage_round_items = []
        for stage in self.STAGE_ORDER:
            if stage not in stage_grouped:
                continue
            for r in sorted(stage_grouped[stage].keys()):
                stage_round_items.append({
                    'stage': stage,
                    'stage_display': dict(ProjectStage.choices)[stage],
                    'round': r,
                    'formulas': stage_grouped[stage][r],
                })
        return stage_round_items, all_stage_formulas

    def _resolve_active_formulas(self, request, stage_round_items):
        """根据 GET 参数定位当前活跃阶段/轮次，返回 (active_stage, active_round, active_formulas)"""
        active_stage = request.GET.get('stage', self.STAGE_ORDER[0])
        try:
            active_round = int(request.GET.get('round')) if request.GET.get('round') else None
        except (ValueError, TypeError):
            active_round = None

        active_item = None
        for item in stage_round_items:
            if item['stage'] == active_stage and (active_round is None or item['round'] == active_round):
                active_item = item
                break
        if active_item is None and stage_round_items:
            active_item = stage_round_items[0]

        if active_item:
            return active_item['stage'], active_item['round'], active_item['formulas']
        return active_stage, active_round, []

    def _build_formula_groups(self, active_formulas, selected_formula):
        """按 code 聚合配方组，并展开选中配方所在组。返回 formula_groups 列表"""
        active_formulas_sorted = sorted(active_formulas, key=lambda f: (f.code or '', f.version))
        formula_groups = []
        for code, items in groupby(active_formulas_sorted, key=lambda f: f.code):
            group_list = list(items)
            is_collapsed = len(group_list) > 1
            formula_groups.append({'code': code, 'formulas': group_list, 'is_collapsed': is_collapsed})

        if selected_formula:
            for g in formula_groups:
                if any(f.pk == selected_formula.pk for f in g['formulas']):
                    g['is_collapsed'] = False
                    break
        return formula_groups

    def _build_base_context(self):
        """构建 GET/POST 共享的基础上下文"""
        project = self._resolve_project()
        material = project.material if project else None
        all_formulas = self._fetch_formulas(project, material)
        stage_round_items, all_stage_formulas = self._build_stage_groups(all_formulas)

        # 预计算哪些配方需要配色（关联的工单有 needs_color_matching=True）
        from app_trial_production.models import ProductionOrderFormulaDetail
        # 仅允许那些关联工单已下发配色任务（ColorMatchingTask 已创建）的配方
        color_formula_ids = set(
            ProductionOrderFormulaDetail.objects.filter(
                formula__project=project,
                needs_color_matching=True,
                production_order__color_task__isnull=False,
            ).values_list('formula_id', flat=True).distinct()
        )

        # 可选：通过 ?order_pk= 传入工单上下文（从工单详情跳转时定位对应实验单号）
        order = None
        order_pk = self.request.GET.get('order_pk')
        if order_pk:
            try:
                order = ProductionOrder.objects.select_related('project').get(
                    pk=order_pk, project=project)
            except ProductionOrder.DoesNotExist:
                pass

        return {
            'production_order': order,
            'project': project,
            'material': material,
            'stage_round_items': stage_round_items,
            'all_stage_formulas': all_stage_formulas,
            'all_formulas': all_formulas,
            'color_formula_ids': color_formula_ids,
        }

    def get(self, request, *args, **kwargs):
        ctx = self._build_base_context()
        stage_round_items = ctx['stage_round_items']
        all_stage_formulas = ctx['all_stage_formulas']

        active_stage, active_round, active_formulas = self._resolve_active_formulas(
            request, stage_round_items)

        # 选中配方
        compare_mode = request.GET.get('compare') == '1'
        global_compare = compare_mode and not request.GET.get('stage')
        selected_formula = None
        selected_formula_id = request.GET.get('formula_id')
        if selected_formula_id and not compare_mode:
            try:
                selected_formula = next(f for f in active_formulas if str(f.pk) == selected_formula_id)
            except StopIteration:
                pass
        if not selected_formula and active_formulas:
            selected_formula = active_formulas[0]

        formula_groups = self._build_formula_groups(active_formulas, selected_formula)

        # 对比模式矩阵
        compare_formulas = all_stage_formulas if global_compare else active_formulas
        cpbom_columns, cpbom_matrix = [], []
        if compare_mode and compare_formulas:
            cpbom_columns, cpbom_matrix = self._build_color_powder_bom_matrix(compare_formulas)

        # BOM 表单
        bom_form = None
        entry_formset = None
        bom_entries = None
        readonly = False
        if selected_formula:
            bom = getattr(selected_formula, 'color_powder_bom', None)
            if bom and request.GET.get('edit') != '1':
                readonly = True
                bom_entries = bom.entries.select_related('raw_material__category').order_by('id')
            else:
                bom_form = ColorPowderBOMForm(instance=bom)
                entry_formset = ColorPowderBOMEntryFormSet(instance=bom, prefix='entries')

        context = {
            'production_order': ctx['production_order'],
            'project': ctx['project'],
            'material': ctx['material'],
            'stage_round_items': stage_round_items,
            'active_stage': active_stage,
            'active_round': active_round,
            'active_formulas': active_formulas,
            'formula_groups': formula_groups,
            'total_formula_count': len(all_stage_formulas),
            'selected_formula': selected_formula,
            'compare_mode': compare_mode,
            'global_compare': global_compare,
            'cpbom_columns': cpbom_columns,
            'cpbom_matrix': cpbom_matrix,
            'bom_form': bom_form,
            'entry_formset': entry_formset,
            'bom_entries': bom_entries,
            'readonly': readonly,
            'color_formula_ids': ctx['color_formula_ids'],
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        formula_id = request.POST.get('formula_id')
        selected_formula = get_object_or_404(LabFormula, pk=formula_id)

        project = self._resolve_project()
        if selected_formula.project_id != project.pk:
            raise PermissionDenied("配方不属于当前项目")

        # 仅允许为已下发配色任务的配方提交 BOM
        from app_trial_production.models import ProductionOrderFormulaDetail
        has_color_task = ProductionOrderFormulaDetail.objects.filter(
            formula=selected_formula,
            needs_color_matching=True,
            production_order__color_task__isnull=False,
        ).exists()
        if not has_color_task:
            raise PermissionDenied("该配方关联的工单未下发配色任务，不允许提交色粉BOM")

        bom, _ = ColorPowderBOM.objects.get_or_create(formula=selected_formula)
        bom_form = ColorPowderBOMForm(request.POST, instance=bom)
        entry_formset = ColorPowderBOMEntryFormSet(request.POST, instance=bom, prefix='entries')

        if bom_form.is_valid() and entry_formset.is_valid():
            bom = bom_form.save(commit=False)
            bom.filled_by = request.user
            bom.save()
            entry_formset.instance = bom
            entry_formset.save()
            messages.success(request, f'配方 {selected_formula.name} v{selected_formula.version} 色粉BOM已保存')

            # 批量保存/覆盖：将该配方的 BOM 复制到同实验单号下其他需配色的配方
            batch_mode = request.POST.get('batch_save_mode', '')
            if batch_mode in ('save', 'overwrite'):
                trial_code = selected_formula.code
                overwrite = (batch_mode == 'overwrite')
                copied = batch_copy_bom(selected_formula, trial_code, request.user, overwrite=overwrite)
                if copied:
                    label = '覆盖' if overwrite else '复制'
                    messages.success(request, f'已批量{label}色粉BOM到 {copied} 个配方版本')

            # BOM 保存后自动推进关联工单的 ColorMatchingTask
            from app_trial_production.models import ProductionOrderFormulaDetail
            order_ids = ProductionOrderFormulaDetail.objects.filter(
                formula=selected_formula,
            ).values_list('production_order_id', flat=True)
            for order_id in order_ids:
                try:
                    task = ColorMatchingTask.objects.get(production_order_id=order_id)
                except ColorMatchingTask.DoesNotExist:
                    continue
                # 已经完成的跳过
                if task.status == ColorMatchingTask.Status.COMPLETED:
                    continue
                if task.status == ColorMatchingTask.Status.PENDING:
                    ColorMatchingTaskService.start_task(task, request.user)
                # 检查该工单所有需配色的配方 BOM 是否都已填完
                if check_order_bom_complete(task.production_order):
                    ColorMatchingTaskService.complete_task(task, request.user)

            # 保留现有 query 参数（如 stage/round/order_pk），覆盖 formula_id
            params = request.GET.copy()
            params['formula_id'] = str(selected_formula.pk)
            return redirect(f'{request.path}?{params.urlencode()}')

        # POST 失败：完整重建上下文，保留阶段/轮次导航和已有 BOM 数据
        ctx = self._build_base_context()
        stage_round_items = ctx['stage_round_items']
        all_stage_formulas = ctx['all_stage_formulas']

        # 尝试恢复用户之前选择的 stage/round（从 POST 数据或默认值）
        active_stage = request.POST.get('active_stage', self.STAGE_ORDER[0])
        try:
            active_round = int(request.POST.get('active_round')) if request.POST.get('active_round') else None
        except (ValueError, TypeError):
            active_round = None

        # 定位活跃阶段/轮次的公式列表
        active_formulas = all_stage_formulas
        for item in stage_round_items:
            if item['stage'] == active_stage and (active_round is None or item['round'] == active_round):
                active_formulas = item['formulas']
                break

        formula_groups = self._build_formula_groups(active_formulas, selected_formula)

        # 已有的 BOM entries（从已保存的 BOM 读取）
        existing_bom = getattr(selected_formula, 'color_powder_bom', None)
        bom_entries = None
        if existing_bom:
            bom_entries = existing_bom.entries.select_related('raw_material__category').order_by('id')

        return render(request, self.template_name, {
            'production_order': ctx['production_order'],
            'project': ctx['project'],
            'material': ctx['material'],
            'stage_round_items': stage_round_items,
            'active_stage': active_stage,
            'active_round': active_round,
            'active_formulas': active_formulas,
            'formula_groups': formula_groups,
            'total_formula_count': len(all_stage_formulas),
            'selected_formula': selected_formula,
            'compare_mode': False,
            'global_compare': False,
            'cpbom_columns': [],
            'cpbom_matrix': [],
            'bom_form': bom_form,
            'entry_formset': entry_formset,
            'bom_entries': bom_entries,
            'readonly': False,
            'color_formula_ids': ctx['color_formula_ids'],
        })
