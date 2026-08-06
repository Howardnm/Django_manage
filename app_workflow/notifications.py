"""
app_workflow 通知接入 — 审批流程相关的通知类型定义 + 声明式信号绑定。

本模块是 app_workflow 向通知模块的声明式接入点：定义 8 个审批通知类型，
并把 app_workflow 的 5 个信号声明式绑定到对应类型。在 AppConfig.ready() 中
import 本模块即完成注册与接线，无需修改 app_notification。

接收者/落地页解析函数与消息模板均在本模块内（业务逻辑归属业务 app）。
"""
from django.contrib.auth import get_user_model

from app_notification.registry import NotificationType, register_ntype
from app_notification.services import notify, register_signal_notification
from .signals import (
    workflow_started, task_created, task_completed,
    workflow_completed, task_returned,
)

User = get_user_model()


# ════════════════════════════════════════════════════════════════
# 接收者解析辅助
# ════════════════════════════════════════════════════════════════

def _first_pending_assignees(context: dict):
    """待办任务的接收者：负责人 + 候选用户 + 候选组成员。"""
    from app_user.models import ReviewGroup
    task = context['task']
    recipients = set()
    if task.assigned_to_id:
        recipients.add(task.assigned_to)
    if task.candidate_users.exists():
        recipients.update(task.candidate_users.all())
    if task.candidate_groups:
        member_ids = ReviewGroup.objects.filter(
            name__in=task.candidate_groups, is_active=True,
        ).values_list('members', flat=True)
        recipients.update(User.objects.filter(pk__in=member_ids))
    return recipients


def _submitted_recipients(context: dict):
    """流程发起 → 首个待办任务的接收者。"""
    instance = context['instance']
    task = instance.tasks.filter(status='PENDING').select_related('assigned_to').first()
    if not task:
        return []
    return _first_pending_assignees({'task': task})


def _initiator_recipients(context: dict):
    """流程发起人。"""
    return [context['instance'].started_by]


def _returned_approver_recipients(context: dict):
    """退回重审 → 被退回的目标任务接收者。"""
    target_task = context['target_task']
    return [target_task.assigned_to] if target_task.assigned_to_id else []


# ════════════════════════════════════════════════════════════════
# 落地页解析辅助
# ════════════════════════════════════════════════════════════════

def _content_url(target, context: dict) -> str:
    """委托 RelatedObjectRouter 解析业务对象落地页。"""
    from app_workflow.utils import related_object_router
    return related_object_router.resolve(target) or ''


def _instance_url(target, context: dict) -> str:
    """跳转到审批实例详情页。"""
    from django.urls import reverse
    instance = context['instance']
    return reverse('workflow_instance_detail', kwargs={'pk': instance.pk})


def _display_name(content_object) -> str:
    """业务对象显示名（注册表/str 回退）。"""
    from app_workflow.utils import related_object_router
    return related_object_router.get_display_name(content_object) or ''


# ════════════════════════════════════════════════════════════════
# 通知类型定义（8 个）
# ════════════════════════════════════════════════════════════════

def _register_workflow_types() -> None:
    register_ntype(NotificationType(
        code='workflow_submitted',
        label='流程发起',
        verb_template='{initiator} 发起了「{display}」的审批',
        recipients=_submitted_recipients,
        url_resolver=_content_url,
        icon='ti-send',
        exclude_actor=False,   # 通知审批人，审批人==发起人也应收到
    ))
    register_ntype(NotificationType(
        code='workflow_task_assigned',
        label='审批待办',
        verb_template='您有新的审批待办：{task_name}（{display}）',
        recipients=_first_pending_assignees,
        url_resolver=_instance_url,
        icon='ti-clipboard',
        exclude_actor=False,   # 通知审批人，审批人==发起人也应收到
    ))
    register_ntype(NotificationType(
        code='workflow_approved',
        label='审核通过',
        verb_template='您的「{display}」节点「{task_name}」已通过',
        recipients=_initiator_recipients,
        url_resolver=_content_url,
        icon='ti-circle-check',
    ))
    register_ntype(NotificationType(
        code='workflow_rejected',
        label='审核驳回',
        verb_template='您的「{display}」审批被「{user}」驳回',
        recipients=_initiator_recipients,
        url_resolver=_content_url,
        icon='ti-circle-x',
    ))
    register_ntype(NotificationType(
        code='workflow_returned_to_approver',
        label='退回重审',
        verb_template='「{display}」审批已退回，请重新审核「{task_name}」',
        recipients=_returned_approver_recipients,
        url_resolver=_content_url,
        icon='ti-rotate',
    ))
    register_ntype(NotificationType(
        code='workflow_returned_to_initiator',
        label='退回重填',
        verb_template='您的「{display}」审批被退回，需重新填写提交',
        recipients=_initiator_recipients,
        url_resolver=_content_url,
        icon='ti-rotate',
    ))
    register_ntype(NotificationType(
        code='workflow_completed',
        label='流程完成',
        verb_template='您的「{display}」审批流程已全部完成',
        recipients=_initiator_recipients,
        url_resolver=_content_url,
        icon='ti-circle-check',
    ))
    register_ntype(NotificationType(
        code='workflow_canceled',
        label='流程取消',
        verb_template='您的「{display}」审批流程已取消',
        recipients=_initiator_recipients,
        url_resolver=_content_url,
        icon='ti-circle-off',
    ))


