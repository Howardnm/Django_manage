from collections import OrderedDict
from itertools import groupby
from django.views.generic import ListView, View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from app_trial_production.mixins import ColorTaskAccessMixin
from app_trial_production.models import ProductionOrder
from app_project.models import ProjectStage
from app_formula.models import LabFormula, ColorPowderBOM, ColorPowderBOMEntry
from app_trial_production.forms import ColorPowderBOMForm, ColorPowderBOMEntryFormSet


class ColorPowderBOMListView(ColorTaskAccessMixin, ListView):
    """显示需要配色的工单列表"""
    model = ProductionOrder
    template_name = 'apps/app_trial_production/color/list.html'
    context_object_name = 'orders'

    def get_queryset(self):
        return ProductionOrder.objects.filter(
            formula_details__needs_color_matching=True,
            status__in=ProductionOrder.POST_EXTRUSION_STATUSES,
        ).select_related(
            'project',
        ).distinct().order_by('-created_at')


class ColorPowderBOMFillView(ColorTaskAccessMixin, View):
    """填写色粉配比 — 含项目配方过程视图（tab / 侧边栏 / 对比模式）"""
    template_name = 'apps/app_trial_production/color/fill.html'

    STAGE_ORDER = ['RND', 'PILOT', 'MID_TEST', 'MASS_PROD']

    def dispatch(self, request, *args, **kwargs):
        self.production_order = get_object_or_404(
            ProductionOrder.objects.select_related('project', 'project__material'),
            pk=kwargs['order_pk'],
        )
        return super().dispatch(request, *args, **kwargs)

    def _fetch_formulas(self, project, material):
        project_formulas = LabFormula.objects.filter(
            project=project,
            project_node__isnull=False,
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
                project__material=material,
                project_node__isnull=False,
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
        """构建色粉BOM对比矩阵"""
        if not formulas:
            return [], []

        formulas = sorted(formulas, key=lambda f: f.created_at)
        columns = [{'type': 'formula', 'obj': f} for f in formulas]

        # 收集所有色粉BOM条目中涉及到的原料，以及每个配方对应的百分比
        all_raw_materials = set()
        cpbom_map = {}  # {formula_id: {raw_material_id: entry}}
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

    def get(self, request, *args, **kwargs):
        project = self.production_order.project
        material = project.material if project else None

        all_formulas = self._fetch_formulas(project, material)

        # 按 stage + round 分组
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
            active_stage = active_item['stage']
            active_round = active_item['round']
            active_formulas = active_item['formulas']
        else:
            active_formulas = []

        # 按 code 分组（侧边栏折叠）
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

        compare_mode = request.GET.get('compare') == '1'
        global_compare = compare_mode and not request.GET.get('stage')

        selected_formula = None
        selected_formula_id = request.GET.get('formula_id')
        if selected_formula_id and not compare_mode:
            try:
                selected_formula = next(
                    f for f in active_formulas if str(f.pk) == selected_formula_id
                )
            except StopIteration:
                pass
        if not selected_formula and active_formulas:
            selected_formula = active_formulas[0]

        if selected_formula:
            for g in formula_groups:
                if any(f.pk == selected_formula.pk for f in g['formulas']):
                    g['is_collapsed'] = False
                    break

        # 选中配方的测试结果 (不再显示)
        # 对比矩阵 — 仅色粉BOM
        compare_formulas = all_stage_formulas if global_compare else active_formulas
        cpbom_columns, cpbom_matrix = [], []
        if compare_mode and compare_formulas:
            cpbom_columns, cpbom_matrix = self._build_color_powder_bom_matrix(compare_formulas)

        # 色粉BOM（原有逻辑）
        bom = None
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
            'production_order': self.production_order,
            'project': project,
            'material': material,
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
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        formula_id = request.POST.get('formula_id')
        selected_formula = get_object_or_404(LabFormula, pk=formula_id)

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
            return redirect(
                f'{request.path}?formula_id={selected_formula.pk}'
            )

        # POST 失败时重建 context
        project = self.production_order.project
        material = project.material if project else None
        all_formulas = self._fetch_formulas(project, material)
        all_stage_formulas = [f for f in all_formulas if f.project_node]

        active_formulas = all_stage_formulas
        formula_groups = []
        sorted_active = sorted(active_formulas, key=lambda f: (f.code or '', f.version))
        for code, items in groupby(sorted_active, key=lambda f: f.code):
            group_list = list(items)
            formula_groups.append({
                'code': code,
                'formulas': group_list,
                'is_collapsed': len(group_list) > 1,
            })

        return render(request, self.template_name, {
            'production_order': self.production_order,
            'project': project,
            'material': material,
            'stage_round_items': [],
            'active_stage': self.STAGE_ORDER[0],
            'active_round': None,
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
            'bom_entries': None,
            'readonly': False,
        })
