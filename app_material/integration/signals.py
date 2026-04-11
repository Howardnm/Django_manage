import json
import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from ..models import MaterialType, MaterialLibrary, WebhookTask

logger = logging.getLogger(__name__)

def create_webhook_task(event_type, instance_data):
    """
    创建并保存一个 WebhookTask 实例到数据库，由后台进程处理发送
    """
    try:
        payload = {
            'event_type': event_type,
            'data': instance_data
        }
        WebhookTask.objects.create(
            event_type=event_type,
            payload=json.dumps(payload)
        )
        logger.info(f"Integration: Webhook Task queued for {event_type} (ID: {instance_data.get('id')})")
    except Exception as e:
        logger.error(f"Integration: Failed to queue Webhook Task: {e}")


# --- 监听核心材料库模型变更 ---

@receiver(post_save, sender=MaterialType)
def material_type_saved(sender, instance, created, **kwargs):
    event_type = 'type_created' if created else 'type_updated'
    data = {'id': instance.id, 'name': instance.name}
    transaction.on_commit(lambda: create_webhook_task(event_type, data))

@receiver(post_delete, sender=MaterialType)
def material_type_deleted(sender, instance, **kwargs):
    data = {'id': instance.id, 'name': instance.name}
    transaction.on_commit(lambda: create_webhook_task('type_deleted', data))

@receiver(post_save, sender=MaterialLibrary)
def material_saved(sender, instance, created, **kwargs):
    event_type = 'material_created' if created else 'material_updated'
    data = {'id': instance.id, 'grade_name': instance.grade_name}
    transaction.on_commit(lambda: create_webhook_task(event_type, data))

@receiver(post_delete, sender=MaterialLibrary)
def material_deleted(sender, instance, **kwargs):
    data = {'id': instance.id, 'grade_name': instance.grade_name}
    transaction.on_commit(lambda: create_webhook_task('material_deleted', data))
