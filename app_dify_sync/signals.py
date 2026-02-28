from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from django.conf import settings

from .models import DifySyncRecord
from .utils import get_document_content

from app_project.models import Project
from app_repository.models import MaterialLibrary
from app_raw_material.models import RawMaterial
from app_formula.models import LabFormula
from app_process.models import ProcessProfile

# 从 settings.py 获取需要同步的模型列表
SYNCED_MODELS_CONFIG = settings.DIFY_SYNC_CONFIG['DATASETS']
SYNCED_MODELS = [
    Project, MaterialLibrary, RawMaterial, LabFormula, ProcessProfile
]

@receiver(post_save)
def handle_model_save(sender, instance, created, **kwargs):
    if sender not in SYNCED_MODELS:
        return

    content_type = ContentType.objects.get_for_model(sender)
    
    # 从 settings 获取对应的 dataset_id
    model_key = f"{sender._meta.app_label}.{sender._meta.model_name}"
    dataset_id = SYNCED_MODELS_CONFIG.get(model_key)
    if not dataset_id:
        return # 如果没有配置数据集ID，则不处理

    # 获取或创建同步记录
    record, record_created = DifySyncRecord.objects.get_or_create(
        content_type=content_type,
        object_id=instance.pk,
        defaults={'dify_dataset_id': dataset_id}
    )

    # 获取格式化后的内容和名称
    name, text = get_document_content(instance)
    new_hash = record.calculate_hash(text)

    # 只有在哈希值不同或记录是新创建时才更新状态
    if record_created or record.source_hash != new_hash:
        record.status = DifySyncRecord.SyncStatus.PENDING if record_created else DifySyncRecord.SyncStatus.OUTDATED
        record.source_hash = new_hash
        record.save()

@receiver(post_delete)
def handle_model_delete(sender, instance, **kwargs):
    if sender not in SYNCED_MODELS:
        return

    content_type = ContentType.objects.get_for_model(sender)
    
    DifySyncRecord.objects.filter(
        content_type=content_type,
        object_id=instance.pk
    ).update(status=DifySyncRecord.SyncStatus.DELETED)
