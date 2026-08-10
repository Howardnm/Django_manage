import logging
from datetime import datetime

from django.views.generic import View, ListView
from django.shortcuts import get_object_or_404
from django.db.models import Count
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.utils import timezone

from app_trial_production.mixins import ExtrusionTaskAccessMixin
from app_trial_production.models import ProductionOrder
from app_trial_production.filters import PendingOrderFilter
from app_trial_production.services import ProductionOrderService
from app_trial_production.services.extrusion_service import build_extrusion_calendar_events
from app_trial_production.utils.extrusion import is_all_day_event
from common_utils.state_machine import InvalidStateTransition

logger = logging.getLogger(__name__)


class ExtrusionEventsApiView(ExtrusionTaskAccessMixin, View):
    """GET: FullCalendar 事件数据 API"""
    enforce_dept_isolation = False

    def get(self, request):
        events = build_extrusion_calendar_events(
            request.GET.get('start', ''),
            request.GET.get('end', ''),
        )
        return JsonResponse(events, safe=False)


class ExtrusionScheduleApiView(ExtrusionTaskAccessMixin, View):
    """POST: 设置工单排产时间（日历拖拽 / 领取按钮回调）"""
    enforce_dept_isolation = False

    def post(self, request):
        order_pk = request.POST.get('order_pk')
        datetime_str = request.POST.get('scheduled_date')
        end_str = request.POST.get('scheduled_end', '')

        order = get_object_or_404(ProductionOrder, pk=order_pk, status='ACCEPTED')

        try:
            datetime_str_clean = datetime_str.replace('Z', '+00:00')
            scheduled_dt = datetime.fromisoformat(datetime_str_clean)
        except (ValueError, TypeError):
            return JsonResponse({'error': '时间格式无效'}, status=400)

        scheduled_end = None
        if end_str:
            try:
                end_str_clean = end_str.replace('Z', '+00:00')
                scheduled_end = datetime.fromisoformat(end_str_clean)
            except (ValueError, TypeError):
                return JsonResponse({'error': '结束时间格式无效'}, status=400)

        ProductionOrderService.schedule_extrusion(order, scheduled_dt, scheduled_end)

        formula_versions = []
        has_color = False
        for fd in order.formula_details.all():
            formula_versions.append(f'v{fd.formula.version}')
            if fd.needs_color_matching:
                has_color = True

        end_dt = order.extrusion_scheduled_end or order.extrusion_scheduled_date
        is_all_day = is_all_day_event(order.extrusion_scheduled_date, end_dt)

        return JsonResponse({
            'success': True,
            'order_pk': order.pk,
            'date': order.extrusion_scheduled_date.isoformat(),
            'end_date': end_dt.isoformat(),
            'allDay': is_all_day,
            'editable': not order.is_extrusion_readonly,
            'color': order.extrusion_calendar_color,
            'border_css': order.extrusion_calendar_border,
            'code': order.code,
            'trial_code': order.trial_code,
            'quantity': str(order.quantity_planned),
            'formula_count': len(formula_versions),
            'needs_color': has_color,
            'project_name': order.project.name if order.project else '',
            'stage_node': f"{order.project_node.get_stage_display()} 第{order.project_node.round}轮" if order.project_node else '',
            'status_label': order.extrusion_status_label,
            'status_badge': order.extrusion_status_badge,
            'quantity_badge': order.extrusion_quantity_badge,
        })


class ExtrusionUnscheduleApiView(ExtrusionTaskAccessMixin, View):
    """POST: 取消排期（将工单退回待排产池）"""
    enforce_dept_isolation = False

    def post(self, request, pk):
        order = get_object_or_404(ProductionOrder, pk=pk, status='ACCEPTED')
        ProductionOrderService.schedule_extrusion(order, None)
        return JsonResponse({
            'success': True,
            'order_pk': order.pk,
            'code': order.code,
            'trial_code': order.trial_code,
            'quantity': str(order.quantity_planned),
            'project_name': order.project.name if order.project else '',
            'process_profile_name': order.process_profile.name if order.process_profile else '',
            'created_at': order.created_at.strftime('%m-%d %H:%M'),
        })


class ExtrusionStatsApiView(ExtrusionTaskAccessMixin, View):
    """GET: 排产工作台顶部统计指标 API"""
    enforce_dept_isolation = False

    def get(self, request):
        pending_count = ProductionOrder.objects.filter(
            status=ProductionOrder.Status.ACCEPTED, extrusion_scheduled_date__isnull=True,
        ).count()
        scheduled_count = ProductionOrder.objects.filter(
            status=ProductionOrder.Status.ACCEPTED, extrusion_scheduled_date__isnull=False,
        ).count()
        in_progress_count = ProductionOrder.objects.filter(
            status=ProductionOrder.Status.EXTRUDING,
        ).count()

        return JsonResponse({
            'pending_count': pending_count,
            'scheduled_count': scheduled_count,
            'in_progress_count': in_progress_count,
        })


class PendingOrdersCardView(ExtrusionTaskAccessMixin, ListView):
    """待排产工单卡片（HTMX 片段）"""
    model = ProductionOrder
    template_name = 'apps/app_trial_production/extrusion/_pending_orders_card.html'
    context_object_name = 'orders'
    paginate_by = 10
    enforce_dept_isolation = False

    def get_queryset(self):
        qs = super().get_queryset()
        if qs is None:
            qs = self.model.objects.all()
        qs = qs.filter(
            status='ACCEPTED', extrusion_scheduled_date__isnull=True,
        ).select_related(
            'project', 'process_profile',
        ).annotate(
            formula_count=Count('formula_details'),
        )
        self.filter = PendingOrderFilter(self.request.GET, queryset=qs)
        return self.filter.qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filter
        now = timezone.now()
        default_dt = now.replace(hour=8, minute=0, second=0, microsecond=0)
        context['default_schedule_time'] = default_dt.strftime('%Y-%m-%dT%H:%M')
        return context
