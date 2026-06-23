import logging
from datetime import datetime, timedelta

from django.views.generic import TemplateView, View, ListView
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


class ExtrusionBoardView(ExtrusionTaskAccessMixin, TemplateView):
    """挤出排产工作台 — 日历 + 待排产池 + 生产中看板"""
    template_name = 'apps/app_trial_production/extrusion/board.html'
    enforce_dept_isolation = False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # 默认排产时间（统计指标改为前端懒加载）
        now = timezone.now()
        default_dt = now.replace(hour=8, minute=0, second=0, microsecond=0)
        context['default_schedule_time'] = default_dt.strftime('%Y-%m-%dT%H:%M')

        return context


class ExtrusionEventsApiView(ExtrusionTaskAccessMixin, View):
    """GET: FullCalendar 事件数据 API — 按时间范围返回已排期工单"""
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
            'formula_details__formula',
        )

        # FullCalendar 传来 ISO 8601 格式，使用时间区间重叠判断
        # 逻辑：事件开始 ≤ 范围结束 AND (事件结束 ≥ 范围开始 OR 无结束时间)
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
            formula_versions = [
                f'v{fd.formula.version}'
                for fd in order.formula_details.all()
            ]
            has_color = order.formula_details.filter(
                needs_color_matching=True,
            ).exists()

            start_dt = order.extrusion_scheduled_date
            end_dt = order.extrusion_scheduled_end or start_dt

            is_all_day = is_all_day_event(start_dt, end_dt)
            if is_all_day:
                # 转为本地时区取日期（UTC 16:00 = 本地次日 00:00）
                local_tz = timezone.get_current_timezone()
                local_start = start_dt.astimezone(local_tz)
                local_end = end_dt.astimezone(local_tz)
                event_start = local_start.date().isoformat()
                # FullCalendar 全天事件 end 为 exclusive：
                # 同一天 → end 为次日；多天 → end 为结束日期
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

    def post(self, request, order_pk):
        order = get_object_or_404(ProductionOrder, pk=order_pk, status='ACCEPTED')

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

    def post(self, request, order_pk):
        order = get_object_or_404(ProductionOrder, pk=order_pk, status='ACCEPTED')
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
    """GET: 排产工作台顶部统计指标 API — 待排产/已排期/生产中 数量"""
    enforce_dept_isolation = False

    def get(self, request):
        pending_count = ProductionOrder.objects.filter(
            status='ACCEPTED',
            extrusion_scheduled_date__isnull=True,
        ).count()

        scheduled_count = ProductionOrder.objects.filter(
            status='ACCEPTED',
            extrusion_scheduled_date__isnull=False,
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
    """待排产工单卡片（HTMX 片段）— 复用 FilterSet + ListView.paginate_by"""
    model = ProductionOrder
    template_name = 'apps/app_trial_production/extrusion/_pending_orders_card.html'
    context_object_name = 'orders'
    paginate_by = 10
    enforce_dept_isolation = False

    def get_queryset(self):
        # Step 1: 权限过滤后的基查询
        qs = super().get_queryset()
        if qs is None:
            qs = self.model.objects.all()

        # Step 2: 基过滤 + 优化关联查询
        qs = qs.filter(
            status='ACCEPTED',
            extrusion_scheduled_date__isnull=True,
        ).select_related(
            'project', 'process_profile',
        ).annotate(
            formula_count=Count('formula_details'),
        )

        # Step 3: 实例化 Filter（在 select_related/prefetch_related 之后）
        self.filter = PendingOrderFilter(self.request.GET, queryset=qs)
        qs = self.filter.qs.order_by('-created_at')
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filter

        now = timezone.now()
        default_dt = now.replace(hour=8, minute=0, second=0, microsecond=0)
        context['default_schedule_time'] = default_dt.strftime('%Y-%m-%dT%H:%M')
        return context