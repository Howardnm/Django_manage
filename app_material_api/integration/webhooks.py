import json
import logging
import requests
from django.conf import settings
from app_material.models.sync import WebhookTask # 保持对 app_material.models.sync 的引用

logger = logging.getLogger(__name__)

def send_data_sync_webhook(event_type, model_name, data_payload):
    """
    通用 Webhook 任务入队函数
    """
    try:
        full_payload = {
            'event_type': event_type,
            'model': model_name,
            'data': data_payload
        }
        
        # 任务表依然留在 app_material 的 models 中，因为它属于核心数据库
        WebhookTask.objects.create(
            event_type=event_type,
            payload=json.dumps(full_payload, ensure_ascii=False),
            status='PENDING'
        )
        logger.info(f"Webhook Task Qued: {event_type} for {model_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to queue Webhook Task for {model_name}: {e}")
        return False

def send_material_webhook(event_type, instance):
    """
    发送物料 Webhook：包含发布状态
    """
    data = {
        'id': instance.id,
        'grade_name': getattr(instance, 'grade_name', str(instance)),
        'is_published': getattr(instance, 'is_published', False),
        'model': 'material'
    }
    return send_data_sync_webhook(event_type, 'material', data)

def perform_webhook_send(task):
    """执行实际的网络发送逻辑"""
    webhook_url = getattr(settings, 'CATALOG_WEBHOOK_URL', None)
    webhook_secret = getattr(settings, 'WEBHOOK_SECRET_KEY', None)

    if not webhook_url:
        task.status = 'FAILED'
        task.last_error = "Target URL not configured."
        task.save()
        return False

    headers = {
        'Content-Type': 'application/json',
        'X-Webhook-Secret': webhook_secret
    }

    try:
        response = requests.post(webhook_url, data=task.payload, headers=headers, timeout=10)
        response.raise_for_status()
        task.status = 'SUCCESS'
        task.save()
        return True
    except Exception as e:
        task.retry_count += 1
        task.last_error = str(e)
        if task.retry_count >= task.max_retries:
            task.status = 'FAILED'
        task.save()
        return False
