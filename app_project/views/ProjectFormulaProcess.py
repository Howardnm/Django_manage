from collections import OrderedDict
from itertools import groupby
import logging
from django.views.generic import DetailView, View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.urls import reverse
from app_project.mixins import ProjectAccessMixin
from app_project.models import Project, ProjectStage, ProjectNode
from app_formula.models import LabFormula
from app_trial_production.models.production_order import ProductionOrderFormulaDetail

logger = logging.getLogger(__name__)


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
            'color_powder_bom__entries__raw_material',
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
                'color_powder_bom__entries__raw_material',
            ).order_by('version')

        return sorted(
            list(project_formulas) + list(material_formulas),
            key=lambda f: (f.version if f.version else 1)
        )

    def _build_comparison_matrices(self, formulas, material=None):
        """参考 FormulaCompareView 构建对比矩阵：材料基准列 + 配方列(按创建时间降序)"""
        if not formulas:
            return [], [], []

        # 按创建时间正序排列 (越早越靠左)
        formulas = sorted(formulas, key=lambda f: f.created_at)

        columns = []
        if material:
            columns.append({'type': 'material', 'obj': material})
        for f in formulas:
            columns.append({'type': 'formula', 'obj': f})

        # BOM 对比矩阵 — 先建内存索引，避免 .filter() 绕过 prefetch 缓存
        all_raw_materials = set()
        bom_map = {}  # {formula_id: {raw_material_id: percentage}}
        for f in formulas:
            bom_map[f.id] = {}
            for line in f.bom_lines.all():
                all_raw_materials.add(line.raw_material)
                bom_map[f.id][line.raw_material_id] = line.percentage
        sorted_raw_materials = sorted(all_raw_materials, key=lambda x: (x.category.order, x.name))

        bom_matrix = []
        for rm in sorted_raw_materials:
            row = {'item': rm, 'values': []}
            for col in columns:
                if col['type'] == 'material':
                    row['values'].append({'val': '-', 'is_empty': True})
                else:
                    pct = bom_map.get(col['obj'].id, {}).get(rm.id)
                    row['values'].append({
                        'val': pct if pct is not None else '-',
                        'is_empty': pct is None,
                    })
            bom_matrix.append(row)

        # 色粉BOM 对比矩阵
        all_cp_materials = set()
        cpbom_map = {}
        for f in formulas:
            cpbom_map[f.id] = {}
            bom = getattr(f, 'color_powder_bom', None)
            if bom:
                for entry in bom.entries.select_related('raw_material__category'):
                    all_cp_materials.add(entry.raw_material)
                    cpbom_map[f.id][entry.raw_material_id] = entry.percentage
        sorted_cp_materials = sorted(all_cp_materials, key=lambda x: (x.category.order, x.name))

        cpbom_matrix = []
        for rm in sorted_cp_materials:
            row = {'item': rm, 'values': []}
            for col in columns:
                if col['type'] == 'material':
                    row['values'].append({'val': '-', 'is_empty': True})
                else:
                    pct = cpbom_map.get(col['obj'].id, {}).get(rm.id)
                    row['values'].append({
                        'val': pct if pct is not None else '-',
                        'is_empty': pct is None,
                    })
            cpbom_matrix.append(row)

        # 性能对比矩阵
        all_test_configs = set()
        mat_props = {}
        if material:
            mat_properties = list(material.properties.select_related('test_config').all())
            for p in mat_properties:
                all_test_configs.add(p.test_config)
            mat_props = {
                p.test_config_id: p.value_text if p.test_config.data_type != 'NUMBER' else p.value
                for p in mat_properties
            }

        formula_props = {}
        for f in formulas:
            formula_props[f.id] = {}
            for r in f.test_results.all():
                if r.production_order_id is not None:
                    continue  # 跳过工单回写结果，对比矩阵仅展示手动录入
                all_test_configs.add(r.test_config)
                formula_props[f.id][r.test_config_id] = r.value_text if r.test_config.data_type != 'NUMBER' else r.value
        sorted_configs = sorted(all_test_configs, key=lambda x: (x.category.order, x.order))

        test_matrix = []
        for tc in sorted_configs:
            row = {'item': tc, 'values': []}
            base_val = mat_props.get(tc.id) if material else None

            for i, col in enumerate(columns):
                if col['type'] == 'material':
                    val = mat_props.get(tc.id)
                    row['values'].append({
                        'val': val if val is not None else '-',
                        'compare_class': '',
                        'is_base': True,
                    })
                else:
                    val = formula_props.get(col['obj'].id, {}).get(tc.id)
                    compare_class = ''
                    if val is not None and base_val is not None and tc.data_type == 'NUMBER':
                        try:
                            if val > base_val:
                                compare_class = 'text-green'
                            elif val < base_val:
                                compare_class = 'text-red'
                        except Exception:
                            pass

                    row['values'].append({
                        'val': val if val is not None else '-',
                        'compare_class': compare_class,
                        'is_base': False,
                    })
            test_matrix.append(row)

        return columns, bom_matrix, test_matrix, cpbom_matrix

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.object
        material = project.material

        all_formulas = self._fetch_formulas(project, material)

        # 按阶段 + 轮次分组，用于顶部 tab
        STAGE_ORDER = ['RND', 'PILOT', 'MID_TEST', 'MASS_PROD']
        stage_grouped = OrderedDict()
        all_stage_formulas = []  # 所有有节点的配方(用于全局对比)
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

        # 构建 tab 列表：[{stage, stage_display, round, formulas}, ...]
        stage_round_items = []
        for stage in STAGE_ORDER:
            if stage not in stage_grouped:
                continue
            for r in sorted(stage_grouped[stage].keys()):
                stage_round_items.append({
                    'stage': stage,
                    'stage_display': dict(ProjectStage.choices)[stage],
                    'round': r,
                    'formulas': stage_grouped[stage][r],
                })

        # 当前激活的阶段和轮次
        active_stage = self.request.GET.get('stage', STAGE_ORDER[0])
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

        # 按 code (实验单号) 分组，用于侧边栏折叠显示
        active_formulas_sorted = sorted(active_formulas, key=lambda f: (f.code or '', f.version))
        formula_groups = []
        for code, items in groupby(active_formulas_sorted, key=lambda f: f.code):
            group_list = list(items)
            is_collapsed = len(group_list) > 1
            formula_groups.append({
                'code': code,
                'formulas': group_list,
                'is_collapsed': is_collapsed,
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

        # 关联工单列表
        related_orders = []
        if selected_formula:
            order_details = ProductionOrderFormulaDetail.objects.filter(
                formula=selected_formula
            ).select_related(
                'production_order__creator',
                'production_order__project',
            )
            related_orders = [
                {
                    'code': d.production_order.code,
                    'status': d.production_order.get_status_display(),
                    'status_css': d.production_order.STATUS_CSS_MAP.get(d.production_order.status, 'bg-secondary-lt'),
                    'status_dot': d.production_order.STATUS_DOT_MAP.get(d.production_order.status, 'bg-secondary'),
                    'planned_quantity': d.planned_quantity,
                    'quantity_actual': d.production_order.quantity_actual,
                    'creator': d.production_order.creator.username,
                    'created_at': d.production_order.created_at,
                    'scheduled_date': d.production_order.extrusion_scheduled_date,
                    'scheduled_end': d.production_order.extrusion_scheduled_end,
                    'pk': d.production_order.pk,
                }
                for d in order_details
            ]

        # 测试结果 Tab 数据（手动录入 + 各工单回写）
        test_result_tabs = []
        if selected_formula:
            # 手动录入 tab
            manual_results = [
                r for r in selected_formula.test_results.all()
                if r.production_order_id is None
            ]
            manual_results.sort(key=lambda r: (
                r.test_config.category.order,
                r.test_config.order,
            ))
            test_result_tabs.append({
                'label': '手动录入',
                'tab_id': 'tab-manual',
                'results': manual_results,
                'type': 'manual',
            })

            # 各工单 tab
            order_results = [
                r for r in selected_formula.test_results.all()
                if r.production_order_id is not None
            ]
            order_results.sort(key=lambda r: (
                r.production_order.code,
                r.test_config.category.order,
                r.test_config.order,
            ))
            for order, items in groupby(order_results, key=lambda r: r.production_order):
                test_result_tabs.append({
                    'label': order.code,
                    'tab_id': f'tab-order-{order.pk}',
                    'results': list(items),
                    'type': 'order',
                    'order': order,
                })

        has_test_results = any(t['results'] for t in test_result_tabs)

        # 对比矩阵 (全局对比用全阶段配方，单tab对比用当前tab)
        compare_formulas = all_stage_formulas if global_compare else active_formulas
        columns, bom_matrix, test_matrix, cpbom_matrix = [], [], [], []
        if compare_mode and compare_formulas:
            columns, bom_matrix, test_matrix, cpbom_matrix = self._build_comparison_matrices(compare_formulas, material=material)

        # 客户竞品 Tab
        competitor_tab_active = self.request.GET.get('tab') == 'competitor'
        competitor_orders = []
        competitor_order_items = []
        selected_competitor_order = None
        if competitor_tab_active:
            from app_trial_production.models import ProductionOrder
            competitor_orders = ProductionOrder.objects.filter(
                project=project,
                skip_extrusion=True,
            ).select_related('creator').order_by('-created_at')

            # 侧边栏列表数据
            for o in competitor_orders:
                competitor_order_items.append({
                    'pk': o.pk,
                    'code': o.code,
                    'status': o.get_status_display(),
                    'status_css': o.STATUS_CSS_MAP.get(o.status, 'bg-secondary-lt'),
                    'status_dot': o.STATUS_DOT_MAP.get(o.status, 'bg-secondary'),
                    'creator': o.creator.username,
                    'created_at': o.created_at,
                    'quantity_planned': o.quantity_planned,
                })

            # 选中的竞品工单详情
            order_id_str = self.request.GET.get('order_id', '')
            if order_id_str:
                try:
                    selected_competitor_order = ProductionOrder.objects.filter(
                        pk=int(order_id_str), project=project, skip_extrusion=True,
                    ).select_related('creator', 'customer').prefetch_related(
                        'mold_requirements__mold',
                        'mold_requirements__formula_details',
                        'test_items__category',
                    ).first()
                except (ValueError, TypeError):
                    pass

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
            'columns': columns,
            'bom_matrix': bom_matrix,
            'test_matrix': test_matrix,
            'cpbom_matrix': cpbom_matrix,
            # 客户竞品 Tab
            'competitor_tab_active': competitor_tab_active,
            'competitor_orders': competitor_orders,
            'competitor_order_items': competitor_order_items,
            'selected_competitor_order': selected_competitor_order,
        })
        return context


