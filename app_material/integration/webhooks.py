import json
import logging
import requests
from django.conf import settings
from ..models.sync import WebhookTask

logger = logging.getLogger(__name__)

def send_material_webhook(event_type, instance):
    """
    Webhook 任务入队入口：将变更事件保存到数据库任务队列中
    """
    try:
        # 构造 Payload
        # 注意：这里只传基础信息，手册系统接收到后会再通过 API 抓取完整详情
        payload_data = {
            'event_type': event_type,
            'data': {
                'id': instance.id,
                'grade_name': getattr(instance, 'grade_name', str(instance)),
            }
        }
        
        # 创建异步任务记录
        WebhookTask.objects.create(
            event_type=event_type,
            payload=json.dumps(payload_data, ensure_ascii=False),
            status='PENDING'
        )
        logger.info(f"Webhook Task queued: {event_type} for ID {instance.id}")
        return True
    except Exception as e:
        logger.error(f"Failed to queue Webhook Task: {e}")
        return False

def perform_webhook_send(task):
    """
    执行实际的网络发送逻辑 (由管理命令或后台进程调用)
    """
    webhook_url = getattr(settings, 'CATALOG_WEBHOOK_URL', None)
    webhook_secret = getattr(settings, 'WEBHOOK_SECRET_KEY', None)

    if not webhook_url:
        task.status = 'FAILED'
        task.last_error = "CATALOG_WEBHOOK_URL not configured."
        task.save()
        return False

    headers = {
        'Content-Type': 'application/json',
        'X-Webhook-Secret': webhook_secret
    }

    try:
        response = requests.post(
            webhook_url, 
            data=task.payload, 
            headers=headers, 
            timeout=10
        )
        response.raise_for_status()
        
        task.status = 'SUCCESS'
        task.save()
        logger.info(f"Webhook Task {task.id} sent successfully.")
        return True
        
    except Exception as e:
        task.retry_count += 1
        task.last_error = str(e)
        
        if task.retry_count >= task.max_retries:
            task.status = 'FAILED'
            logger.error(f"Webhook Task {task.id} failed after {task.max_retries} retries: {e}")
        else:
            task.status = 'PENDING'
            logger.warning(f"Webhook Task {task.id} retry {task.retry_count}/{task.max_retries} due to: {e}")
            
        task.save()
        return False
