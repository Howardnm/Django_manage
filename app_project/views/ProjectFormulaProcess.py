from collections import Counter, OrderedDict, defaultdict
from statistics import mean
from itertools import groupby
import logging
from django.views.generic import DetailView, View
from django.http import Http404, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.urls import reverse
from common_utils.state_machine import InvalidStateTransition
from app_project.mixins import ProjectAccessMixin
from app_project.models import Project, ProjectStage, ProjectNode
from app_formula.models import LabFormula, FormulaTestResult
from app_material.models import TestConfig
from app_trial_production.models.production_order import ProductionOrderFormulaDetail

logger = logging.getLogger(__name__)

_RETURNABLE_TASK_STATUS = ('COMPLETED', 'RESULTS_WRITTEN_BACK')


def _latest_testing_tasks(order_ids):
    """每个工单最新一条测试任务。一次查询，按创建时间与主键倒序取第一条。"""
    if not order_ids:
        return {}
    from app_material_testing.models import TestingTask

    latest = {}
    tasks = TestingTask.objects.filter(
        production_order_id__in=order_ids,
    ).order_by('production_order_id', '-created_at', '-pk')
    for task in tasks:
        latest.setdefault(task.production_order_id, task)
    return latest


class ProjectFormulaProcessView(ProjectAccessMixin, DetailView):
    """项目配方过程详情页：按RND轮次展示配方迭代过程"""
    permission_required = 'app_project.view_project'
    model = Project
    template_name = 'apps/app_project/formula_process.html'
    context_object_name = 'project'

    queryset = Project.objects.select_related(
        'manager', 'repository', 'repository__customer', 'repository__oem',
        'material'
    ).prefetch_related(
        'material__properties__test_config__category'
    )

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def _fetch_formulas(self, project, material):
        project_formulas = LabFormula.objects.filter(
            project=project
        ).select_related(
            'project_node', 'material_type', 'creator', 'process', 'project',
        ).prefetch_related(
            'bom_lines__raw_material__category',
            'test_results__test_config__category',
            'test_results__production_order',
            'color_powder_bom__entries__raw_material__category',
        ).order_by('version')

        material_formulas = LabFormula.objects.none()
        if material:
            material_formulas = LabFormula.objects.filter(
                project__material=material
            ).exclude(
                pk__in=project_formulas.values_list('pk', flat=True)
            ).select_related(
                'project', 'project_node', 'material_type', 'creator', 'process'
            ).prefetch_related(
                'bom_lines__raw_material__category',
                'test_results__test_config__category',
                'test_results__production_order',
                'color_powder_bom__entries__raw_material__category',
            ).order_by('version')

        return sorted(
            list(project_formulas) + list(material_formulas),
            key=lambda f: (f.version if f.version else 1)
        )

    def _build_comparison_matrices(self, formulas, material=None):
        """构建对比矩阵：材料基准列 + 配方列(按创建时间正序)，委托共享矩阵构建器。"""
        from common_utils.comparison_matrix import build_compare_matrices

        # 按创建时间正序排列 (越早越靠左)
        formulas = sorted(formulas, key=lambda f: f.created_at)

        columns = []
        if material:
            columns.append({'type': 'material', 'obj': material})
        for f in formulas:
            columns.append({'type': 'formula', 'obj': f})

        bom_matrix, cpbom_matrix, test_matrix = build_compare_matrices(columns)
        return columns, bom_matrix, test_matrix, cpbom_matrix

    @staticmethod
    def _build_test_result_tabs(formula, tab_id_prefix='tab'):
        """构建测试结果 Tab 数据 — 手动录入 + 各工单回写。
        Returns: (tabs, has_results)
        """
        from itertools import groupby
        tabs = []

        # 手动录入
        manual = [
            r for r in formula.test_results.all()
            if r.production_order_id is None
        ]
        manual.sort(key=lambda r: (
            r.test_config.category.order,
            r.test_config.order,
        ))
        tabs.append({
            'label': '手动录入',
            'tab_id': f'{tab_id_prefix}-manual',
            'results': manual,
            'type': 'manual',
        })

        # 各工单回写
        order_results = [
            r for r in formula.test_results.all()
            if r.production_order_id is not None
        ]
        order_results.sort(key=lambda r: (
            r.production_order.code,
            r.test_config.category.order,
            r.test_config.order,
        ))
        order_groups = [
            (order, list(items))
            for order, items in groupby(order_results, key=lambda r: r.production_order)
        ]
        latest_task = _latest_testing_tasks([order.pk for order, _ in order_groups])
        for order, items in order_groups:
            task = latest_task.get(order.pk)
            can_return = bool(task and task.status in _RETURNABLE_TASK_STATUS)
            tabs.append({
                'label': order.code,
                'tab_id': f'{tab_id_prefix}-order-{order.pk}',
                'results': items,
                'type': 'order',
                'order': order,
                'order_id': order.pk,
                'task_status': task.status if task else '',
                'task_status_label': task.get_status_display() if task else '无测试任务',
                'can_return': can_return,
            })

        return tabs, any(t['results'] for t in tabs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from django.core.exceptions import ObjectDoesNotExist

        from app_raw_material.models import PriceAvgConfig, RawMaterial

        project = self.object
        material = project.material

        all_formulas = self._fetch_formulas(project, material)

        # 按阶段 + 轮次分组，用于顶部 tab。名单与可新增配方的阶段同一份，含开发周期完成。
        stage_order = ProjectNode.FORMULA_STAGES
        stage_grouped = OrderedDict()
        all_stage_formulas = []  # 所有配方(用于全局对比，含竞品)
        competitor_formulas = []  # 竞品配方 → 伪阶段「客户竞品」
        for f in all_formulas:
            if f.is_competitor or not f.project_node:
                # 竞品配方（含无节点的异常配方兜底）：纳入全局对比池，统一归入「客户竞品」伪阶段
                all_stage_formulas.append(f)
                competitor_formulas.append(f)
                continue
            all_stage_formulas.append(f)
            s = f.project_node.stage
            if s not in stage_grouped:
                stage_grouped[s] = OrderedDict()
            r = f.project_node.round
            if r not in stage_grouped[s]:
                stage_grouped[s][r] = []
            stage_grouped[s][r].append(f)

        # 构建 tab 列表：[{stage, stage_display, round, formulas}, ...]
        stage_round_items = []
        for stage in stage_order:
            if stage not in stage_grouped:
                continue
            for r in sorted(stage_grouped[stage].keys()):
                stage_round_items.append({
                    'stage': stage,
                    'stage_display': dict(ProjectStage.choices)[stage],
                    'round': r,
                    'formulas': stage_grouped[stage][r],
                })

        # 客户竞品伪阶段：竞品配方无 project_node，统一追加到 Tab 栏末尾
        if competitor_formulas:
            stage_round_items.append({
                'stage': 'COMPETITOR',
                'stage_display': '客户竞品',
                'round': None,
                'formulas': competitor_formulas,
            })

        # 当前激活的阶段和轮次
        active_stage = self.request.GET.get('stage', stage_order[0])
        active_round = self.request.GET.get('round')
        try:
            active_round = int(active_round) if active_round else None
        except (ValueError, TypeError):
            active_round = None

        # 查找匹配的 tab item
        active_item = None
        for item in stage_round_items:
            if item['stage'] == active_stage and (active_round is None or item['round'] == active_round):
                active_item = item
                break
        if active_item is None and stage_round_items:
            active_item = stage_round_items[0]

        if active_item:
            active_stage = active_item['stage']
            active_round = active_item['round']
            active_formulas = active_item['formulas']
        else:
            active_formulas = []

        # 按 code (实验单号) 分组，用于侧边栏折叠显示。
        # 所有实验单一律折叠（含只有一个版本的），列表形态保持统一；
        # 选中配方所在的那一组会在下面被自动展开。
        active_formulas_sorted = sorted(active_formulas, key=lambda f: (f.code or '', f.version))
        formula_groups = []
        for code, items in groupby(active_formulas_sorted, key=lambda f: f.code):
            formula_groups.append({
                'code': code,
                'formulas': list(items),
                'is_collapsed': True,
            })

        # 对比模式
        compare_mode = self.request.GET.get('compare') == '1'
        global_compare = compare_mode and not self.request.GET.get('stage')

        # 选中的单个配方（非对比模式）
        selected_formula = None
        selected_formula_id = self.request.GET.get('formula_id')
        if selected_formula_id and not compare_mode:
            try:
                selected_formula = next(
                    f for f in active_formulas if str(f.pk) == selected_formula_id
                )
            except StopIteration:
                pass
        if not selected_formula and active_formulas:
            selected_formula = active_formulas[0]

        # 如果选中的配方在某个折叠组中，自动展开该组
        if selected_formula:
            for g in formula_groups:
                if any(f.pk == selected_formula.pk for f in g['formulas']):
                    g['is_collapsed'] = False
                    break

        # 关联工单列表 — 当前阶段 tab 内所有配方的工单（按工单去重）
        related_orders = []
        if not compare_mode and active_formulas:
            formula_ids = [f.pk for f in active_formulas]
            order_details = ProductionOrderFormulaDetail.objects.filter(
                formula_id__in=formula_ids
            ).select_related(
                'production_order__creator',
                'production_order__project',
            ).order_by('-production_order__created_at')
            seen_order_pks = set()
            for d in order_details:
                o = d.production_order
                if o.pk in seen_order_pks:
                    continue
                seen_order_pks.add(o.pk)
                related_orders.append({
                    'code': o.code,
                    'status': o.get_status_display(),
                    'status_css': o.STATUS_CSS_MAP.get(o.status, 'bg-secondary-lt'),
                    'status_dot': o.STATUS_DOT_MAP.get(o.status, 'bg-secondary'),
                    'planned_quantity': o.quantity_planned,
                    'quantity_actual': o.quantity_actual,
                    'creator': o.creator.username,
                    'trial_code': o.trial_code,
                    'created_at': o.created_at,
                    'scheduled_date': o.extrusion_scheduled_date,
                    'scheduled_end': o.extrusion_scheduled_end,
                    'pk': o.pk,
                })

        # 测试结果 Tab 数据（手动录入 + 各工单回写）
        test_result_tabs, has_test_results = [], False
        if selected_formula:
            test_result_tabs, has_test_results = self._build_test_result_tabs(selected_formula)

        # 对比矩阵 (全局对比用全阶段配方，单tab对比用当前tab) → DRF 序列化为 JSON 数据契约
        compare_formulas = all_stage_formulas if global_compare else active_formulas
        compare_data = None
        if compare_mode and compare_formulas:
            from common_utils.serializers.compare import serialize_compare
            columns, bom_matrix, test_matrix, cpbom_matrix = self._build_comparison_matrices(compare_formulas, material=material)
            compare_data = serialize_compare(
                columns, (bom_matrix, cpbom_matrix, test_matrix),
                PriceAvgConfig.get().months, project,
            )
        elif active_formulas:
            # 单配方模式：侧边栏成本徽章、BOM 卡片、色粉卡片、信息卡片的合计成本
            # 共用一次价格装载（对比模式上面已经预热过了）
            from app_formula.services import FormulaCostCalculator
            FormulaCostCalculator.for_formulas(active_formulas)

        # 客户竞品详细卡片 — 选中竞品配方时展示其关联工单的竞品信息
        selected_competitor_info = None
        if selected_formula and selected_formula.is_competitor:
            detail = selected_formula.productionorderformuladetail_set.select_related(
                'production_order__customer',
            ).order_by('-production_order__created_at').first()
            if detail:
                o = detail.production_order
                selected_competitor_info = {
                    'company': o.competitor_company,
                    'brand': o.competitor_brand,
                    'model': o.competitor_model,
                    'customer': o.customer,
                    'order_pk': o.pk,
                    'order_code': o.code,
                    'order_status': o.get_status_display(),
                    'injection_temperature': o.injection_temperature,
                    'injection_pretreatment': o.injection_pretreatment,
                }

        stock_totals = {}
        if selected_formula and not compare_mode:
            material_ids = [
                line.raw_material_id for line in selected_formula.bom_lines.all()
            ]
            try:
                powder = selected_formula.color_powder_bom
            except ObjectDoesNotExist:
                powder = None
            if powder is not None:
                material_ids.extend(
                    entry.raw_material_id for entry in powder.entries.all()
                )
            stock_totals = RawMaterial.unrestricted_stock_totals(material_ids)

        context.update({
            'material': material,
            'related_orders': related_orders,
            'stage_round_items': stage_round_items,
            'active_stage': active_stage,
            'active_round': active_round,
            'active_formulas': active_formulas,
            'formula_groups': formula_groups,
            'total_formula_count': len(all_stage_formulas),
            'selected_formula': selected_formula,
            'test_result_tabs': test_result_tabs,
            'has_test_results': has_test_results,
            'compare_mode': compare_mode,
            'global_compare': global_compare,
            'compare_data': compare_data,
            'selected_competitor_info': selected_competitor_info,
            'avg_months': PriceAvgConfig.get().months,
            'stock_totals': stock_totals,
        })
        return context


class CompetitorOrderCreateView(ProjectAccessMixin, View):
    """客户竞品工单创建 — 自动创建无BOM配方实验单并关联，跳过挤出环节。"""

    model = Project
    pk_url_kwarg = 'pk'
    permission_required = 'app_project.view_project'

    def get(self, request, pk):
        project = self.get_object_or_deny()
        from app_material.models import TestConfig, MaterialType
        from app_mold_injection.models import MoldType
        from itertools import groupby
        all_configs = TestConfig.objects.select_related('category').order_by('category__order', 'order')
        grouped_test_items = []
        for cat, items in groupby(all_configs, key=lambda tc: tc.category):
            grouped_test_items.append({'category': cat, 'items': list(items)})
        available_molds = MoldType.objects.filter(
            status='AVAILABLE',
        ).order_by('mold_code')
        preset_molds = available_molds.filter(mold_type='TEST_SPECIMEN')
        material_types = MaterialType.objects.order_by('name')
        context = {
            'project': project,
            'grouped_test_items': grouped_test_items,
            'available_molds': available_molds,
            'preset_molds': preset_molds,
            'material_types': material_types,
        }
        return render(request, 'apps/app_project/competitor_create.html', context)

    def post(self, request, pk):
        project = self.get_object_or_deny()
        self.check_edit_permission(project)

        # ── 提取基础字段 ──
        quantity_planned = float(request.POST.get('quantity_planned', 0) or 0)
        injection_temperature = request.POST.get('injection_temperature', '') or None
        injection_pretreatment = request.POST.get('injection_pretreatment', '')
        packaging_desc = request.POST.get('packaging_desc', '')
        storage_location = request.POST.get('storage_location', '')
        competitor_company = request.POST.get('competitor_company', '')
        competitor_brand = request.POST.get('competitor_brand', '')
        competitor_model = request.POST.get('competitor_model', '')
        customer_id = request.POST.get('customer_id', '') or None
        material_type_id = request.POST.get('material_type', '') or None
        material_color_name = request.POST.get('material_color_name', '')
        pantone_code = request.POST.get('pantone_code', '')
        rgb_value = request.POST.get('rgb_value', '')

        # ── 校验 ──
        if quantity_planned <= 0:
            messages.error(request, '计划数量必须大于 0')
            return redirect(reverse('project_formula_process', kwargs={'pk': pk}) + '?stage=COMPETITOR')

        if not material_type_id:
            messages.error(request, '请选择基材类型')
            return redirect(reverse('project_formula_process', kwargs={'pk': pk}) + '?stage=COMPETITOR')

        # ── 构建配方名称 ──
        formula_name_parts = ['竞品']
        if competitor_company:
            formula_name_parts.append(competitor_company)
        if competitor_brand:
            formula_name_parts.append(competitor_brand)
        if competitor_model:
            formula_name_parts.append(competitor_model)
        if len(formula_name_parts) == 1:
            formula_name_parts.append(project.name)
        formula_name = '-'.join(formula_name_parts)[:100]

        # ── 解析模具行 ──
        mold_rows = self._parse_mold_rows(request.POST)
        valid_molds = [(int(mid), int(qty)) for mid, qty in mold_rows if mid and qty > 0]

        # ── 解析测试项目 ──
        test_item_ids = [int(tid) for tid in request.POST.getlist('test_items') if tid]

        # ── 创建工单 + 配方 ──
        from app_trial_production.services.order_service import ProductionOrderService
        from app_mold_injection.models import MoldRequirement, MoldRequirementFormulaDetail

        with transaction.atomic():
            order, formula = ProductionOrderService.create_competitor_order_with_formula(
                user=request.user,
                project=project,
                formula_name=formula_name,
                material_type_id=int(material_type_id),
                quantity_planned=quantity_planned,
                material_color_name=material_color_name,
                pantone_code=pantone_code,
                rgb_value=rgb_value,
                injection_temperature=injection_temperature,
                injection_pretreatment=injection_pretreatment,
                packaging_desc=packaging_desc,
                storage_location=storage_location,
                competitor_company=competitor_company,
                competitor_brand=competitor_brand,
                competitor_model=competitor_model,
                customer_id=customer_id,
            )

            # 模具需求（formula 指向创建的配方）
            for i, (mold_id, qty) in enumerate(valid_molds):
                mr = MoldRequirement.objects.create(
                    production_order=order,
                    mold_id=mold_id,
                    order=i,
                )
                MoldRequirementFormulaDetail.objects.create(
                    mold_requirement=mr,
                    formula=formula,
                    specimen_quantity=qty,
                )

            # 测试项目
            if test_item_ids:
                order.test_items.set(test_item_ids)

        messages.success(
            request,
            f'竞品工单 [{order.code}] 已创建（配方: {formula.code}）'
            f'（{len(valid_molds)} 个模具，跳过挤出直达注塑）'
        )
        return redirect(
            reverse('project_formula_process', kwargs={'pk': pk})
            + f'?stage=COMPETITOR&formula_id={formula.pk}'
        )

    @staticmethod
    def _parse_mold_rows(post_data):
        """解析 POST 中的模具行数据。"""
        rows = []
        index = 0
        while True:
            mold_key = f'mold_id_{index}'
            if mold_key not in post_data:
                break
            try:
                mold_id = int(post_data.get(mold_key, 0) or 0)
                qty = int(post_data.get(f'specimen_qty_{index}', 0) or 0)
            except (ValueError, TypeError):
                mold_id = 0
                qty = 0
            rows.append((mold_id, qty))
            index += 1
        return rows


class FormulaMeanWritebackView(ProjectAccessMixin, View):
    """把同一实验单各版本的工单结果对照展示，并回写手动录入。

    地址是 ``/mean-writeback/<实验单号>/``。同一 ``code`` 的全部版本列在一页。
    已有手动值的格子保持原值，不用工单均值覆盖；该版本这一项还没有手动值时，才预填均值。
    """

    permission_required = 'app_project.view_project'

    def _get_project(self, pk):
        project = get_object_or_404(Project, pk=pk)
        self.check_object_permission(project)
        self.check_edit_permission(project)
        return project

    def _get_formula(self, pk, formula_pk):
        """按版本主键取一条配方。测试退回和旧地址跳转还用它。"""
        project = self._get_project(pk)
        return get_object_or_404(
            LabFormula.objects.select_related('project', 'material_type'),
            pk=formula_pk, project=project,
        )

    def _formulas_for_code(self, pk, formula_code):
        """本项目下这个实验单号的全部版本，按版本号升序。对不上或单号为空则 404。"""
        project = self._get_project(pk)
        if not formula_code:
            raise Http404
        formulas = list(
            LabFormula.objects.filter(project_id=project.pk, code=formula_code)
            .select_related('project', 'material_type')
            .order_by('version', 'pk')
        )
        if not formulas:
            raise Http404
        return formulas

    @staticmethod
    def _format_number(value):
        if value is None:
            return '—'
        return f'{value:.3f}'

    @staticmethod
    def _aggregate_items(test_config, items):
        """工单结果 → (数值均值, 文本众数)。没有可聚合的值时两者都空。"""
        if test_config.data_type == 'NUMBER':
            vals = [r.value for r in items if r.value is not None]
            if not vals:
                return None, ''
            return round(mean(vals), 3), ''
        texts = [r.value_text for r in items if r.value_text]
        if not texts:
            return None, ''
        return None, Counter(texts).most_common(1)[0][0]

    @staticmethod
    def _input_number(value):
        if value is None:
            return ''
        return f'{value:.3f}'

    def _build_matrices(self, formulas):
        """只读工单矩阵 + 可编辑手动矩阵。行是各版本工单结果与手动录入的并集。"""
        formula_ids = [f.pk for f in formulas]
        results = FormulaTestResult.objects.filter(
            formula_id__in=formula_ids,
        ).select_related('test_config__category', 'production_order')

        order_map = defaultdict(lambda: defaultdict(list))
        manual_map = defaultdict(dict)
        orders_by_formula = defaultdict(list)
        seen_orders = defaultdict(set)
        test_configs = {}

        for result in results:
            test_configs.setdefault(result.test_config_id, result.test_config)
            if result.production_order_id:
                order_map[result.formula_id][result.test_config_id].append(result)
                if result.production_order_id not in seen_orders[result.formula_id]:
                    seen_orders[result.formula_id].add(result.production_order_id)
                    orders_by_formula[result.formula_id].append(result.production_order)
            else:
                manual_map[result.formula_id][result.test_config_id] = result

        for orders in orders_by_formula.values():
            orders.sort(key=lambda order: order.code)

        version_columns = []
        for formula in formulas:
            orders = orders_by_formula[formula.pk]
            version_columns.append({
                'formula': formula,
                'orders': orders,
                'span': len(orders) + 1,
            })

        rows = []
        for test_config in sorted(
            test_configs.values(),
            key=lambda tc: (tc.category.order if tc.category else 0, tc.order, tc.pk),
        ):
            order_cells = []
            editors = []
            date_source = None
            for formula in formulas:
                items = order_map[formula.pk].get(test_config.pk, [])
                by_order = {item.production_order_id: item for item in items}
                orders = orders_by_formula[formula.pk]
                for index, order in enumerate(orders):
                    item = by_order.get(order.pk)
                    if item is None:
                        text = '—'
                    elif test_config.data_type == 'NUMBER':
                        text = self._format_number(item.value)
                    else:
                        text = item.value_text or '—'
                    order_cells.append({
                        'text': text,
                        'version_start': index == 0,
                        'is_mean': False,
                    })
                agg_value, agg_text = self._aggregate_items(test_config, items)
                if test_config.data_type == 'NUMBER':
                    mean_text = self._format_number(agg_value)
                else:
                    mean_text = agg_text or '—'
                order_cells.append({
                    'text': mean_text,
                    'version_start': not orders,
                    'is_mean': True,
                })

                manual = manual_map[formula.pk].get(test_config.pk)
                if manual is not None:
                    # 已有手动记录就用它，哪怕值是空的，也不退回均值
                    if date_source is None:
                        date_source = manual
                    if test_config.data_type == 'NUMBER':
                        input_value, input_text = self._input_number(manual.value), ''
                    else:
                        input_value, input_text = '', manual.value_text
                elif test_config.data_type == 'NUMBER':
                    input_value, input_text = self._input_number(agg_value), ''
                else:
                    input_value, input_text = '', agg_text
                editors.append({
                    'formula_id': formula.pk,
                    'input_value': input_value,
                    'input_text': input_text,
                })

            rows.append({
                'test_config': test_config,
                'data_type': test_config.data_type,
                'order_cells': order_cells,
                'editors': editors,
                'test_date': date_source.test_date if date_source else None,
                'remark': date_source.remark if date_source else '',
            })
        return version_columns, rows

    def get(self, request, pk, formula_code):
        formulas = self._formulas_for_code(pk, formula_code)
        formula = formulas[0]
        version_columns, rows = self._build_matrices(formulas)

        all_test_configs = TestConfig.objects.select_related('category').order_by(
            'category__order', 'order')

        # 空表也要能进来：本页同时用于新增测试项目。
        return render(request, 'apps/app_project/detail/_test_result_mean_writeback.html', {
            'project': formula.project,
            'formula': formula,
            'formulas': formulas,
            'version_columns': version_columns,
            'order_colspan': sum(col['span'] for col in version_columns) + 1,
            'rows': rows,
            'all_test_configs': all_test_configs,
            # 新增行选中测试项目后，由 JS 按 type 生成对应的值控件；
            # SELECT 型还要拿 options 填下拉，否则只能退化成文本框。
            'writeback_config_meta': {
                str(tc.pk): {
                    'type': tc.data_type,
                    'options': tc.get_options_list() if tc.data_type == 'SELECT' else [],
                }
                for tc in all_test_configs
            },
        })

    @staticmethod
    def _parse_value_key(key):
        """``num_{配方pk}_{测试项pk}`` / ``txt_{配方pk}_{测试项pk}``。对不上返回 None。"""
        if key.startswith('num_'):
            kind, rest = 'value', key[4:]
        elif key.startswith('txt_'):
            kind, rest = 'text', key[4:]
        else:
            return None
        formula_id, sep, test_config_id = rest.partition('_')
        if sep and formula_id.isdigit() and test_config_id.isdigit():
            return kind, int(formula_id), int(test_config_id)
        return None

    def post(self, request, pk, formula_code):
        formulas = self._formulas_for_code(pk, formula_code)
        formula = formulas[0]
        allowed_ids = {item.pk for item in formulas}
        from decimal import Decimal, InvalidOperation

        from django.utils.dateparse import parse_date

        # 没有这个标记就无法区分「用户删光了行」和「请求被裁剪」，后者会把手动录入清空。
        if request.POST.get('writeback_form') != '1':
            messages.error(request, '提交的数据不完整，请刷新页面后重试。')
            return redirect(self._redirect_url(pk, formula))

        # 只处理本次真正提交的格子。没出现的测试项不动 —— 不能从「没提交」推断成「删掉」，
        # 否则并发时别人刚加的项会被清掉。空值才删这一格。
        by_test = defaultdict(dict)
        dates, remarks, origins = {}, {}, {}
        for key, raw in request.POST.items():
            parsed = self._parse_value_key(key)
            if parsed:
                kind, formula_id, test_config_id = parsed
                if formula_id in allowed_ids:
                    by_test[test_config_id][formula_id] = (kind, raw)
            elif key.startswith('date_') and key[5:].isdigit():
                dates[int(key[5:])] = raw
            elif key.startswith('rem_') and key[4:].isdigit():
                remarks[int(key[4:])] = raw
            elif key.startswith('orig_') and key[5:].isdigit() and raw.isdigit():
                # orig_{新pk} = 原pk：这一行的测试项目被改过，原项在全部版本上的手动记录都要移除
                origins[int(key[5:])] = int(raw)

        test_config_ids = set(by_test) | set(origins)
        configs = {
            item.pk: item
            for item in TestConfig.objects.filter(pk__in=test_config_ids)
        }

        created = updated = removed = 0
        with transaction.atomic():
            for test_config_id, origin in origins.items():
                if origin == test_config_id or test_config_id not in configs:
                    continue
                removed += FormulaTestResult.objects.filter(
                    formula_id__in=allowed_ids,
                    test_config_id=origin,
                    production_order__isnull=True,
                ).delete()[0]

            existing_map = {
                (item.formula_id, item.test_config_id): item
                for item in FormulaTestResult.objects.filter(
                    formula_id__in=allowed_ids,
                    test_config_id__in=by_test.keys(),
                    production_order__isnull=True,
                )
            }

            for test_config_id, formula_cells in by_test.items():
                test_config = configs.get(test_config_id)
                if test_config is None:
                    continue
                shared_date = parse_date(dates.get(test_config_id) or '')
                shared_remark = (remarks.get(test_config_id) or '').strip()[:50]
                for formula_id, (kind, raw_value) in formula_cells.items():
                    existing = existing_map.get((formula_id, test_config_id))
                    value = (raw_value or '').strip()
                    if not value:
                        if existing:
                            existing.delete()
                            removed += 1
                        continue

                    expects_number = test_config.data_type == 'NUMBER'
                    if expects_number != (kind == 'value'):
                        continue

                    if kind == 'value':
                        try:
                            parsed = Decimal(value)
                        except InvalidOperation:
                            continue
                        defaults = {'value': parsed, 'value_text': ''}
                    else:
                        defaults = {'value': None, 'value_text': value}
                    defaults['test_date'] = shared_date
                    defaults['remark'] = shared_remark

                    if existing:
                        for attr, val in defaults.items():
                            setattr(existing, attr, val)
                        existing.save()
                        updated += 1
                    else:
                        FormulaTestResult.objects.create(
                            formula_id=formula_id,
                            test_config_id=test_config_id,
                            production_order=None,
                            **defaults,
                        )
                        created += 1

        if created or updated or removed:
            messages.success(
                request,
                f'测试数据已保存：新增 {created} 项、更新 {updated} 项、清除 {removed} 项')
        else:
            messages.info(request, '没有需要保存的改动')
        return redirect(self._redirect_url(pk, formula))

    @staticmethod
    def _redirect_url(project_pk, formula):
        """根据配方类型决定重定向目标。"""
        base = reverse('project_formula_process', kwargs={'pk': project_pk})
        if formula.is_competitor:
            return f'{base}?stage=COMPETITOR&formula_id={formula.pk}'
        return f'{base}?formula_id={formula.pk}'


class FormulaMeanWritebackLegacyRedirectView(FormulaMeanWritebackView):
    """旧地址 ``/mean-writeback/<配方pk>/`` 跳到实验单号地址。"""

    def get(self, request, pk, formula_pk):
        formula = self._get_formula(pk, formula_pk)
        if not formula.code:
            raise Http404
        return redirect(
            'project_formula_mean_writeback',
            pk=pk, formula_code=formula.code,
        )

    def post(self, request, pk, formula_pk):
        return self.http_method_not_allowed(request)


class FormulaTestReturnView(ProjectAccessMixin, View):
    """把配方过程页当前工单 tab 的测试任务退回测试中。"""

    permission_required = 'app_project.view_project'

    def post(self, request, pk, formula_pk, order_pk):
        FormulaMeanWritebackView._get_formula(self, pk, formula_pk)

        def finish(level, text, ok):
            getattr(messages, level)(request, text)
            return JsonResponse(
                {'status': 'success' if ok else 'error', 'message': text},
                status=200 if ok else 400,
            )

        has_written = FormulaTestResult.objects.filter(
            formula_id=formula_pk, production_order_id=order_pk,
        ).exists()
        if not has_written:
            return finish('error', '该工单在当前配方上没有已回写的测试结果，不能退回', False)

        from app_material_testing.models import TestingTask
        from app_material_testing.services import TestingTaskService

        task = TestingTask.objects.filter(
            production_order_id=order_pk,
        ).select_related('production_order').order_by('-created_at', '-pk').first()
        if task is None:
            return finish('error', '该工单没有测试任务', False)

        try:
            TestingTaskService.return_to_in_progress(task, request.user)
        except ValueError as exc:
            return finish('warning', str(exc), False)
        except InvalidStateTransition:
            logger.exception(f"Test return failed for task {task.pk}")
            return finish('error', '测试任务状态已变化，请刷新后重试', False)

        return finish(
            'success',
            f'工单 {task.production_order.code} 的测试任务已退回测试中，材料测试中心可以重新填写',
            True,
        )