class CompetitorOrderCreateView(ProjectAccessMixin, View):
    """客户竞品工单创建 — 直接关联项目，跳过挤出环节。"""

    model = Project
    pk_url_kwarg = 'pk'
    permission_required = 'app_project.view_project'

    def get(self, request, pk):
        project = self.get_object_or_deny()
        from app_material.models import TestConfig
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
        context = {
            'project': project,
            'grouped_test_items': grouped_test_items,
            'available_molds': available_molds,
            'preset_molds': preset_molds,
        }
        return render(request, 'apps/app_project/competitor_create.html', context)

    def post(self, request, pk):
        project = self.get_object_or_deny()

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

        if quantity_planned <= 0:
            messages.error(request, '计划数量必须大于 0')
            return redirect(reverse('project_formula_process', kwargs={'pk': pk}) + '?tab=competitor')

        # ── 解析模具行 ──
        mold_rows = self._parse_mold_rows(request.POST)
        valid_molds = [(int(mid), int(qty)) for mid, qty in mold_rows if mid and qty > 0]

        # ── 解析测试项目 ──
        test_item_ids = [int(tid) for tid in request.POST.getlist('test_items') if tid]

        # ── 创建工单 ──
        from app_trial_production.models import ProductionOrder
        from app_mold_injection.models import MoldRequirement

        with transaction.atomic():
            order = ProductionOrder.objects.create(
                project=project,
                quantity_planned=quantity_planned,
                injection_temperature=injection_temperature,
                injection_pretreatment=injection_pretreatment,
                packaging_desc=packaging_desc,
                storage_location=storage_location,
                competitor_company=competitor_company,
                competitor_brand=competitor_brand,
                competitor_model=competitor_model,
                customer_id=customer_id,
                skip_extrusion=True,
                creator=request.user,
            )

            # 模具需求
            for i, (mold_id, qty) in enumerate(valid_molds):
                mr = MoldRequirement.objects.create(
                    production_order=order,
                    mold_id=mold_id,
                    order=i,
                )
                # 竞品工单：每行创建一个 MoldRequirementFormulaDetail（formula=None）
                from app_mold_injection.models import MoldRequirementFormulaDetail
                MoldRequirementFormulaDetail.objects.create(
                    mold_requirement=mr,
                    formula=None,
                    specimen_quantity=qty,
                )

            # 测试项目
            if test_item_ids:
                order.test_items.set(test_item_ids)

        messages.success(
            request,
            f'竞品工单 [{order.code}] 已创建'
            f'（{len(valid_molds)} 个模具，跳过挤出直达注塑）'
        )
        return redirect(
            reverse('project_formula_process', kwargs={'pk': pk})
            + f'?tab=competitor&order_id={order.pk}'
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
