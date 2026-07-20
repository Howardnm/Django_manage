import logging

from django.db import transaction
from django.db.models import Sum
from django.forms import modelformset_factory
from django.utils.safestring import mark_safe
from django.views.generic import DetailView, CreateView, UpdateView, View
from django.shortcuts import redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from django.core.exceptions import PermissionDenied

from app_formula.models import LabFormula
from app_material.models import TestConfig
from app_mold_injection.models import MoldRequirement, MoldRequirementFormulaDetail, MoldType
from app_project.models import Project
from app_trial_production.mixins import TrialProductionAccessMixin, RndAccessMixin, ExtrusionTaskAccessMixin
from app_trial_production.models import ProductionOrder, SampleInventory, TrialProductionConfig
from app_trial_production.forms import (
    ProductionOrderForm, ProductionOrderUpdateForm, MoldRequirementRowFormSet,
)
from app_trial_production.services import ProductionOrderService
from app_user.models import User
from common_utils.state_machine import InvalidStateTransition

logger = logging.getLogger(__name__)


# ---- 共享辅助函数 ----

def _build_merged_bom(formulas, details_map=None):
    """将同实验单号下多个配方的BOM合并为多列比例展示结构。

    Returns: (rows, formula_totals, grand_total)
    """
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


def _build_bom_data(formulas):
    """构建供前端JS动态计算配料表的Python字典（由模板 json_script 序列化）。

    与 _build_merged_bom() 遍历相同的 BOM lines，但输出格式为前端 JS 优化。
    两者之间的 BOM line 遍历逻辑有重合，保持分离以避免 HTML 渲染数据过于复杂。
    """
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


def _build_grouped_test_items():
    """构建测试项目分组数据"""
    tests = TestConfig.objects.select_related('category').order_by('category__order', 'order')
    grouped = {}
    for t in tests:
        if t.category not in grouped:
            grouped[t.category] = {'category': t.category, 'items': []}
        grouped[t.category]['items'].append(t)
    return list(grouped.values())


def _save_mold_matrix(order, formset, formula_pks):
    """批量保存模具矩阵：delete-all-then-recreate。

    一行 formset form = 一个模具，变体列数据从 formset.get_variant_qtys() 读取。
    """
    order.mold_requirements.filter(injection_task__isnull=True).delete()
    for i, form in enumerate(formset):
        if form.cleaned_data.get('DELETE'):
            continue
        mold = form.cleaned_data.get('mold')
        if not mold:
            continue
        variant_qtys = formset.get_variant_qtys(i)
        if not variant_qtys:
            continue
        mr = MoldRequirement.objects.create(
            production_order=order, mold=mold, order=i,
        )
        for formula_pk, qty in variant_qtys.items():
            MoldRequirementFormulaDetail.objects.create(
                mold_requirement=mr,
                formula_id=formula_pk,
                specimen_quantity=qty,
            )


def _build_mold_formset_initial(order, formulas):
    """从现有 DB 数据构建 formset 初始值（纯函数，无副作用）。

    Returns:
        (queryset, variant_qty_map)
        queryset — 每个模具一行 MoldRequirement，供 formset queryset 参数
        variant_qty_map — {form_index: {formula_pk: quantity, ...}}，供模板回填变体列值
    """
    existing = list(order.mold_requirements.filter(
        injection_task__isnull=True,
    ).prefetch_related('formula_details').order_by('order', 'pk'))

    instances = []
    variant_qty_map = {}
    for i, mr in enumerate(existing):
        instances.append(mr)
        variant_qty_map[i] = {
            str(detail.formula_id): detail.specimen_quantity
            for detail in mr.formula_details.all()
        }
    queryset = MoldRequirement.objects.filter(
        pk__in=[i.pk for i in instances]
    ) if instances else MoldRequirement.objects.none()
    return queryset, variant_qty_map


