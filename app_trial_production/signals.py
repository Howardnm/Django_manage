from django.dispatch import receiver
from app_workflow.signals import task_created
from app_notification.signals import _send_notification_to_recipients


@receiver(task_created)
def trial_task_created_handler(sender, task, **kwargs):
    """当工作流创建新任务时，通知相关用户"""
    from app_workflow.models import WorkflowTask

    # 找到任务候选人/分配人
    recipients = set()
    if task.assigned_to:
        recipients.add(task.assigned_to)
    if task.candidate_users.exists():
        recipients.update(task.candidate_users.all())
    if task.candidate_groups:
        from app_user.models import ReviewGroup
        groups = ReviewGroup.objects.filter(
            name__in=task.candidate_groups, is_active=True)
        for group in groups:
            recipients.update(group.user_set.all())

    if not recipients:
        return

    # 获取关联的生产工单
    wf_instance = task.instance
    target = wf_instance.content_object if wf_instance else None

    _send_notification_to_recipients(
        recipients=recipients,
        actor=wf_instance.started_by if wf_instance else None,
        verb=f"您有新的待办任务: {task.task_name}",
        target=target,
        action_object=task,
    )
