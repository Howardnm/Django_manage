"""配方模块的信号处理。

`Attachment` 通过 GenericForeignKey（content_type + object_id）关联父对象，
删除父对象时 Django **不会**自动级联 —— `content_type` 上的 CASCADE 只在
ContentType 行本身被删除时触发，`object_id` 是普通整数列。

不手动清理的话，附件行会指向已删除的配方/测试结果，数据库行与磁盘文件永久残留。
（`app_attachment/signals.py` 的模块 docstring 声称会自动级联，那是错的。）
"""
import logging

from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import FormulaTestResult, LabFormula

logger = logging.getLogger(__name__)


def _purge_attachments(model, pk, label):
    """删除 model(pk) 名下全部附件行。

    硬删除 Attachment 行：会触发 app_attachment 的 post_delete 信号与
    django-cleanup，自动清理磁盘文件。
    """
    try:
        from app_attachment.models import Attachment
    except ImportError:  # 附件模块未安装时静默跳过
        return

    content_type = ContentType.objects.get_for_model(model)
    attachments = Attachment.objects.filter(content_type=content_type, object_id=pk)
    count = attachments.count()
    if count:
        attachments.delete()
        logger.info('删除%s #%s 时联动清理 %d 个孤儿附件', label, pk, count)


@receiver(pre_delete, sender=LabFormula)
def cleanup_formula_attachments(sender, instance, **kwargs):
    """删除配方（实验单版本）时清理其名下的附件。"""
    _purge_attachments(LabFormula, instance.pk, '配方')


@receiver(pre_delete, sender=FormulaTestResult)
def cleanup_test_result_attachments(sender, instance, **kwargs):
    """删除测试结果时清理其名下的附件（检测报告等）。

    注意：配方被删除时其测试结果会级联删除，每个结果都会走这条信号，
    因此挂在测试结果上的报告不会因为父配方消失而变成孤儿。
    """
    _purge_attachments(FormulaTestResult, instance.pk, '测试结果')
