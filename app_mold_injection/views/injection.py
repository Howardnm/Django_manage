import logging

from django.db.models import Count
from django.views.generic import ListView, DetailView, View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from app_formula.models import LabFormula
from app_mold_injection.mixins import InjectionTaskAccessMixin
from app_mold_injection.models import InjectionTask
from app_mold_injection.forms import InjectionCompleteForm
from app_mold_injection.services import InjectionTaskService
from common_utils.state_machine import InvalidStateTransition

logger = logging.getLogger(__name__)


# 注塑任务状态筛选 Tab
INJECTION_STATUS_TABS = [
    {'value': 'ALL', 'label': '全部状态', 'icon': 'ti ti-filter'},
    {'value': 'PENDING', 'label': '未注塑', 'icon': 'ti ti-clock'},
    {'value': 'COMPLETED', 'label': '已完成', 'icon': 'ti ti-check'},
]


def _order_material_types(order):
    """工单关联配方的基材类型，按版本顺序去重。

    与测试任务详情同一数据源：实验单号 + 项目下的全部配方版本。
    """
    if order is None:
        return []
    seen = set()
    material_types = []
    formulas = LabFormula.objects.filter(
        code=order.trial_code,
        project=order.project,
    ).select_related('material_type').order_by('version')
    for formula in formulas:
        material_type = formula.material_type
        if material_type.pk in seen:
            continue
        seen.add(material_type.pk)
        material_types.append(material_type)
    return material_types


def _build_mold_formula_matrix(mold_requirements):
    """从 mold_requirements QuerySet 构建 (formulas, matrix_rows) 元组。

    供 InjectionDetailView 和 InjectionCompleteView 共用，
    避免重复的两层循环遍历逻辑。
    """
    formula_map = {}
    for req in mold_requirements:
        for detail in req.formula_details.all():
            if detail.formula_id and detail.formula_id not in formula_map:
                formula_map[detail.formula_id] = detail.formula
    formulas = sorted(formula_map.values(), key=lambda f: f.version)

    matrix_rows = []
    for req in mold_requirements:
        qty_map = {}
        row_total = 0
        for detail in req.formula_details.all():
            if detail.formula_id:
                qty_map[detail.formula_id] = detail.specimen_quantity
            row_total += detail.specimen_quantity
        matrix_rows.append({
            'mold': req.mold,
            'quantities': [qty_map.get(f.pk, 0) for f in formulas],
            'total': row_total,
        })
    return formulas, matrix_rows


class InjectionTaskListView(InjectionTaskAccessMixin, ListView):
    """注塑任务列表"""
    model = InjectionTask
    template_name = 'apps/app_mold_injection/injection/list.html'
    context_object_name = 'injection_tasks'
    paginate_by = 20
    permission_required = 'app_mold_injection.view_injectiontask'

    def get_queryset(self):
        from app_mold_injection.filters import InjectionTaskFilter
        qs = super().get_queryset()
        if qs is None:
            qs = self.model.objects.all()
        qs = qs.select_related(
            'production_order', 'production_order__project',
        ).prefetch_related(
            'mold_requirements__mold',
        ).annotate(
            mold_count=Count('mold_requirements'),
        )
        self.filter = InjectionTaskFilter(self.request.GET, queryset=qs)
        qs = self.filter.qs

        # 状态 tab 筛选（卡片头部 tab，非 django_filters 字段）
        status_param = self.request.GET.get('status', '')
        if status_param in ('PENDING', 'COMPLETED'):
            qs = qs.filter(status=status_param)

        if not self.request.GET.get('sort'):
            qs = qs.order_by('-created_at')
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = getattr(self, 'filter', None)
        context['current_sort'] = self.request.GET.get('sort', '')
        context['current_status'] = self.request.GET.get('status', 'ALL')
        context['status_tabs'] = INJECTION_STATUS_TABS
        return context


class InjectionDetailView(InjectionTaskAccessMixin, DetailView):
    """注塑任务详情"""
    model = InjectionTask
    template_name = 'apps/app_mold_injection/injection/detail.html'
    context_object_name = 'injection_task'
    permission_required = 'app_mold_injection.view_injectiontask'

    def get_queryset(self):
        qs = super().get_queryset()
        if qs is None:
            return self.model.objects.all()
        return qs.select_related(
            'production_order', 'production_order__project',
            'operator',
        ).prefetch_related(
            'mold_requirements__mold', 'mold_requirements__formula_details__formula',
        )

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        task = self.object

        formulas, matrix_rows = _build_mold_formula_matrix(
            task.mold_requirements.all())

        ctx['mold_matrix_formulas'] = formulas
        ctx['mold_matrix_rows'] = matrix_rows
        ctx['has_mold_requirements'] = len(matrix_rows) > 0
        ctx['material_types'] = _order_material_types(task.production_order)

        ctx['show_complete_btn'] = task.status == 'PENDING'
        ctx['complete_form'] = InjectionCompleteForm(instance=task)
        return ctx


class InjectionCompleteView(InjectionTaskAccessMixin, View):
    """完成注塑任务"""
    template_name = 'apps/app_mold_injection/injection/complete.html'
    permission_required = 'app_mold_injection.change_injectiontask'

    def get(self, request, pk):
        return redirect('mold_injection:task_detail', pk=pk)

    def post(self, request, pk):
        task = get_object_or_404(InjectionTask, pk=pk)
        if task.status != 'PENDING':
            messages.warning(request, '当前任务状态不允许完成')
            return redirect('mold_injection:task_detail', pk=pk)

        form = InjectionCompleteForm(request.POST, instance=task)
        if not form.is_valid():
            messages.error(request, '备注未通过校验，注塑任务未完成')
            return redirect('mold_injection:task_detail', pk=pk)

        task.remark = form.cleaned_data.get('remark', '')
        try:
            task.save(update_fields=['remark'])
            InjectionTaskService.complete_task(task, request.user)
            messages.success(request, '注塑任务已完成')
        except InvalidStateTransition as e:
            logger.exception(f"Injection complete failed: pk={pk}")
            messages.error(request, f'注塑任务完成失败：{e}')
        return redirect('mold_injection:task_detail', pk=pk)