def _build_variant_qty_map_from_post(post_data, formula_pks):
    """从 POST 数据提取变体列值，构建 {row_idx: {formula_pk_str: qty}} 映射。

    用于 POST 验证失败后回填变体列输入框，避免用户数据丢失。
    """
    total = int(post_data.get('mold-TOTAL_FORMS', 0))
    variant_qty_map = {}
    for i in range(total):
        for pk in formula_pks:
            key = f'variant_qty_{i}_{pk}'
            val = post_data.get(key, '')
            if val:
                try:
                    qty = int(val)
                except (ValueError, TypeError):
                    qty = 0
                if qty != 0:
                    variant_qty_map.setdefault(i, {})[str(pk)] = qty
    return variant_qty_map


def _build_mold_formset_error_message(formset):
    """构建 formset 验证错误信息"""
    lines = ['<div class="d-flex align-items-center gap-2 mb-2">'
             '<i class="ti ti-alert-triangle fs-4"></i>'
             '<strong>模具需求保存失败，请修正以下问题：</strong></div>']
    for e in formset.non_form_errors():
        lines.append(f'<div class="ms-4">• {e}</div>')
    for i, sf in enumerate(formset):
        if not sf.errors:
            continue
        for field_name, errs in sf.errors.items():
            label = sf[field_name].label if field_name in sf.fields else field_name
            for e in errs:
                lines.append(f'<div class="ms-4">• 第{i+1}行 {label}: {e}</div>')
    return mark_safe('\n'.join(lines)) if len(lines) > 1 else ''


# ---- 视图 ----

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
            qs = self.model.objects.all()
        return qs.select_related(
            'project__material', 'project_node', 'process_profile',
            'process_profile__machine', 'process_profile__screw_combination',
            'creator', 'extruder_operator', 'approved_by', 'workflow_instance',
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
            _build_merged_bom(formulas, details_map)
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
                injection.mold_requirements.prefetch_related('formula_details'), formulas)
        else:
            plans = order.mold_requirements.filter(
                injection_task__isnull=True,
            ).select_related('mold').prefetch_related('formula_details')
            if plans.exists():
                context['mold_matrix'] = self._build_mold_matrix(
                    plans, formulas, is_pending=True)

        # 是否已完成颗粒分拨（控制分拨按钮显隐 + 注塑任务触发屏障）
        context['has_pellet_splits'] = ext.pellet_split_completed if ext else False

        # 配方粒度的分拨明细
        existing_splits = SampleInventory.objects.filter(
            production_order=order, type='PELLET',
        ).values('formula_id', 'sub_type', 'batch_number').annotate(
            total_qty=Sum('quantity'),
        )
        split_map = {}
        batch_map = {}
        for s in existing_splits:
            key = (s['formula_id'], s['sub_type'])
            split_map[key] = float(s['total_qty'] or 0)
            if s['batch_number']:
                batch_map[s['formula_id']] = s['batch_number']

        formula_split_summaries = []
        for fd in details_map.values():
            finished_qty = split_map.get((fd.formula_id, 'FINISHED'), 0)
            for_injection_qty = split_map.get((fd.formula_id, 'FOR_INJECTION'), 0)
            formula_split_summaries.append({
                'formula': fd.formula,
                'planned_qty': float(fd.planned_quantity or 0),
                'finished_qty': finished_qty,
                'for_injection_qty': for_injection_qty,
                'total_split': finished_qty + for_injection_qty,
                'batch_number': batch_map.get(fd.formula_id, ''),
            })
        context['formula_split_summaries'] = formula_split_summaries

        # 操作权限：挤出操作员或超级用户可触发启动挤出
        context['can_start_extrusion'] = order.can_start_extrusion and (
            self.request.user.user_type == User.UserType.EXTRUSION_OPERATOR
            or self.request.user.is_superuser
        )

        return context

    @staticmethod
    def _build_mold_matrix(mold_requirements, formulas, is_pending=False):
        """构建模具×配方矩阵（详情页展示用）"""
        mold_map = {}
        for mr in mold_requirements:
            mold = mr.mold
            if mold.pk not in mold_map:
                mold_map[mold.pk] = {'mold': mold, 'quantities': {}, 'cells': []}
            for detail in mr.formula_details.all():
                mold_map[mold.pk]['quantities'][detail.formula_id] = detail.specimen_quantity
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
        result = {
            'mold_rows': mold_rows,
            'formulas': formulas,
            'formula_totals': formula_totals,
            'grand_total': grand_total,
        }
        if is_pending:
            result['is_pending'] = True
        return result

