from collections import OrderedDict
from itertools import groupby
from django.views.generic import DetailView
from app_project.mixins import ProjectAccessMixin
from app_project.models import Project, ProjectStage, ProjectNode
from app_formula.models import LabFormula
from app_trial_production.models.production_order import ProductionOrderFormulaDetail


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
        })
        return context
