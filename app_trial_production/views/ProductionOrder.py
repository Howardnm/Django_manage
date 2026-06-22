from django.views.generic import ListView, DetailView, CreateView, UpdateView, View
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count
import logging
from app_trial_production.mixins import (
    TrialProductionAccessMixin, ExtrusionTaskAccessMixin, RndAccessMixin,
)
from app_trial_production.models import ProductionOrder
from app_mold_injection.models import MoldType
from app_trial_production.forms import (
    ProductionOrderForm, ProductionOrderUpdateForm,
)
from app_trial_production.services import ProductionOrderService

logger = logging.getLogger(__name__)


class ProductionOrderListView(TrialProductionAccessMixin, ListView):
    """挤出任务列表 — 仅显示生产中的工单"""
    model = ProductionOrder
    template_name = 'apps/app_trial_production/order/list.html'
    context_object_name = 'orders'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        if qs is None:
            return self.model.objects.all()
        return qs.filter(
            status='EXTRUDING',
        ).select_related(
            'project', 'creator', 'process_profile',
        ).prefetch_related(
            'formula_details__formula',
        ).annotate(
            formula_count=Count('formula_details'),
        ).order_by('-created_at')


class ProductionOrderDetailView(TrialProductionAccessMixin, DetailView):
    """排产工单详情"""
    model = ProductionOrder
    template_name = 'apps/app_trial_production/order/detail.html'
    context_object_name = 'order'

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def get_queryset(self):
        qs = super().get_queryset()
        if qs is None:
            return self.model.objects.all()
        return qs.select_related(
            'project', 'project_node', 'process_profile',
            'process_profile__machine', 'process_profile__screw_combination',
            'creator', 'extruder_operator', 'workflow_instance',
        ).prefetch_related(
            'formula_details__formula',
            'sample_inventories',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object

        # 子任务状态
        ext = getattr(order, 'extrusion_task', None)
        color = getattr(order, 'color_task', None)
        injection = getattr(order, 'injection_task', None)
        context['extrusion_task'] = ext
        context['color_task'] = color
        context['injection_task'] = injection

        # 测试任务
        context['testing_tasks'] = order.testing_tasks.all()

        # 配方信息
        from app_formula.models import LabFormula
        formulas = list(LabFormula.objects.filter(
            code=order.trial_code, project=order.project,
        ).select_related(
            'material_type', 'process', 'process__machine',
        ).prefetch_related(
            'bom_lines__raw_material__category',
            'color_powder_bom__entries__raw_material',
        ).order_by('version'))

        context['formulas'] = formulas
        details_map = {fd.formula_id: fd for fd in order.formula_details.all()}
        context['formula_pairs'] = [(f, details_map.get(f.pk)) for f in formulas]
        context['has_any_color_matching'] = any(
            fd.needs_color_matching for fd in details_map.values())

        # BOM 合并展示
        context['merged_bom_rows'], formula_totals_map, context['bom_grand_total'] = \
            self._build_merged_bom(formulas, details_map)
        context['bom_formula_columns'] = [
            {
                'version': f.version,
                'pk': f.pk,
                'planned_qty': details_map.get(f.pk).planned_quantity if details_map.get(f.pk) else 0,
                'total': formula_totals_map.get(f.pk, 0),
                'needs_color': details_map.get(f.pk).needs_color_matching if details_map.get(f.pk) else False,
            }
            for f, _ in context['formula_pairs']
        ]

        # 模具需求矩阵
        if injection:
            context['mold_matrix'] = self._build_mold_matrix(
                injection.mold_requirements.all(), formulas)

        # 样品库存汇总
        from app_trial_production.services import SampleInventoryService
        context['pellet_summary'] = SampleInventoryService.get_pellet_summary(order.trial_code)
        context['specimen_summary'] = SampleInventoryService.get_specimen_summary(order.trial_code)

        # 操作权限
        from app_user.models import User
        from app_user.mixins import IdentityConfig
        user = self.request.user
        context['can_start_extrusion'] = order.can_start_extrusion and (
            user.user_type == User.UserType.EXTRUSION_OPERATOR
            or user.user_type in IdentityConfig.TECH_CORE
        )

        return context

    @staticmethod
    def _build_mold_matrix(mold_requirements, formulas):
        """构建模具×配方矩阵"""
        mold_map = {}
        for mr in mold_requirements:
            mold = mr.mold
            if mold.pk not in mold_map:
                mold_map[mold.pk] = {'mold': mold, 'quantities': {}, 'cells': []}
            mold_map[mold.pk]['quantities'][mr.formula_id] = mr.specimen_quantity
        mold_rows = list(mold_map.values())
        for row in mold_rows:
            row_total = 0
            for f in formulas:
                qty = row['quantities'].get(f.pk, 0)
                row['cells'].append({'formula_pk': f.pk, 'qty': qty})
                row_total += qty
            row['row_total'] = row_total
        formula_totals = []
        grand_total = 0
        for f in formulas:
            total = sum(row['quantities'].get(f.pk, 0) for row in mold_rows)
            formula_totals.append({'formula_pk': f.pk, 'total': total})
            grand_total += total
        return {
            'mold_rows': mold_rows,
            'formulas': formulas,
            'formula_totals': formula_totals,
            'grand_total': grand_total,
        }

    @staticmethod
    def _build_merged_bom(formulas, details_map=None):
        """合并多配方BOM为多列展示"""
        if not formulas:
            return [], {}, 0
        details_map = details_map or {}
        base_formula = formulas[0]
        rows = []
        formula_totals = {f.pk: 0 for f in formulas}
        grand_total = 0
        for base_line in base_formula.bom_lines.all():
            raw_id = base_line.raw_material_id
            pct_columns = []
            row_total = 0
            for f in formulas:
                pct = ''
                for bl in f.bom_lines.all():
                    if bl.raw_material_id == raw_id and bl.feeding_port == base_line.feeding_port:
                        pct = bl.percentage
                        break
                fd = details_map.get(f.pk)
                planned_qty = float(fd.planned_quantity) if fd else 0
                pct_val = float(pct) if pct else 0
                feeding_qty = round((pct_val / 100) * planned_qty, 3) if planned_qty > 0 else 0
                formula_totals[f.pk] += feeding_qty
                row_total += feeding_qty
                pct_columns.append({
                    'version': f.version, 'value': pct, 'formula_pk': f.pk,
                    'feeding_qty': feeding_qty if planned_qty > 0 else 0,
                })
            grand_total += row_total
            rows.append({
                'feeding_port': base_line.get_feeding_port_display(),
                'raw_material': base_line.raw_material,
                'is_pre_mix': base_line.is_pre_mix,
                'pre_mix_order': base_line.pre_mix_order,
                'pre_mix_time': base_line.pre_mix_time,
                'weighing_scale': base_line.get_weighing_scale_display() if base_line.weighing_scale else '',
                'is_tail': base_line.is_tail,
                'pct_columns': pct_columns,
                'row_total': round(row_total, 3),
            })
        formula_totals = {k: round(v, 3) for k, v in formula_totals.items()}
        return rows, formula_totals, round(grand_total, 3)


class ProductionOrderCreateView(RndAccessMixin, CreateView):
    """创建排产工单"""
    model = ProductionOrder
    form_class = ProductionOrderForm
    template_name = 'apps/app_trial_production/order/create.html'

    def get_initial(self):
        initial = super().get_initial()
        initiate_data = self.request.session.get('trial_initiate_data')
        if initiate_data:
            initial['process_profile'] = initiate_data.get('process_profile_id')
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['mold_types'] = MoldType.objects.filter(status='AVAILABLE').order_by('mold_code')
        initiate_data = self.request.session.get('trial_initiate_data')
        if initiate_data:
            context['initiate_data'] = initiate_data
            context['trial_code'] = initiate_data.get('trial_code', '')
            from app_formula.models import LabFormula
            formulas = list(LabFormula.objects.filter(
                code=initiate_data.get('trial_code', ''),
                project_id=initiate_data.get('project_id'),
            ).prefetch_related('bom_lines__raw_material__category').order_by('version'))
            context['trial_formulas'] = formulas

            # 测试样条模具（预填充注塑矩阵）
            context['test_specimen_molds'] = MoldType.objects.filter(
                status='AVAILABLE', mold_type='TEST_SPECIMEN',
            ).order_by('mold_code')

            # BOM 合并展示 + JS 计算数据
            context['merged_bom_rows'] = self._build_merged_bom(formulas)
            context['bom_data'] = self._build_bom_data(formulas)

        # 测试项目分组
        from app_material.models import TestConfig
        tests = TestConfig.objects.select_related('category').order_by('category__order', 'order')
        grouped = {}
        for t in tests:
            if t.category not in grouped:
                grouped[t.category] = {'category': t.category, 'items': []}
            grouped[t.category]['items'].append(t)
        context['grouped_test_items'] = list(grouped.values())
        return context

    @staticmethod
    def _build_merged_bom(formulas):
        """将同实验单号下多个配方的BOM合并为多列比例展示结构（创建页简化版）"""
        if not formulas:
            return []
        base_formula = formulas[0]
        rows = []
        for base_line in base_formula.bom_lines.all():
            raw_id = base_line.raw_material_id
            pct_columns = []
            for f in formulas:
                pct = ''
                for bl in f.bom_lines.all():
                    if bl.raw_material_id == raw_id and bl.feeding_port == base_line.feeding_port:
                        pct = bl.percentage
                        break
                pct_columns.append({'version': f.version, 'value': pct, 'formula_pk': f.pk})
            rows.append({
                'feeding_port': base_line.get_feeding_port_display(),
                'raw_material': base_line.raw_material,
                'is_pre_mix': base_line.is_pre_mix,
                'pre_mix_order': base_line.pre_mix_order,
                'pre_mix_time': base_line.pre_mix_time,
                'weighing_scale': base_line.get_weighing_scale_display() if base_line.weighing_scale else '',
                'is_tail': base_line.is_tail,
                'pct_columns': pct_columns,
            })
        return rows

    @staticmethod
    def _build_bom_data(formulas):
        """构建供前端JS动态计算配料表的Python字典（由模板 json_script 序列化）"""
        if not formulas:
            return {'formulas': [], 'rows': []}
        rows = []
        base_formula = formulas[0]
        for base_line in base_formula.bom_lines.all():
            raw_id = base_line.raw_material_id
            percentages = {}
            for f in formulas:
                pct = 0
                for bl in f.bom_lines.all():
                    if bl.raw_material_id == raw_id and bl.feeding_port == base_line.feeding_port:
                        pct = float(bl.percentage)
                        break
                percentages[str(f.pk)] = pct
            rows.append({'percentages': percentages})
        return {
            'formulas': [{'pk': str(f.pk), 'version': f.version} for f in formulas],
            'rows': rows,
        }

    def form_valid(self, form):
        initiate_data = self.request.session.get('trial_initiate_data') or {}
        trial_code = self.request.POST.get('trial_code') or initiate_data.get('trial_code', '')
        project_id = self.request.POST.get('project_id') or initiate_data.get('project_id')
        project_node_id = self.request.POST.get('project_node_id') or initiate_data.get('project_node_id')

        if project_id:
            from app_project.models import Project
            project = get_object_or_404(Project, pk=project_id)
            RndAccessMixin.check_project_ownership(project, self.request.user)

        # 构建配方明细
        from app_formula.models import LabFormula
        formulas = list(LabFormula.objects.filter(
            code=trial_code, project_id=project_id,
        ).order_by('version'))

        formula_details = []
        for f in formulas:
            qty_str = self.request.POST.get(f'planned_qty_{f.pk}', '0')
            try:
                qty = float(qty_str)
            except (ValueError, TypeError):
                qty = 0
            needs_cm = self.request.POST.get(f'needs_color_{f.pk}') == 'on'
            formula_details.append({
                'formula_id': f.pk,
                'planned_quantity': qty,
                'needs_color_matching': needs_cm,
            })

        # 构建模具矩阵
        mold_matrix = []
        mold_count = int(self.request.POST.get('mold_count', 0))
        for i in range(mold_count):
            mold_id = self.request.POST.get(f'mold_{i}')
            if not mold_id:
                continue
            formula_quantities = {}
            for formula in formulas:
                qty_val = self.request.POST.get(f'qty_{i}_{formula.pk}', '0')
                try:
                    qty = int(qty_val)
                except (ValueError, TypeError):
                    qty = 0
                if qty > 0:
                    formula_quantities[str(formula.pk)] = qty
            if formula_quantities:
                mold_matrix.append({
                    'mold_id': int(mold_id),
                    'formula_quantities': formula_quantities,
                })

        # 测试项目
        test_item_ids = self.request.POST.getlist('test_items') or None

        # 委托 Service 创建
        self.object = ProductionOrderService.create_order(
            user=self.request.user,
            trial_code=trial_code,
            project_id=project_id,
            project_node_id=project_node_id,
            process_profile_id=form.instance.process_profile_id,
            formula_details=formula_details,
            test_item_ids=test_item_ids,
            mold_matrix=mold_matrix,
            remark=form.cleaned_data.get('remark', ''),
        )

        self.request.session.pop('trial_initiate_data', None)
        messages.success(self.request, f'生产工单 {self.object.code} 创建成功')
        return redirect('trial_order_detail', pk=self.object.pk)


class ProductionOrderUpdateView(ExtrusionTaskAccessMixin, UpdateView):
    """编辑排产工单"""
    model = ProductionOrder
    form_class = ProductionOrderUpdateForm
    template_name = 'apps/app_trial_production/order/edit.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['formula_details'] = self.object.formula_details.select_related(
            'formula').order_by('formula__version')
        return context

    def form_valid(self, form):
        self.object = form.save()
        for fd in self.object.formula_details.all():
            qty_str = self.request.POST.get(f'planned_qty_{fd.formula_id}', '')
            if qty_str:
                try:
                    fd.planned_quantity = float(qty_str)
                except (ValueError, TypeError):
                    pass
            fd.needs_color_matching = self.request.POST.get(
                f'needs_color_{fd.formula_id}') == 'on'
            fd.save(update_fields=['planned_quantity', 'needs_color_matching'])
        messages.success(self.request, '工单更新成功')
        return redirect('trial_order_detail', pk=self.object.pk)


