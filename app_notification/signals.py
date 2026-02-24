from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from app_project.models import ProjectNode
from .models import Notification
from .thread_local import get_current_user

def _send_notification_to_recipients(project, actor, verb, target, action_object=None):
    """
    一个内部辅助函数，它会计算所有收件人（包括有权限的团队成员）并发送通知。
    """
    recipients = set()

    # 1. 添加项目负责人
    if project.manager:
        recipients.add(project.manager)
        
        # 2. 查找负责人所在的所有组
        for group in project.manager.groups.all():
            # 3. 获取组内所有成员
            for member in group.user_set.all():
                # 关键修改：检查成员是否拥有查看项目的权限
                if member.has_perm('app_project.view_project'):
                    recipients.add(member)

    # 4. 添加所有超级管理员 (他们默认拥有所有权限)
    superusers = User.objects.filter(is_superuser=True)
    recipients.update(superusers)

    # 5. 批量创建通知，并排除操作者本人
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


@receiver(post_save, sender=ProjectNode)
def project_node_saved_handler(sender, instance, created, **kwargs):
    """
    当 ProjectNode 模型被保存时 (创建或更新)，发送通知。
    """
    node = instance
    project = node.project
    actor = get_current_user() or project.manager
    verb = f"{'创建了' if created else '更新了'}进度节点【{node.get_stage_display()}】"

    # 调用重构后的辅助函数
    _send_notification_to_recipients(project, actor, verb, target=node, action_object=project)