class ProductionOrderCreateView(RndAccessMixin, CreateView):
    """创建排产工单"""
    model = ProductionOrder
    form_class = ProductionOrderForm
    template_name = 'apps/app_trial_production/order/form.html'

    def get_initial(self):
        initial = super().get_initial()
        initial['quantity_planned'] = 0  # 默认值，JS 会根据计划产量动态更新
        initiate_data = self.request.session.get('trial_initiate_data')
        if initiate_data:
            initial['process_profile'] = initiate_data.get('process_profile_id')
            initial['sap_material_code'] = initiate_data.get('sap_material_code', '')
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_mode'] = 'create'
        context['formula_details_map'] = {}
        context['existing_test_item_ids'] = set()
        context['mold_types'] = MoldType.objects.filter(status='AVAILABLE').order_by('mold_code')
        initiate_data = self.request.session.get('trial_initiate_data')
        if initiate_data:
            context['initiate_data'] = initiate_data
            context['trial_code'] = initiate_data.get('trial_code', '')
            formulas = list(LabFormula.objects.filter(
                code=initiate_data.get('trial_code', ''),
                project_id=initiate_data.get('project_id'),
            ).prefetch_related('bom_lines__raw_material__category').order_by('version'))
            context['trial_formulas'] = formulas

            # BOM 合并展示 + JS 计算数据
            context['merged_bom_rows'] = _build_merged_bom(formulas)[0]
            context['bom_data'] = _build_bom_data(formulas)

            # 构建模具 formset（一行=一个模具，变体列由模板裸 <input> 渲染）
            formula_pks = [f.pk for f in formulas]
            test_molds = MoldType.objects.filter(
                status='AVAILABLE', mold_type='TEST_SPECIMEN',
            ).order_by('mold_code')

            if self.request.method == 'POST':
                context['mold_formset'] = MoldRequirementRowFormSet(
                    self.request.POST, prefix='mold', formula_pks=formula_pks)
                # 从 POST 数据恢复变体列值（验证失败时保留用户输入）
                context['variant_qty_map'] = _build_variant_qty_map_from_post(
                    self.request.POST, formula_pks,
                )
            else:
                initial = [{'mold': m} for m in test_molds]
                # Django modelformset 的 initial 分配给 extra 表单，
                # 因此 extra 必须 ≥ len(initial) 才能让预填行显示。
                from app_trial_production.forms import (
                    BaseMoldRequirementRowFormSet, MoldRequirementRowForm,
                )
                PrefillFormSet = modelformset_factory(
                    MoldRequirement,
                    form=MoldRequirementRowForm,
                    formset=BaseMoldRequirementRowFormSet,
                    extra=len(initial),
                    can_delete=True,
                )
                context['mold_formset'] = PrefillFormSet(
                    queryset=MoldRequirement.objects.none(),
                    initial=initial, prefix='mold', formula_pks=formula_pks,
                )
                context['variant_qty_map'] = {}
            context['formula_pks'] = formula_pks

        # 测试项目分组
        context['grouped_test_items'] = _build_grouped_test_items()
        return context


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

        # 测试项目
        test_item_ids = self.request.POST.getlist('test_items') or None

        # ★ 先校验模具 formset（仅读 POST 数据，无需事务），失败则直接返回表单
        mold_formset = MoldRequirementRowFormSet(
            self.request.POST, prefix='mold',
            formula_pks=[f['formula_id'] for f in formula_details],
        )
        if not mold_formset.is_valid():
            error_msg = _build_mold_formset_error_message(mold_formset)
            messages.error(self.request, error_msg)
            return self.form_invalid(form)

        with transaction.atomic():
            # 委托 Service 创建工单
            self.object = ProductionOrderService.create_order(
                user=self.request.user,
                trial_code=trial_code,
                project_id=project_id,
                project_node_id=project_node_id,
                process_profile_id=form.instance.process_profile_id,
                formula_details=formula_details,
                test_item_ids=test_item_ids,
                sap_material_code=form.cleaned_data.get('sap_material_code', ''),
                packaging_desc=form.cleaned_data.get('packaging_desc', ''),
                storage_location=form.cleaned_data.get('storage_location', ''),
                remark=form.cleaned_data.get('remark', ''),
            )

            # 保存模具矩阵
            _save_mold_matrix(
                self.object, mold_formset,
                [f['formula_id'] for f in formula_details],
            )

        self.request.session.pop('trial_initiate_data', None)
        messages.success(self.request, f'生产工单 {self.object.code} 创建成功')
        return redirect('trial_order_detail', pk=self.object.pk)


