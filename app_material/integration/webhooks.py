import json
import logging
import requests
from django.conf import settings
from ..models.sync import WebhookTask

logger = logging.getLogger(__name__)

def send_material_webhook(event_type, instance):
    """
    Webhook 任务入队入口
    支持物料变更事件和维度数据(场景/特征)变更事件
    """
    try:
        # 根据模型类型构造数据负载
        data = {'id': instance.id}
        
        if hasattr(instance, 'grade_name'):
            data['name'] = instance.grade_name
            data['model'] = 'material'
        elif hasattr(instance, 'name'):
            data['name'] = instance.name
            # 判断模型属于场景还是特征
            data['model'] = 'scenario' if 'Scenario' in instance.__class__.__name__ else 'characteristic'

        payload_data = {
            'event_type': event_type,
            'data': data
        }
        
        # 保存到任务队列
        WebhookTask.objects.create(
            event_type=event_type,
            payload=json.dumps(payload_data, ensure_ascii=False),
            status='PENDING'
        )
        logger.info(f"Webhook Task Qued: {event_type} for {data['model']} {instance.id}")
        return True
    except Exception as e:
        logger.error(f"Failed to queue Webhook Task: {e}")
        return False

def perform_webhook_send(task):
    """由守护进程或管理命令调用，执行实际发送"""
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
