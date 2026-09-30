"""
产品报价需求单视图层。

Views:
    QuotationListView       — 需求单列表
    QuotationCreateView     — 发起报价（步骤①）
    QuotationDetailView     — 单页面：卡片 + 审批栏 + 流程图 + 审批意见
    QuotationStepActionView — 各步骤填写/审批提交
    QuotationReturnView     — 退回
    QuotationReassignView   — 移交
    QuotationPrintView      — OA 核价申请单打印
"""

import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import DetailView, FormView, ListView, View

from app_workflow.models import WorkflowTask
from app_workflow.services import WorkflowService
from app_workflow.views import build_workflow_status_map
from common_utils.printing.mixins import PrintableMixin

from .filters import QuotationFilter
from .forms import QuotationCreateForm
from .mixins import QuotationAccessMixin
from .models import QuotationBOM, QuotationField, QuotationMaterialPrice, QuotationRequest
from .printing.renderer import QuotationPrintRenderer
from .services import (
    STEP_LABELS,
    STEP_TASKS,
    TASK_COST,
    TASK_CUSTOMER_PRICE,
    TASK_PURCHASE_PRICE,
    TASK_RD_SELECT,
    TASK_SELECT_BOM,
    QuotationService,
)

logger = logging.getLogger(__name__)


class QuotationListView(QuotationAccessMixin, ListView):
    """产品报价需求单列表。"""
    model = QuotationRequest
    template_name = 'apps/app_quotation/list.html'
    context_object_name = 'quotations'
    paginate_by = 20
    permission_required = 'app_quotation.view_quotationrequest'

    def get_queryset(self):
        qs = super().get_queryset()
        if qs is None:
            qs = self.model.objects.all()
        qs = qs.select_related(
            'finished_material', 'customer', 'business_group', 'subsidiary', 'creator',
        )
        self.filter = QuotationFilter(self.request.GET, queryset=qs)
        return self.filter.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filter
        return context


class QuotationCreateView(QuotationAccessMixin, FormView):
    """步骤① 发起报价。"""
    form_class = QuotationCreateForm
    template_name = 'apps/app_quotation/create.html'
    permission_required = 'app_quotation.add_quotationrequest'

    # FK 固定字段的渲染顺序（其余按 QuotationField.group 分区）
    FK_FIELDS = ('finished_material', 'product_name', 'product_type',
                 'customer', 'business_group', 'subsidiary', 'salesperson')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_sections'] = self._build_form_sections(context['form'])
        return context

    def _build_form_sections(self, form):
        """按分区把表单字段组织成「4 个/行」的表格结构（不足用 None 补齐）。

        返回 [{'name': str, 'rows': [[BoundField|None, …], …]}, …]。
        FK 路由字段归入「基本信息」分区（与详情页 meta 分区同名，天然合并）。
        """
        sections, index = [], {}

        def get_section(name):
            if name not in index:
                index[name] = {'name': name, 'fields': []}
                sections.append(index[name])
            return index[name]

        for name in self.FK_FIELDS:
            if name in form.fields:
                get_section('基本信息')['fields'].append(form[name])
        for f in QuotationField.objects.filter(is_active=True).order_by('order', 'id'):
            if f.key not in form.fields:
                continue
            get_section(f.group or '其他')['fields'].append(form[f.key])  # BoundField

        result = []
        for s in sections:
            fields = s['fields']
            rows = []
            for i in range(0, len(fields), 4):
                row = fields[i:i + 4]
                row += [None] * (4 - len(row))
                rows.append(row)
            result.append({'name': s['name'], 'rows': rows})
        return result

    def form_valid(self, form):
        # FK 字段 → 模型
        self.object = QuotationRequest(
            finished_material=form.cleaned_data['finished_material'],
            customer=form.cleaned_data['customer'],
            business_group=form.cleaned_data['business_group'],
            subsidiary=form.cleaned_data['subsidiary'],
            salesperson=form.cleaned_data.get('salesperson'),
            creator=self.request.user,
        )

        # 动态字段 → form_data 快照（number/date 转字符串保精度）
        self.object.form_data = self._serialize_form_data(form)
        self.object.save()

        definition = QuotationService.get_workflow_definition()
        if definition is None:
            messages.error(self.request, '未找到报价审批流程定义，请先在流程模块创建并启用。')
            self.object.delete()
            return self.form_invalid(form)

        QuotationService.start_flow(self.object, definition)
        messages.success(self.request, f'需求单「{self.object.code}」已发起，进入审批流程。')
        return redirect('quotation_detail', pk=self.object.pk)

    def _serialize_form_data(self, form):
        """把动态字段序列化进 form_data 快照（number/date 转字符串保精度）。"""
        form_data = {}
        for field in QuotationField.objects.filter(is_active=True):
            value = form.cleaned_data.get(field.key)
            if value in (None, ''):
                continue
            if field.field_type == QuotationField.FieldType.DATE:
                value = value.isoformat()
            elif field.field_type == QuotationField.FieldType.NUMBER:
                value = str(value)
            form_data[field.key] = value
        return form_data