class ProductionOrderStartWorkflowView(RndAccessMixin, View):
    """DRAFT → 发起审批流程（仅研发人员）"""

    def post(self, request, pk):
        order = get_object_or_404(ProductionOrder, pk=pk)
        if not order.can_start_workflow:
            messages.warning(request, '当前状态不可发起审批')
            return redirect('trial_order_detail', pk=order.pk)

        if order.project:
            RndAccessMixin.check_project_ownership(order.project, request.user)
        elif order.creator_id != request.user.pk:
            raise PermissionDenied("您不是该工单的创建者")

        from app_trial_production.models import TrialProductionConfig
        config = TrialProductionConfig.get()
        if not config.workflow_definition:
            messages.error(request, '未配置审批流程，请先在排产配置中设置')
            return redirect('trial_order_detail', pk=order.pk)

        try:
            ProductionOrderService.start_workflow(order, config.workflow_definition, request.user)
            messages.success(request, '审批流程已启动')
        except Exception:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception(f"Workflow start failed for order {order.code}")
            messages.error(request, '启动审批流程时发生错误，请稍后重试')
        return redirect('trial_order_detail', pk=order.pk)


class ProductionOrderInitiateView(RndAccessMixin, View):
    """从配方过程页点击'试验排产'按钮"""

    def post(self, request):
        trial_code = request.POST.get('trial_code')
        project_id = request.POST.get('project_id')
        project_node_id = request.POST.get('project_node_id')

        if project_id:
            from app_project.models import Project
            project = get_object_or_404(Project, pk=project_id)
            RndAccessMixin.check_project_ownership(project, request.user)

        from app_formula.models import LabFormula
        formulas = LabFormula.objects.filter(
            code=trial_code, project_id=project_id,
        ).order_by('version')

        if not formulas.exists():
            messages.error(request, f'未找到实验单号 {trial_code} 的配方')
            return redirect(request.META.get('HTTP_REFERER', '/'))

        first = formulas.first()
        project_name = first.project.name if first.project else ''
        request.session['trial_initiate_data'] = {
            'trial_code': trial_code,
            'project_id': int(project_id) if project_id else None,
            'project_node_id': int(project_node_id) if project_node_id else None,
            'project_name': project_name,
            'formula_name': first.name,
            'process_profile_id': first.process_id,
            'material_type_id': first.material_type_id,
        }
        return redirect('trial_order_create')


