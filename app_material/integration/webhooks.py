import json
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

def perform_webhook_send(task):
    """
    执行实际的 Webhook 发送逻辑，并更新任务状态
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
        # payload 在模型中是以字符串存储的 JSON
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
            task.status = 'PENDING' # 回到等待状态，由处理器下次重试
            logger.warning(f"Webhook Task {task.id} retry {task.retry_count}/{task.max_retries} due to: {e}")
            
        task.save()
        return False
