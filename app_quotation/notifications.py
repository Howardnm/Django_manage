"""
产品报价需求单通知类型定义与信号绑定。

财务经理审批（⑧）通过后，知会成本中心各组组长（⑨）。
常规的「待办 / 通过 / 驳回 / 完成」通知由 app_workflow.notifications 全局信号已覆盖，
这里只补报价流程特有的「知会」类型。
"""

from app_notification.registry import NotificationType, register_ntype
from app_notification.services import register_signal_notification

from app_workflow.signals import task_completed

from .models import QuotationRequest
from .services import ROLE_COST_LEADER, TASK_FINANCE_MANAGER


def _cost_leader_recipients(context):
    """成本中心各组组长（role=cost_leader 的主负责人）。"""
    from app_user.models import OrgRole, OrgRoleAssignment
    role = OrgRole.objects.filter(code=ROLE_COST_LEADER).first()
    if role is None:
        return []
    return [
        a.user for a in OrgRoleAssignment.objects.filter(
            role=role, is_primary=True,
        ).select_related('user')
    ]


def _quotation_url(target, context):
    if target is None:
        return ''
    from django.urls import reverse
    try:
        return reverse('quotation_detail', kwargs={'pk': target.pk})
    except Exception:
        return ''


register_ntype(NotificationType(
    code='quotation.notified',
    label='报价需求单知会',
    verb_template='报价需求单「{display}」已进入成本中心知会环节',
    recipients=_cost_leader_recipients,
    url_resolver=_quotation_url,
    icon='ti-bell-ring',
    exclude_actor=False,
))


def _notify_cost_leaders_builder(signal_kwargs):
    """财务经理审批通过 → 知会成本中心各组组长。"""
    task = signal_kwargs.get('task')
    action = signal_kwargs.get('action')
    user = signal_kwargs.get('user')
    if action != 'APPROVE' or task is None:
        return None
    if task.spiff_task_id != TASK_FINANCE_MANAGER:
        return None
    request = task.instance.content_object
    if not isinstance(request, QuotationRequest):
        return None
    return {'target': request, 'actor': user, 'display': request.code}


register_signal_notification(
    task_completed,
    'quotation.notified',
    _notify_cost_leaders_builder,
)
