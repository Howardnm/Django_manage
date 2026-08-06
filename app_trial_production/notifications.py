"""
app_trial_production 通知接入 — 排产工单状态流转通知的类型定义 + 声明式信号绑定。

定义 production_order.state_changed 类型，并把 common_utils.state_machine
的通用 state_changed 信号声明式绑定到它（仅 ProductionOrder 且有关联项目时触发）。
在 AppConfig.ready() 中 import 本模块即完成注册与接线。
"""
from django.contrib.auth import get_user_model

from app_notification.registry import NotificationType, register_ntype
from app_notification.services import register_signal_notification
from common_utils.state_machine import state_changed

User = get_user_model()


def _order_project_recipients(context: dict):
    """排产工单状态 → 关联项目负责人 + 项目协同成员 + 协同销售成员。"""
    order = context['order']
    project = order.project
    if not project:
        return []
    user_ids = {project.manager_id} if project.manager_id else set()
    user_ids.update(project.members.values_list('user_id', flat=True))
    user_ids.update(project.sales_members.values_list('user_id', flat=True))
    return User.objects.filter(pk__in=user_ids)


def _content_url(target, context: dict) -> str:
    """委托 RelatedObjectRouter 解析业务对象落地页。"""
    from app_workflow.utils import related_object_router
    return related_object_router.resolve(target) or ''


def _register_trial_types() -> None:
    register_ntype(NotificationType(
        code='production_order.state_changed',
        label='排产工单状态',
        verb_template='排产工单「{order_code}」状态：{old_label} → {new_label}',
        recipients=_order_project_recipients,
        url_resolver=_content_url,
        icon='ti-truck',
    ))


def _state_changed_builder(kw: dict):
    """state_changed 只对 ProductionOrder 且有关联项目时发通知。"""
    from app_trial_production.models import ProductionOrder
    obj = kw.get('obj')
    if not isinstance(obj, ProductionOrder) or not obj.project_id:
        return None
    old_status = kw.get('old_status')
    return {
        'target': obj,
        'action_object': obj.project,
        'actor': kw.get('user'),
        'order': obj,
        'order_code': obj.code,
        'old_label': ProductionOrder.Status(old_status).label if old_status else '',
        'new_label': obj.status_label,
    }


def _register_trial_bindings() -> None:
    register_signal_notification(state_changed, 'production_order.state_changed', _state_changed_builder)


# import 本模块即完成注册与接线（AppConfig.ready() 触发）
_register_trial_types()
_register_trial_bindings()