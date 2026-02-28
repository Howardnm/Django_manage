from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from django.conf import settings

from .models import DifySyncRecord
from .utils import get_document_content

from app_project.models import Project, ProjectNode
from app_repository.models import MaterialLibrary
from app_raw_material.models import RawMaterial
from app_formula.models import LabFormula
from app_process.models import ProcessProfile

# 关键修改：现在只同步这些顶级模型
SYNCED_MODELS = [
    Project, MaterialLibrary, RawMaterial, LabFormula, ProcessProfile
]

def update_or_create_sync_record(instance):
    """一个辅助函数，用于为给定的实例创建或更新同步记录"""
    # 检查实例类型是否在需要同步的列表中
    if type(instance) not in SYNCED_MODELS:
        return

    content_type = ContentType.objects.get_for_model(instance)
    
    model_key = f"{instance._meta.app_label}.{instance._meta.model_name}"
    dataset_id = settings.DIFY_SYNC_CONFIG['DATASETS'].get(model_key)
    if not dataset_id or "YOUR_" in dataset_id:
        return

    record, record_created = DifySyncRecord.objects.get_or_create(
        content_type=content_type,
        object_id=instance.pk,
        defaults={'dify_dataset_id': dataset_id}
    )

    _, text = get_document_content(instance)
    new_hash = record.calculate_hash(text)

    if record_created or record.source_hash != new_hash:
        record.status = DifySyncRecord.SyncStatus.PENDING if record_created else DifySyncRecord.SyncStatus.OUTDATED
        record.source_hash = new_hash
        record.save()

@receiver(post_save)
def handle_synced_model_save(sender, instance, created, **kwargs):
    """监听所有顶级模型的保存事件"""
    if sender in SYNCED_MODELS:
        update_or_create_sync_record(instance)

@receiver(post_delete)
def handle_synced_model_delete(sender, instance, **kwargs):
    """监听所有顶级模型的删除事件"""
    if sender not in SYNCED_MODELS:
        return
    content_type = ContentType.objects.get_for_model(sender)
    DifySyncRecord.objects.filter(
        content_type=content_type,
        object_id=instance.pk
    ).update(status=DifySyncRecord.SyncStatus.DELETED)


# 关键修改：单独处理 ProjectNode 的保存事件
@receiver(post_save, sender=ProjectNode)
def handle_project_node_save(sender, instance, **kwargs):
    """
    当一个项目节点被保存时，我们不为节点本身创建同步记录，
    而是触发对其父级 Project 的同步记录更新。
    """
    project = instance.project
    # 直接调用辅助函数来更新父级项目的同步记录
    update_or_create_sync_record(project)