class QuotationEditView(QuotationCreateView):
    """退回修订：发起者编辑基本信息后重新提交，重启审批流。"""
    permission_required = 'app_quotation.change_quotationrequest'

    def dispatch(self, request, *args, **kwargs):
        self.object = get_object_or_404(QuotationRequest, pk=kwargs['pk'])
        self.check_object_permission(self.object)
        if request.user.pk != self.object.creator_id:
            raise PermissionDenied('只有发起人可以重新填写。')
        if not self.object.needs_revision:
            messages.error(request, '该需求单不处于退回修订状态。')
            return redirect('quotation_detail', pk=self.object.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        q = self.object
        initial = {
            'finished_material': q.finished_material_id,
            'customer': q.customer_id,
            'business_group': q.business_group_id,
            'subsidiary': q.subsidiary_id,
            'salesperson': q.salesperson_id or '',
            'product_name': q.finished_material.grade_name,
            'product_type': (q.finished_material.category.name
                             if q.finished_material.category_id else ''),
        }
        initial.update(q.form_data or {})  # 动态字段快照（date 已 isoformat、number 已 str）
        kwargs['initial'] = initial
        return kwargs

    def form_valid(self, form):
        q = self.object
        q.finished_material = form.cleaned_data['finished_material']
        q.customer = form.cleaned_data['customer']
        q.business_group = form.cleaned_data['business_group']
        q.subsidiary = form.cleaned_data['subsidiary']
        q.salesperson = form.cleaned_data.get('salesperson')
        q.form_data = self._serialize_form_data(form)
        q.save()

        # 清理上一次审批残留，重新走流程
        q.boms.all().delete()
        q.material_prices.all().delete()
        q.marginal_cost = q.contribution_rate = q.customer_price = None
        q.save(update_fields=['marginal_cost', 'contribution_rate', 'customer_price'])

        WorkflowService.restart(q.workflow_instance, self.request.user, context_data={})
        q.status = QuotationRequest.Status.RUNNING
        q.save(update_fields=['status'])
        messages.success(self.request, f'需求单「{q.code}」已重新提交，进入审批流程。')
        return redirect('quotation_detail', pk=q.pk)


class QuotationDetailView(QuotationAccessMixin, DetailView):
    """单页面详情：按当前步骤门控卡片 + 审批栏 + 流程图 + 审批意见。"""
    model = QuotationRequest
    template_name = 'apps/app_quotation/detail.html'
    context_object_name = 'quotation'
    permission_required = 'app_quotation.view_quotationrequest'

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        quotation = self.object
        user = self.request.user

        current_task = quotation.current_task
        can_act = False
        if current_task and current_task.status == 'PENDING':
            can_act = (
                current_task.assigned_to_id == user.pk
                or current_task.candidate_users.filter(pk=user.pk).exists()
            )

        context['current_task'] = current_task
        context['can_act'] = can_act

        boms = list(quotation.boms.select_related('formula').order_by('pk'))
        cost_map = QuotationService.bom_cost_map(quotation)
        context['bom_rows'] = [{'bom': b, 'cost': cost_map.get(b.pk)} for b in boms]
        context['selected_formula_ids'] = list(
            quotation.boms.values_list('formula_id', flat=True))
        context['material_prices'] = quotation.material_prices.select_related('raw_material')

        instance = quotation.workflow_instance
        if instance is not None:
            context['bpmn_xml'] = instance.definition.bpmn_xml
            context['status_map'] = build_workflow_status_map(instance)
            context['history'] = instance.history.select_related('approver').order_by('timestamp')
            context['returnable_targets'] = current_task.returnable_targets if current_task else []
        else:
            context['bpmn_xml'] = ''
            context['status_map'] = {}
            context['history'] = []
            context['returnable_targets'] = []

        context['candidate_formulas'] = QuotationService.candidate_formulas(
            quotation.finished_material)
        bom_columns, bom_rows = QuotationService.bom_matrix(quotation.finished_material)
        context['bom_columns'] = bom_columns
        context['bom_rows'] = bom_rows
        # 只读矩阵：仅已复选的配方
        sel_columns, sel_rows = QuotationService.selected_bom_matrix(quotation)
        context['selected_bom_columns'] = sel_columns
        context['selected_bom_rows'] = sel_rows
        context['material_lines'] = QuotationService.material_lines(quotation)

        context['current_task_id'] = current_task.spiff_task_id if current_task else ''
        context['steps'] = self._build_step_progress(quotation)
        context['info_sections'] = quotation.get_info_sections()
        context['needs_revision'] = quotation.needs_revision
        context['is_creator'] = (user.pk == quotation.creator_id)
        context['show_bom_matrix'] = QuotationService.is_bom_matrix_viewer(quotation, user)
        # 步骤②可编辑态：can_act 且当前任务是选BOM
        context['edit_bom_matrix'] = (
            can_act and current_task is not None
            and current_task.spiff_task_id == TASK_SELECT_BOM
        )

        return context

    def _build_step_progress(self, quotation):
        """线性步骤进度（completed/current/pending）。"""
        instance = quotation.workflow_instance
        if instance is None:
            return []
        completed_ids = set(
            instance.tasks.filter(status='COMPLETED').values_list('spiff_task_id', flat=True))
        current_id = ''
        task = quotation.current_task
        if task:
            current_id = task.spiff_task_id
        steps = []
        for task_id in STEP_TASKS:
            if task_id in completed_ids:
                status = 'completed'
            elif task_id == current_id:
                status = 'current'
            else:
                status = 'pending'
            steps.append({'task_id': task_id, 'label': STEP_LABELS.get(task_id, task_id),
                          'status': status})
        return steps


class QuotationStepActionView(QuotationAccessMixin, View):
    """各步骤填写/审批的统一提交入口。"""
    permission_required = 'app_quotation.change_quotationrequest'

    def post(self, request, pk):
        quotation = get_object_or_404(QuotationRequest, pk=pk)
        self.check_object_permission(quotation)
        task = quotation.current_task
        if task is None or task.status != 'PENDING':
            messages.error(request, '当前没有待处理步骤。')
            return redirect('quotation_detail', pk=pk)
        if task.assigned_to_id != request.user.pk:
            messages.error(request, '您不是当前步骤的负责人。')
            return redirect('quotation_detail', pk=pk)

        action = request.POST.get('action', 'APPROVE')
        remark = request.POST.get('remark', '').strip()
        task_id = task.spiff_task_id

        try:
            with transaction.atomic():
                # 驳回时无需校验/保存当前步骤的填写内容
                if action == 'APPROVE':
                    if task_id == TASK_SELECT_BOM:
                        self._save_boms(quotation, request)
                    elif task_id == TASK_PURCHASE_PRICE:
                        self._save_prices(quotation, request)
                    elif task_id == TASK_COST:
                        self._save_cost(quotation, request)
                    elif task_id == TASK_RD_SELECT:
                        self._save_rd_select(quotation, request)
                    elif task_id == TASK_CUSTOMER_PRICE:
                        self._save_customer_price(quotation, request)
                    WorkflowService.complete_task(task, request.user, action, remark)
                elif action == 'REJECT':
                    # 驳回 = 退回发起者修订重提，流程不终止
                    WorkflowService.return_task(
                        task, request.user, {'is_initiator': True}, remark)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('quotation_detail', pk=pk)
        except Exception:
            logger.exception('报价需求单步骤处理失败 pk=%s task=%s', pk, task_id)
            messages.error(request, '步骤处理失败，请检查填写内容。')
            return redirect('quotation_detail', pk=pk)

        messages.success(request, '步骤已提交。')
        return redirect('quotation_detail', pk=pk)

    # ── 各步骤字段保存 ──

    def _save_boms(self, quotation, request):
        formula_ids = request.POST.getlist('formula_ids')
        if not formula_ids:
            raise ValueError('请至少选择一个配方。')

        # 只允许该成品候选集内的配方，防止越权提交无关配方
        allowed = set(
            QuotationService.candidate_formulas(quotation.finished_material)
            .values_list('pk', flat=True)
        )
        valid_ids = [int(fid) for fid in formula_ids
                     if str(fid).isdigit() and int(fid) in allowed]
        if not valid_ids:
            raise ValueError('所选的配方不在该成品的候选中。')

        quotation.boms.all().delete()
        for fid in valid_ids:
            QuotationBOM.objects.create(request=quotation, formula_id=fid)

    def _save_prices(self, quotation, request):
        for key, value in request.POST.items():
            if not key.startswith('price_') or not value.strip():
                continue
            rm_id = key[len('price_'):]
            if not rm_id.isdigit():
                continue
            try:
                price = Decimal(value)
            except InvalidOperation:
                raise ValueError('行情价必须为数字。')
            QuotationMaterialPrice.objects.update_or_create(
                request=quotation, raw_material_id=int(rm_id),
                defaults={'price_tax_included': price, 'entered_by': request.user},
            )
        if not quotation.material_prices.exists():
            raise ValueError('请至少填写一个原材料的行情价。')
        QuotationService.write_market_prices(quotation, request.user)

    def _save_cost(self, quotation, request):
        quotation.marginal_cost = self._parse_decimal(request.POST.get('marginal_cost'))
        quotation.contribution_rate = self._parse_decimal(
            request.POST.get('contribution_rate'), nullable=True)
        quotation.save(update_fields=['marginal_cost', 'contribution_rate'])

    def _save_rd_select(self, quotation, request):
        bom_id = request.POST.get('selected_bom')
        if not bom_id:
            raise ValueError('请选择一个配方。')
        quotation.boms.update(is_selected=False, selected_by=None)
        QuotationBOM.objects.filter(pk=bom_id, request=quotation).update(
            is_selected=True, selected_by=request.user)

    def _save_customer_price(self, quotation, request):
        quotation.customer_price = self._parse_decimal(request.POST.get('customer_price'))
        quotation.save(update_fields=['customer_price'])

    @staticmethod
    def _parse_decimal(value, nullable=False):
        if value is None or not str(value).strip():
            if nullable:
                return None
            raise ValueError('请填写金额。')
        try:
            return Decimal(str(value).strip())
        except InvalidOperation:
            raise ValueError('金额必须为数字。')


class QuotationReturnView(QuotationAccessMixin, View):
    """退回当前步骤到前序节点或发起人。"""
    permission_required = 'app_quotation.change_quotationrequest'

    def post(self, request, pk):
        quotation = get_object_or_404(QuotationRequest, pk=pk)
        self.check_object_permission(quotation)
        task = quotation.current_task
        if task is None or task.assigned_to_id != request.user.pk:
            messages.error(request, '您不是当前步骤的负责人。')
            return redirect('quotation_detail', pk=pk)

        target_pk = request.POST.get('target_pk', '')
        remark = request.POST.get('remark', '').strip()
        try:
            if target_pk in ('initiator', '0'):
                target = {'is_initiator': True}
            else:
                target = WorkflowTask.objects.get(pk=int(target_pk), instance=task.instance)
            WorkflowService.return_task(task, request.user, target, remark)
        except Exception as e:
            logger.exception('退回失败 pk=%s', pk)
            messages.error(request, f'退回失败: {e}')
            return redirect('quotation_detail', pk=pk)

        messages.success(request, '已退回。')
        return redirect('quotation_detail', pk=pk)


class QuotationReassignView(QuotationAccessMixin, View):
    """移交当前步骤给其他用户（复用审批流自带 reassign）。"""
    permission_required = 'app_quotation.change_quotationrequest'

    def post(self, request, pk):
        quotation = get_object_or_404(QuotationRequest, pk=pk)
        self.check_object_permission(quotation)
        task = quotation.current_task
        if task is None or task.assigned_to_id != request.user.pk:
            messages.error(request, '您不是当前步骤的负责人。')
            return redirect('quotation_detail', pk=pk)

        to_user_id = request.POST.get('to_user_id')
        from django.contrib.auth import get_user_model
        User = get_user_model()
        to_user = get_object_or_404(User, pk=to_user_id)
        try:
            WorkflowService.reassign(task, request.user, to_user)
        except Exception as e:
            logger.exception('移交失败 pk=%s', pk)
            messages.error(request, f'移交失败: {e}')
            return redirect('quotation_detail', pk=pk)

        messages.success(request, f'已移交给 {to_user.username}。')
        return redirect('quotation_detail', pk=pk)


class QuotationPrintView(QuotationAccessMixin, PrintableMixin, DetailView):
    """OA 核价申请单打印。"""
    model = QuotationRequest
    permission_required = 'app_quotation.view_quotationrequest'
    renderer_class = QuotationPrintRenderer

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def get_print_renderer(self):
        return QuotationPrintRenderer(self.object)

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return self.render_print_response()
