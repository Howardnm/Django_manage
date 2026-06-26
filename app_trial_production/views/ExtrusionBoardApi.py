import logging
from datetime import datetime, timedelta

from django.views.generic import View, ListView
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.utils import timezone

from app_trial_production.mixins import ExtrusionTaskAccessMixin
from app_trial_production.models import ProductionOrder
from app_trial_production.filters import PendingOrderFilter
from app_trial_production.services import ProductionOrderService
from app_trial_production.utils.extrusion import is_all_day_event

logger = logging.getLogger(__name__)


class ExtrusionEventsApiView(ExtrusionTaskAccessMixin, View):
    """GET: FullCalendar 事件数据 API"""
    enforce_dept_isolation = False

    def get(self, request):
        start_str = request.GET.get('start', '')
        end_str = request.GET.get('end', '')

        qs = ProductionOrder.objects.filter(
            status__in=['ACCEPTED', 'EXTRUDING', 'INJECTION_MOLDING', 'TESTING'],
            extrusion_scheduled_date__isnull=False,
        ).select_related(
            'project', 'extrusion_task', 'process_profile',
        ).prefetch_related(
            'formula_details__formula__material_type',
        )

        if start_str and end_str:
            try:
                start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
                qs = qs.filter(
                    extrusion_scheduled_date__lte=end_dt,
                ).filter(
                    Q(extrusion_scheduled_end__gte=start_dt) |
                    Q(extrusion_scheduled_end__isnull=True),
                )
            except (ValueError, TypeError):
                pass

        events = []
        for order in qs.order_by('extrusion_scheduled_date'):
            formula_versions = [f'v{fd.formula.version}' for fd in order.formula_details.all()]
            has_color = order.formula_details.filter(needs_color_matching=True).exists()

            # 从关联配方中提取颜色信息（取第一个有数据的配方）
            material_type_name = ''
            material_color_name = ''
            pantone_code = ''
            rgb_value = ''
            for fd in order.formula_details.all():
                f = fd.formula
                if not material_type_name and f.material_type_id:
                    material_type_name = f.material_type.name
                if not material_color_name and f.material_color_name:
                    material_color_name = f.material_color_name
                if not pantone_code and f.pantone_code:
                    pantone_code = f.pantone_code
                if not rgb_value and f.rgb_value:
                    rgb_value = f.rgb_value
                if all([material_type_name, material_color_name, pantone_code, rgb_value]):
                    break

            start_dt = order.extrusion_scheduled_date
            end_dt = order.extrusion_scheduled_end or start_dt

            is_all_day = is_all_day_event(start_dt, end_dt)
            if is_all_day:
                local_tz = timezone.get_current_timezone()
                local_start = start_dt.astimezone(local_tz)
                local_end = end_dt.astimezone(local_tz)
                event_start = local_start.date().isoformat()
                if local_end.date() == local_start.date():
                    event_end = (local_start.date() + timedelta(days=1)).isoformat()
                else:
                    event_end = local_end.date().isoformat()
            else:
                event_start = start_dt.isoformat()
                event_end = end_dt.isoformat()

            events.append({
                'id': str(order.pk),
                'title': order.code,
                'start': event_start,
                'end': event_end,
                'allDay': is_all_day,
                'editable': not order.is_extrusion_readonly,
                'color': order.extrusion_calendar_color,
                'textColor': '#1e293b',
                'borderColor': order.extrusion_calendar_border,
                'extendedProps': {
                    'trial_code': order.trial_code,
                    'project_name': order.project.name if order.project else '',
                    'process_profile_name': order.process_profile.name if order.process_profile else '',
                    'created_at': order.created_at.strftime('%Y-%m-%d %H:%M'),
                    'quantity': str(order.quantity_planned),
                    'formula_count': len(formula_versions),
                    'needs_color': has_color,
                    'stage_node': (
                        f"{order.project_node.get_stage_display()} 第{order.project_node.round}轮"
                        if order.project_node else ''
                    ),
                    'order_pk': order.pk,
                    'status_label': order.extrusion_status_label,
                    'status_badge': order.extrusion_status_badge,
                    'quantity_badge': order.extrusion_quantity_badge,
                    'border_css': order.extrusion_calendar_border,
                    'material_type_name': material_type_name,
                    'material_color_name': material_color_name,
                    'pantone_code': pantone_code,
                    'rgb_value': rgb_value,
                },
            })

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


class ExtrusionStartApiView(ExtrusionTaskAccessMixin, View):
    """POST: 开始挤出生产（创建 ExtrusionTask + ColorMatchingTask）"""
    enforce_dept_isolation = False

    def post(self, request, pk):
        order = get_object_or_404(ProductionOrder, pk=pk, status='ACCEPTED')

        try:
            ProductionOrderService.start_extrusion(order, request.user)
            messages.success(request, f'工单 {order.code} 已开始挤出生产')
        except Exception:
            logger.exception(f"Failed to start extrusion for order {order.pk}")
            messages.error(request, '开始生产时发生错误，请稍后重试')

        return HttpResponse(status=204, headers={'HX-Refresh': 'true'})


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
            status='ACCEPTED', extrusion_scheduled_date__isnull=True,
        ).count()
        scheduled_count = ProductionOrder.objects.filter(
            status='ACCEPTED', extrusion_scheduled_date__isnull=False,
        ).count()
        in_progress_count = ProductionOrder.objects.filter(
            status='EXTRUDING',
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