# ════════════════════════════════════════════════════════════════
# 上下文构造器（signal kwargs → notify() context）
# ════════════════════════════════════════════════════════════════

def _submitted_builder(kw: dict):
    instance = kw['instance']
    return {
        'target': instance.content_object,
        'action_object': instance,
        'actor': instance.started_by,
        'instance': instance,
        'display': _display_name(instance.content_object),
        'initiator': instance.started_by.username if instance.started_by else '',
    }


def _task_assigned_builder(kw: dict):
    task = kw['task']
    instance = task.instance
    return {
        'target': instance.content_object,
        'action_object': task,
        'actor': instance.started_by,
        'instance': instance,
        'task': task,
        'display': _display_name(instance.content_object),
        'task_name': task.display_name or task.task_name,
    }


def _approved_builder(kw: dict):
    task = kw['task']
    instance = task.instance
    # 最后一次 APPROVE 会置 status=COMPLETED，不发"节点通过"，改由
    # workflow_completed(COMPLETED) 发"流程完成"，避免重复。
    if not (kw['action'] == 'APPROVE' and instance.status == 'RUNNING'):
        return None
    return {
        'target': instance.content_object,
        'action_object': task,
        'actor': kw['user'],
        'instance': instance,
        'display': _display_name(instance.content_object),
        'task_name': task.display_name or task.task_name,
    }


def _rejected_builder(kw: dict):
    task = kw['task']
    instance = task.instance
    if kw['action'] != 'REJECT':
        return None
    return {
        'target': instance.content_object,
        'action_object': task,
        'actor': kw['user'],
        'instance': instance,
        'display': _display_name(instance.content_object),
        'task_name': task.display_name or task.task_name,
        'user': kw['user'].username if kw['user'] else '',
    }


def _completed_builder(kw: dict):
    if kw['status'] != 'COMPLETED':
        return None
    instance = kw['instance']
    return {
        'target': instance.content_object,
        'action_object': instance,
        'actor': None,   # 系统通知，避免被 recipients.discard(actor) 吞掉
        'instance': instance,
        'display': _display_name(instance.content_object),
    }


def _canceled_builder(kw: dict):
    if kw['status'] != 'CANCELED':
        return None
    instance = kw['instance']
    return {
        'target': instance.content_object,
        'action_object': instance,
        'actor': None,
        'instance': instance,
        'display': _display_name(instance.content_object),
    }


def _returned_initiator_builder(kw: dict):
    task = kw['task']
    instance = task.instance
    if kw.get('target_task') is not None:
        return None
    return {
        'target': instance.content_object,
        'action_object': task,
        'actor': kw['user'],
        'instance': instance,
        'display': _display_name(instance.content_object),
    }


def _returned_approver_builder(kw: dict):
    task = kw['task']
    instance = task.instance
    target_task = kw.get('target_task')
    if target_task is None:
        return None
    return {
        'target': instance.content_object,
        'action_object': task,
        'actor': kw['user'],
        'instance': instance,
        'target_task': target_task,
        'display': _display_name(instance.content_object),
        'task_name': target_task.display_name or target_task.task_name,
    }


# ════════════════════════════════════════════════════════════════
# 声明式信号绑定
# ════════════════════════════════════════════════════════════════

def _register_workflow_bindings() -> None:
    register_signal_notification(workflow_started, 'workflow_submitted', _submitted_builder)
    register_signal_notification(task_created, 'workflow_task_assigned', _task_assigned_builder)
    register_signal_notification(task_completed, 'workflow_approved', _approved_builder)
    register_signal_notification(task_completed, 'workflow_rejected', _rejected_builder)
    register_signal_notification(workflow_completed, 'workflow_completed', _completed_builder)
    register_signal_notification(workflow_completed, 'workflow_canceled', _canceled_builder)
    register_signal_notification(task_returned, 'workflow_returned_to_initiator', _returned_initiator_builder)
    register_signal_notification(task_returned, 'workflow_returned_to_approver', _returned_approver_builder)


# import 本模块即完成注册与接线（AppConfig.ready() 触发）
_register_workflow_types()
_register_workflow_bindings()