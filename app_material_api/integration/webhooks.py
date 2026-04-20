import logging
from ..services.webhook_service import WebhookService

logger = logging.getLogger(__name__)

# --- 兼容性映射：将原有函数指向新的 Service 类 ---
# 这样做可以确保 app_repository 等外部模块不需要改动代码即可直接使用新引擎

def send_data_sync_webhook(event_type, model_name, data_payload):
    return WebhookService.queue_task(event_type, model_name, data_payload)

def send_material_webhook(event_type, instance):
    return WebhookService.notify_material_change(event_type, instance)

def perform_webhook_send(task):
    return WebhookService.dispatch_task(task)
