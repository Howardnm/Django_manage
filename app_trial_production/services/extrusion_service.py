import logging
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from common_utils.state_machine import StateMachine

logger = logging.getLogger(__name__)


class ExtrusionTaskService:
    """挤出任务业务"""

    @staticmethod
    @transaction.atomic
    def start_task(task, user):
        """开始挤出任务"""
        if not task.operator_id:
            task.operator = user
            task.save(update_fields=['operator'])
        StateMachine.transition(task, 'IN_PROGRESS', user)

        # 同步推进工单状态
        order = task.production_order
        if order.status == 'ACCEPTED':
            StateMachine.transition(order, 'EXTRUDING', user)

    @staticmethod
    @transaction.atomic
    def save_record(task, params, user):
        """
        保存挤出参数记录（不改变状态）。

        Args:
            task: ExtrusionTask 实例
            params: dict 包含所有参数字段
            user: 记录人
        """
        for field in task.ALL_PARAM_FIELDS:
            if field in params:
                setattr(task, field, params[field])

        if 'remark' in params:
            task.remark = params['remark']

        task.recorded_by = user
        task.save()

    @staticmethod
    @transaction.atomic
    def complete_task(task, user):
        """
        完成挤出任务 → 调用并行屏障检查。
        实际产量由后续颗粒分拨汇总得出，不在此处写入。
        """
        StateMachine.transition(task, 'COMPLETED', user)

        from .order_service import ProductionOrderService
        ProductionOrderService.check_and_advance(task.production_order)


def build_extrusion_calendar_events(start_str, end_str):
    """构建挤出排产 FullCalendar 事件列表 — 可写工作台与只读看板共用。

    Args:
        start_str: FullCalendar 附带的时间范围起点（可选）。
        end_str: FullCalendar 附带的时间范围终点（可选）。
    Returns:
        list[dict]: FullCalendar 事件负载。
    """
    from app_trial_production.models import ProductionOrder
    from app_trial_production.utils.extrusion import is_all_day_event

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

    return events
