import logging

from django.views.generic import ListView, View
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from app_trial_production.mixins import ExtrusionTaskAccessMixin
from app_trial_production.models import ExtrusionTask
from app_trial_production.filters import ExtrusionTaskFilter
from app_trial_production.services import ExtrusionTaskService

from common_utils.state_machine import InvalidStateTransition

logger = logging.getLogger(__name__)


class ExtrusionTaskListView(ExtrusionTaskAccessMixin, ListView):
    """挤出任务列表"""
    model = ExtrusionTask
    template_name = 'apps/app_trial_production/extrusion/list.html'
    context_object_name = 'tasks'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        if qs is None:
            qs = self.model.objects.all()
        qs = qs.select_related(
            'production_order', 'production_order__project',
            'operator',
        ).filter(
            production_order__extrusion_scheduled_date__isnull=False,
            production_order__status__in=[
                'ACCEPTED', 'EXTRUDING', 'INJECTION_MOLDING', 'TESTING', 'COMPLETED',
            ],
        ).order_by('-created_at')

        self.filter = ExtrusionTaskFilter(self.request.GET, queryset=qs)
        qs = self.filter.qs
        if not self.request.GET.get('sort'):
            qs = qs.order_by('-created_at')
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filter
        sort_list = self.request.GET.getlist('sort')
        context['current_sort'] = sort_list[0] if sort_list else ''
        return context


class ExtrusionTaskDetailView(ExtrusionTaskAccessMixin, View):
    """旧的挤出详情地址。工艺参数已在工单详情上展示。"""

    def get(self, request, pk):
        return redirect('trial_order_detail', pk=pk)


class ExtrusionTaskStartView(ExtrusionTaskAccessMixin, View):
    """开始挤出任务"""

    def post(self, request, pk):
        task = get_object_or_404(ExtrusionTask, production_order_id=pk)
        if task.status != 'PENDING':
            messages.warning(request, '任务状态不允许开始')
            return redirect('trial_order_detail', pk=pk)

        # 操作员归属校验
        if task.operator_id and task.operator_id != request.user.pk:
            if not request.user.is_superuser:
                raise PermissionDenied("您不是该任务分配的挤出操作员")

        try:
            ExtrusionTaskService.start_task(task, request.user)
            messages.success(request, '挤出任务已开始')
        except InvalidStateTransition as e:
            logger.exception(f"Extrusion start failed: pk={pk}")
            messages.error(request, f'启动挤出任务失败：{e}')
        return redirect('trial_order_detail', pk=pk)


class ExtrusionRecordFormView(ExtrusionTaskAccessMixin, View):
    """旧的记录参数地址。工艺参数改在工单上维护，这里只跳回详情。"""

    def get(self, request, pk):
        return redirect('trial_order_detail', pk=pk)

    def post(self, request, pk):
        return redirect('trial_order_detail', pk=pk)


