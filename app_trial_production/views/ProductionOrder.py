from django.views.generic import ListView, DetailView, CreateView, UpdateView, View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse
from app_trial_production.mixins import (
    TrialProductionAccessMixin, ExtrusionTaskAccessMixin, RndAccessMixin,
)
from app_user.models import User
from app_user.mixins import IdentityConfig
from app_trial_production.models import ProductionOrder, MoldRequirement, InjectionMoldingOrder, MoldType, ProductionOrderFormulaDetail
from app_trial_production.forms import (
    ProductionOrderForm, ProductionOrderUpdateForm,
)


class ProductionOrderListView(TrialProductionAccessMixin, ListView):
    model = ProductionOrder
    template_name = 'apps/app_trial_production/order/list.html'
    context_object_name = 'orders'
    paginate_by = 20

    def get_queryset(self):
        return ProductionOrder.objects.exclude(
            status__in=ProductionOrder.HIDDEN_STATUSES,
        ).select_related(
            'project', 'creator', 'process_profile',
        ).prefetch_related(
            'formula_details__formula',
        ).order_by('-created_at')


class ProductionOrderDetailView(TrialProductionAccessMixin, DetailView):
    model = ProductionOrder
    template_name = 'apps/app_trial_production/order/detail.html'
    context_object_name = 'order'

    def get_queryset(self):
        return ProductionOrder.objects.select_related(
            'project', 'project_node', 'process_profile',
            'process_profile__machine', 'process_profile__screw_combination',
            'creator', 'extruder_operator', 'workflow_instance',
        ).prefetch_related(
            'sample_splits',
            'injection_order__mold_requirements__mold',
            'injection_order__mold_requirements__formula',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object
        user = self.request.user
        user_groups = set(user.review_groups.filter(is_active=True).values_list('name', flat=True))
        context['show_rnd_bom'] = not ('配色部门' in user_groups)

        context['extrusion_statuses'] = ProductionOrder.EXTRUSION_READY_STATUSES
        context['post_extrusion_statuses'] = ProductionOrder.POST_EXTRUSION_STATUSES

        can_complete = order.status == 'EXTRUDING' and (
            user.user_type == User.UserType.EXTRUSION_OPERATOR
            or user.user_type in IdentityConfig.TECH_CORE
        )
        context['can_complete_extrusion'] = can_complete

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
        context['merged_bom_rows'], formula_totals_map, context['bom_grand_total'] = self._build_merged_bom(formulas, details_map)
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

        # 模具需求矩阵数据
        if order.injection_order:
            context['mold_matrix'] = self._build_mold_matrix(
                order.injection_order.mold_requirements.all(), formulas)

        return context

    @staticmethod
    def _build_mold_matrix(mold_requirements, formulas):
        """构建模具×配方矩阵，预计算所有模板需要的值"""
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
                    'version': f.version,
                    'value': pct,
                    'formula_pk': f.pk,
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
    model = ProductionOrder
    form_class = ProductionOrderForm
    template_name = 'apps/app_trial_production/order/create.html'

    def dispatch(self, request, *args, **kwargs):
        self.initiate_data = request.session.pop('trial_initiate_data', None)
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        if self.initiate_data:
            initial['process_profile'] = self.initiate_data.get('process_profile_id')
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['mold_types'] = MoldType.objects.filter(status='AVAILABLE').order_by('mold_code')
        context['test_specimen_molds'] = MoldType.objects.filter(
            status='AVAILABLE', mold_type='TEST_SPECIMEN',
        ).order_by('mold_code')
        if self.initiate_data:
            context['initiate_data'] = self.initiate_data
            context['trial_code'] = self.initiate_data.get('trial_code', '')
            from app_formula.models import LabFormula
            formulas = list(LabFormula.objects.filter(
                code=self.initiate_data.get('trial_code', ''),
                project_id=self.initiate_data.get('project_id'),
            ).prefetch_related(
                'bom_lines__raw_material__category',
            ).order_by('version'))
            context['trial_formulas'] = formulas
            context['merged_bom_rows'] = self._build_merged_bom(formulas)
            context['bom_data_json'] = self._build_bom_data_json(formulas)

        # 测试项目按 MetricCategory 分组
        from app_material.models import TestConfig, MetricCategory
        categories = MetricCategory.objects.all().order_by('order')
        grouped_tests = []
        for cat in categories:
            items = TestConfig.objects.filter(category=cat).order_by('order')
            if items.exists():
                grouped_tests.append({'category': cat, 'items': items})
        context['grouped_test_items'] = grouped_tests

        return context

    def _build_merged_bom(self, formulas):
        """将同实验单号下多个配方的BOM合并为多列比例展示结构"""
        if not formulas:
            return []

        # 以第一个配方的BOM行顺序为基准
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

    def _build_bom_data_json(self, formulas):
        """构建供前端JS动态计算配料表的JSON数据"""
        import json
        if not formulas:
            return '{}'

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

        data = {
            'formulas': [{'pk': str(f.pk), 'version': f.version} for f in formulas],
            'rows': rows,
        }
        return json.dumps(data, ensure_ascii=False)

    def form_valid(self, form):
        form.instance.creator = self.request.user
        trial_code = self.request.POST.get('trial_code') or (self.initiate_data or {}).get('trial_code', '')
        project_id = self.request.POST.get('project_id') or (self.initiate_data or {}).get('project_id')
        project_node_id = self.request.POST.get('project_node_id') or (self.initiate_data or {}).get('project_node_id')
        if trial_code:
            form.instance.trial_code = trial_code
        if project_id:
            form.instance.project_id = project_id
        if project_node_id:
            form.instance.project_node_id = project_node_id

        self.object = form.save()

        # 保存每个配方的计划产量和配色需求
        from app_formula.models import LabFormula
        formulas = list(LabFormula.objects.filter(
            code=self.object.trial_code, project=self.object.project,
        ).order_by('version'))

        total_qty = 0
        for f in formulas:
            qty_str = self.request.POST.get(f'planned_qty_{f.pk}', '0')
            try:
                qty = float(qty_str)
            except (ValueError, TypeError):
                qty = 0
            needs_cm = self.request.POST.get(f'needs_color_{f.pk}') == 'on'
            ProductionOrderFormulaDetail.objects.create(
                production_order=self.object,
                formula=f,
                planned_quantity=qty,
                needs_color_matching=needs_cm,
            )
            total_qty += qty

        # 更新工单总计划产量
        if total_qty > 0:
            self.object.quantity_planned = total_qty
            self.object.save(update_fields=['quantity_planned'])

        # 自动创建测试工单
        test_item_ids = self.request.POST.getlist('test_items')
        if test_item_ids:
            assigned_to_id = self.request.POST.get('assigned_to') or None
            from app_trial_production.models import TestingOrder
            TestingOrder.objects.create(
                production_order=self.object,
                status='PENDING',
                assigned_to_id=assigned_to_id,
            ).test_items.set(test_item_ids)

        # 处理模具 × 配方矩阵数据
        mold_count = int(self.request.POST.get('mold_count', 0))
        if mold_count > 0:
            has_any_mold = any(
                self.request.POST.get(f'mold_{i}') for i in range(mold_count)
            )
            if has_any_mold:
                injection_order = InjectionMoldingOrder.objects.create(
                    production_order=self.object,
                    status='PENDING',
                )
                for i in range(mold_count):
                    mold_id = self.request.POST.get(f'mold_{i}')
                    if not mold_id:
                        continue
                    try:
                        mold = MoldType.objects.get(pk=int(mold_id))
                    except (MoldType.DoesNotExist, ValueError):
                        continue

                    for formula in formulas:
                        qty_val = self.request.POST.get(f'qty_{i}_{formula.pk}', '0')
                        try:
                            qty = int(qty_val)
                        except (ValueError, TypeError):
                            qty = 0
                        if qty > 0:
                            MoldRequirement.objects.create(
                                injection_order=injection_order,
                                mold=mold,
                                formula=formula,
                                specimen_quantity=qty,
                            )

        messages.success(self.request, f'生产工单 {self.object.code} 创建成功')
        return redirect('trial_production_order_detail', pk=self.object.pk)


class ProductionOrderUpdateView(ExtrusionTaskAccessMixin, UpdateView):
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

        # 更新每个配方的计划产量和配色需求
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
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('trial_production_order_detail', kwargs={'pk': self.object.pk})


class ProductionOrderStartWorkflowView(RndAccessMixin, View):
    """DRAFT状态的工单 → 发起审批流程 (仅研发人员)"""

    def post(self, request, pk):
        order = get_object_or_404(ProductionOrder, pk=pk)
        if not order.can_start_workflow:
            messages.warning(request, '当前状态不可发起审批')
            return redirect('trial_production_order_detail', pk=order.pk)

        if order.project and not RndAccessMixin.check_project_ownership(order.project, request.user):
            messages.error(request, '无权操作该项目的排产单')
            return redirect('trial_production_order_detail', pk=order.pk)

        from app_trial_production.models import TrialProductionConfig
        from app_trial_production.services import TrialProductionService

        config = TrialProductionConfig.get()
        if not config.workflow_definition:
            messages.error(request, '未配置审批流程，请先在排产配置中设置')
            return redirect('trial_production_order_detail', pk=order.pk)

        TrialProductionService.start_workflow(
            order, config.workflow_definition, request.user)
        messages.success(request, '审批流程已启动')
        return redirect('trial_production_order_detail', pk=order.pk)


class ProductionOrderCompleteExtrusionView(ExtrusionTaskAccessMixin, View):
    """完成挤出 → EXTRUDING 流转到 COLOR_POST (仅挤出操作员和技术核心)"""

    def post(self, request, pk):
        order = get_object_or_404(ProductionOrder, pk=pk)
        if order.status != 'EXTRUDING':
            messages.warning(request, '当前状态不可完成挤出')
            return redirect('trial_production_order_detail', pk=order.pk)

        has_color = order.formula_details.filter(needs_color_matching=True).exists()
        if has_color:
            order.status = 'COLOR_POST'
            msg = '挤出完成，工单已流转至配色阶段'
        else:
            order.status = 'SAMPLE_SPLITTING'
            msg = '挤出完成，无需配色，工单已流转至样品分拨阶段'
        order.save(update_fields=['status', 'updated_at'])
        messages.success(request, msg)
        return redirect('trial_production_order_detail', pk=order.pk)


class ProductionOrderInitiateView(RndAccessMixin, View):
    """从配方过程页点击'试验排产'按钮，传入实验单号创建工单 (仅研发人员)"""

    def post(self, request):
        trial_code = request.POST.get('trial_code')
        project_id = request.POST.get('project_id')
        project_node_id = request.POST.get('project_node_id')

        # 验证项目归属：只允许项目负责人或项目成员发起排产
        if project_id:
            from app_project.models import Project
            project = get_object_or_404(Project, pk=project_id)
            if not RndAccessMixin.check_project_ownership(project, request.user):
                messages.error(request, '您不是该项目的负责人或成员，无法创建排产单')
                return redirect(request.META.get('HTTP_REFERER', '/'))

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
        return redirect('trial_production_order_create')
