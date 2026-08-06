import logging

from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import FormSubmission

logger = logging.getLogger(__name__)


@receiver(pre_delete, sender=FormSubmission)
def cleanup_submission_attachments(sender, instance, **kwargs):
    """删除表单提交（含草稿）时，联动删除其附件记录及物理文件。

    附件通过 GenericForeignKey（content_type + object_id）关联提交，
    Django 不会自动级联清理。若不手动处理，附件 object_id 会指向已删除的
    提交，形成孤儿附件，数据库行与磁盘文件永久残留。

    此处硬删除 Attachment 行：会触发 django-cleanup 与 app_attachment 的
    post_delete 信号，自动清理物理文件。
    """
    try:
        from app_attachment.models import Attachment
    except ImportError:
        return

    ct = ContentType.objects.get_for_model(FormSubmission)
    attachments = Attachment.objects.filter(content_type=ct, object_id=instance.pk)
    count = attachments.count()
    if count:
        attachments.delete()
        logger.info('删除提交 #%s 时联动清理 %d 个孤儿附件', instance.pk, count)