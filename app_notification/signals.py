from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from app_project.models import ProjectNode
from .models import Notification
from .thread_local import get_current_user

def _send_notification_to_recipients(recipients, actor, verb, target, action_object=None):
    """一个内部函数，用于创建并发送通知"""
    notifications_to_create = [
        Notification(
            recipient=recipient,
            actor=actor,
            verb=verb,
            target=target,
            action_object=action_object
        )
        for recipient in recipients if not (actor and recipient == actor)
    ]
    if notifications_to_create:
        Notification.objects.bulk_create(notifications_to_create)

# 项目级别的通知信号已被移除

@receiver(post_save, sender=ProjectNode)
def project_node_saved_handler(sender, instance, created, **kwargs):
    """
    当 ProjectNode 模型被保存时，仅在“更新”时发送通知。
    """
    # 关键修改：如果节点是新创建的，则不发送通知。
    if created:
        return

    node = instance
    project = node.project
    actor = get_current_user() or project.manager # 优先从中间件获取，否则回退到项目负责人
    verb = f"更新了进度节点 '{node.get_stage_display()}'"

    # 确定接收者
    recipients = set()
    if project.manager:
        recipients.add(project.manager)
        # 添加组内有权限的成员
        for group in project.manager.groups.all():
            for member in group.user_set.all():
                if member.has_perm('app_project.view_project'):
                    recipients.add(member)

    # 添加所有超级管理员
    superusers = User.objects.filter(is_superuser=True)
    recipients.update(superusers)

    # 发送通知，目标是节点本身，上下文是项目
    _send_notification_to_recipients(recipients, actor, verb, target=node, action_object=project)