class ProductionOrderUpdateView(RndAccessMixin, UpdateView):
    """编辑排产工单（仅草稿状态可编辑）"""
    model = ProductionOrder
    form_class = ProductionOrderUpdateForm
    template_name = 'apps/app_trial_production/order/form.html'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.status != ProductionOrder.Status.DRAFT:
            raise PermissionDenied('仅草稿状态的工单可编辑')
        if obj.project:
            RndAccessMixin.check_project_ownership(obj.project, self.request.user)
        elif obj.creator_id != self.request.user.pk:
            raise PermissionDenied('您不是该工单的创建者')
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object
        context['page_mode'] = 'edit'

        context['mold_types'] = MoldType.objects.filter(status='AVAILABLE').order_by('mold_code')

        # 配方信息（从订单的 trial_code + project 查找）
        formulas = list(LabFormula.objects.filter(
            code=order.trial_code,
            project_id=order.project_id,
        ).prefetch_related('bom_lines__raw_material__category').order_by('version'))
        context['trial_formulas'] = formulas

        # 现有配方明细 → 预填计划产量 & 配色标记
        formula_details_map = {}
        for fd in order.formula_details.all():
            formula_details_map[fd.formula_id] = fd
        context['formula_details_map'] = formula_details_map

        # BOM 合并展示 + JS 计算数据
        context['merged_bom_rows'] = _build_merged_bom(formulas, formula_details_map)[0]
        context['bom_data'] = _build_bom_data(formulas)

        # 现有模具配置（从 mold_requirements 读取，构建 formset 初始值）
        formula_pks = [f.pk for f in formulas]
        context['formula_pks'] = formula_pks

        if self.request.method == 'POST':
            context['mold_formset'] = MoldRequirementRowFormSet(
                self.request.POST, prefix='mold', formula_pks=formula_pks)
            context['variant_qty_map'] = _build_variant_qty_map_from_post(
                self.request.POST, formula_pks,
            )
        else:
            queryset, variant_qty_map = _build_mold_formset_initial(order, formulas)
            context['mold_formset'] = MoldRequirementRowFormSet(
                queryset=queryset, prefix='mold', formula_pks=formula_pks)
            context['variant_qty_map'] = variant_qty_map

        # 已选测试项目 ID 集合
        context['existing_test_item_ids'] = set(
            order.test_items.values_list('pk', flat=True)
        )

        # 测试项目分组
        context['grouped_test_items'] = _build_grouped_test_items()

        return context

    def form_valid(self, form):
        # ★ 先校验模具 formset（仅读 POST 数据），失败则直接返回表单
        formula_pks = [fd.formula_id for fd in self.object.formula_details.all()]
        mold_formset = MoldRequirementRowFormSet(
            self.request.POST, prefix='mold', formula_pks=formula_pks)
        if not mold_formset.is_valid():
            error_msg = _build_mold_formset_error_message(mold_formset)
            messages.error(self.request, error_msg)
            return self.form_invalid(form)

        with transaction.atomic():
            order = form.save()

            # 更新配方明细 & 计划总产量
            total_qty = 0
            for fd in order.formula_details.all():
                qty_str = self.request.POST.get(f'planned_qty_{fd.formula_id}', '')
                if qty_str:
                    try:
                        fd.planned_quantity = float(qty_str)
                    except (ValueError, TypeError):
                        pass
                else:
                    fd.planned_quantity = 0
                fd.needs_color_matching = self.request.POST.get(
                    f'needs_color_{fd.formula_id}') == 'on'
                fd.save(update_fields=['planned_quantity', 'needs_color_matching'])
                total_qty += float(fd.planned_quantity or 0)

            # 保存模具矩阵（delete-all-then-recreate）
            _save_mold_matrix(order, mold_formset, formula_pks)

            # 更新测试项目
            test_item_ids = self.request.POST.getlist('test_items')
            if test_item_ids:
                order.test_items.set([int(tid) for tid in test_item_ids if tid.isdigit()])
            else:
                order.test_items.clear()

            order.quantity_planned = total_qty
            order.save(update_fields=['quantity_planned', 'updated_at'])

            logger.info(
                f"ProductionOrder {order.code} updated by {self.request.user}, "
                f"mold_plan_count={order.mold_requirements.filter(injection_task__isnull=True).count()}, "
                f"formula_count={order.formula_details.count()}, test_items={len(test_item_ids)}"
            )
        messages.success(self.request, '工单更新成功')
        return redirect('trial_order_detail', pk=order.pk)


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

        config = TrialProductionConfig.get()
        if not config.workflow_definition:
            messages.error(request, '未配置审批流程，请先在排产配置中设置')
            return redirect('trial_order_detail', pk=order.pk)

        try:
            ProductionOrderService.start_workflow(order, config.workflow_definition, request.user)
            messages.success(request, '审批流程已启动')
        except InvalidStateTransition as e:
            logger.exception(f"Workflow start failed for order {order.code}")
            messages.error(request, f'启动审批流程失败：{e}')
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

        formulas = LabFormula.objects.filter(
            code=trial_code, project_id=project_id,
        ).order_by('version')

        if not formulas.exists():
            messages.error(request, f'未找到实验单号 {trial_code} 的配方')
            return redirect(request.META.get('HTTP_REFERER', '/'))

        first = formulas.first()
        project_name = first.project.name if first.project else ''

        # 沿 配方→项目→成品材料 链查找 SAP 物料编码
        sap_material_code = ''
        if first.project and first.project.material:
            sap_material_code = first.project.material.sap_material_code or ''

        request.session['trial_initiate_data'] = {
            'trial_code': trial_code,
            'project_id': int(project_id) if project_id else None,
            'project_node_id': int(project_node_id) if project_node_id else None,
            'project_name': project_name,
            'formula_name': first.name,
            'process_profile_id': first.process_id,
            'material_type_id': first.material_type_id,
            'sap_material_code': sap_material_code,
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
        return redirect('trial_dashboard')


class ProductionOrderPrintView(TrialProductionAccessMixin, DetailView):
    """排产工单打印 — 输出 A4 HTML 打印页面"""
    model = ProductionOrder
    template_name = 'apps/app_trial_production/order/print_sheet.html'
    context_object_name = 'order'

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def get_queryset(self):
        qs = super().get_queryset()
        if qs is None:
            qs = self.model.objects.all()
        return qs.select_related(
            'project__material__category',
            'project__repository__customer',
            'project_node',
            'process_profile',
            'process_profile__machine',
            'process_profile__screw_combination',
            'creator', 'extruder_operator', 'approved_by',
        ).prefetch_related(
            'formula_details__formula',
            'mold_requirements__mold',
            'mold_requirements__formula_details',
            'sample_inventories',
        )

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        from app_trial_production.printing.renderer import (
            TrialProductionSheetRenderer,
        )
        renderer = TrialProductionSheetRenderer(production_order=self.object)
        return HttpResponse(renderer.render_html())


class ProductionOrderStartExtrusionView(ExtrusionTaskAccessMixin, View):
    """开始挤出 — 创建 ExtrusionTask + ColorMatchingTask，跳转挤出详情（仅挤出操作员）"""

    def post(self, request, pk):
        order = get_object_or_404(ProductionOrder, pk=pk, status='ACCEPTED')
        try:
            ProductionOrderService.start_extrusion(order, request.user)
            messages.success(request, f'工单 {order.code} 已开始挤出生产')
        except InvalidStateTransition as e:
            logger.exception(f"Failed to start extrusion for order {order.pk}")
            messages.error(request, f'开始挤出失败：{e}')
        return redirect('trial_order_detail', pk=pk)
