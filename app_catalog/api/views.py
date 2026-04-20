import json
import logging
import traceback
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from .handlers import WebhookHandler

logger = logging.getLogger(__name__)

@csrf_exempt
@require_http_methods(["POST"])
def material_webhook_receiver(request):
    """
    通用 Webhook 接收网关。
    """
    # 1. 安全性检查
    webhook_secret = request.headers.get('X-Webhook-Secret')
    if not webhook_secret or webhook_secret != getattr(settings, 'WEBHOOK_SECRET_KEY', ''):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized (Secret mismatch)'}, status=401)

    try:
        payload = json.loads(request.body)
        event_type = payload.get('event_type')
        model_type = payload.get('model')
        data = payload.get('data', {})

        if not event_type or not data:
            return JsonResponse({'status': 'error', 'message': 'Invalid payload structure'}, status=400)

        # 2. 逻辑分发 (基于对象模块化处理器)
        # A. 会员同步
        if model_type == 'member' and event_type == 'member_sync':
            return WebhookHandler.handle_member_sync(data)

        # B. 基础维度更新 (场景/特征)
        if event_type == 'dimension_updated':
            return WebhookHandler.handle_dimension_update(model_type, data)

        # C. 物料主数据同步
        remote_id = data.get('id')
        if event_type == 'material_deleted':
            return WebhookHandler.handle_material_delete(remote_id)

        if event_type in ['material_created', 'material_updated']:
            # 此处最容易抛出 500 错误，进行拦截
            return WebhookHandler.handle_material_save(remote_id)
            
        return JsonResponse({'status': 'success', 'message': f'Event {event_type} ignored'})

    except Exception as e:
        # 核心增强：打印完整堆栈到子系统日志，并将简短错误信息回传主系统
        stack_trace = traceback.format_exc()
        logger.error(f"Webhook Gateway Internal Error: {str(e)}\n{stack_trace}")
        return JsonResponse({
            'status': 'error', 
            'message': f"Catalog system error: {str(e)}"
        }, status=500)
