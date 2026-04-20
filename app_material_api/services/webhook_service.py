import json
import logging
import requests
from django.conf import settings
from app_material.models.sync import WebhookTask

logger = logging.getLogger(__name__)

class WebhookService:
    """
    主系统 Webhook 核心引擎：
    负责将本地变更封装为任务包，并可靠地分发给子系统（电子手册等）。
    """
    
    @staticmethod
    def queue_task(event_type, model_name, data):
        """将同步任务存入本地队列（即 WebhookTask 表）"""
        try:
            full_payload = {
                'event_type': event_type,
                'model': model_name,
                'data': data
            }
            task = WebhookTask.objects.create(
                event_type=event_type,
                payload=json.dumps(full_payload, ensure_ascii=False),
                status='PENDING'
            )
            return task
        except Exception as e:
            logger.error(f"Webhook Queueing failed: {e}")
            return None

    @staticmethod
    def notify_material_change(event_type, instance):
        """针对物料变化的特化通知方法"""
        data = {
            'id': instance.id,
            'grade_name': getattr(instance, 'grade_name', str(instance)),
            'is_published': getattr(instance, 'is_published', False)
        }
        return WebhookService.queue_task(event_type, 'material', data)

    @staticmethod
    def notify_dimension_change(event_type, model_name, instance):
        """针对维度（场景、特征）变化的特化通知方法"""
        data = {
            'id': instance.id,
            'name': instance.name
        }
        return WebhookService.queue_task(event_type, model_name, data)

    @staticmethod
    def notify_member_sync(user_profile_data):
        """针对会员账号的同步通知"""
        return WebhookService.queue_task('member_sync', 'member', user_profile_data)

    @staticmethod
    def dispatch_task(task):
        """执行实际的网络发送（可供管理命令或 Celery 调用）"""
        target_url = getattr(settings, 'CATALOG_WEBHOOK_URL', None)
        secret = getattr(settings, 'WEBHOOK_SECRET_KEY', None)

        if not target_url:
            error_msg = "Target URL (CATALOG_WEBHOOK_URL) not configured in settings."
            task.status = 'FAILED'
            task.last_error = error_msg
            task.save()
            logger.error(f"Webhook dispatch failed for task {task.id}: {error_msg}")
            return False

        if not secret:
            error_msg = "Webhook Secret Key (WEBHOOK_SECRET_KEY) not configured in settings."
            task.status = 'FAILED'
            task.last_error = error_msg
            task.save()
            logger.error(f"Webhook dispatch failed for task {task.id}: {error_msg}")
            return False

        headers = {
            'Content-Type': 'application/json',
            'X-Webhook-Secret': secret
        }

        try:
            response = requests.post(target_url, data=task.payload, headers=headers, timeout=10)
            response.raise_for_status()  # 检查 HTTP 状态码，非 2xx 抛出异常
            task.status = 'SUCCESS'
            task.save()
            logger.info(f"Webhook task {task.id} dispatched successfully to {target_url}")
            return True
        except requests.exceptions.RequestException as e:
            error_msg = f"Network or HTTP error: {e}"
            if hasattr(e, 'response') and e.response is not None:
                error_msg += f" | Response status: {e.response.status_code}"
                error_msg += f" | Response body: {e.response.text}"
            
            task.retry_count += 1
            task.last_error = error_msg
            if task.retry_count >= task.max_retries:
                task.status = 'FAILED'
            task.save()
            logger.error(f"Webhook dispatch failed for task {task.id} to {target_url}: {error_msg}")
            return False
        except Exception as e:
            error_msg = f"Unexpected error during webhook dispatch: {e}"
            task.retry_count += 1
            task.last_error = error_msg
            if task.retry_count >= task.max_retries:
                task.status = 'FAILED'
            task.save()
            logger.error(f"Webhook dispatch failed for task {task.id} to {target_url}: {error_msg}")
            return False
