"""
附件相关信号处理

当父对象被删除时，自动清理关联的附件记录。
由于 Attachment 使用 GenericForeignKey 且 content_type
设置了 on_delete=CASCADE，父对象删除时 Django 会自动级联删除
Attachment 记录。此信号文件预留用于额外的清理逻辑。
"""
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Attachment


@receiver(post_delete, sender=Attachment)
def cleanup_attachment_file(sender, instance, **kwargs):
    """
    删除 Attachment 记录后，清理物理文件。

    注意：django-cleanup 已在 INSTALLED_APPS 中，
    会自动处理 FileField 的文件清理。
    此信号作为备份，确保在 django-cleanup 未启用时也能清理。
    """
    if instance.file:
        try:
            instance.file.delete(save=False)
        except Exception:
            # 文件可能已被 django-cleanup 删除，忽略异常
            pass