class ProductionOrderDeleteView(TrialProductionAccessMixin, View):
    """删除草稿工单 — 仅创建人或超级用户可操作"""

    def post(self, request, pk):
        order = get_object_or_404(ProductionOrder, pk=pk)

        if order.status != ProductionOrder.Status.DRAFT:
            messages.error(request, '只有草稿状态的工单才能删除')
            return redirect('trial_order_detail', pk=order.pk)

        if not (request.user.is_superuser or order.creator_id == request.user.pk):
            raise PermissionDenied('您不是该工单的创建者，无权删除')

        order_code = order.code
        order.delete()
        messages.success(request, f'草稿工单 {order_code} 已删除')
        return redirect('trial_order_list')


class ProductionOrderStartExtrusionView(RndAccessMixin, View):
    """开始挤出 — 创建 ExtrusionTask + ColorMatchingTask，跳转挤出详情"""

    def post(self, request, pk):
        order = get_object_or_404(ProductionOrder, pk=pk, status='ACCEPTED')
        try:
            ProductionOrderService.start_extrusion(order, request.user)
            messages.success(request, f'工单 {order.code} 已开始挤出生产')
        except Exception:
            logger.exception(f"Failed to start extrusion for order {order.pk}")
            messages.error(request, '开始挤出失败，请稍后重试')
        return redirect('trial_extrusion_detail', order_pk=pk)
