import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings # 导入 settings
from ..models import CatalogCategory, CatalogProduct
from ..services.material_api import client

logger = logging.getLogger(__name__)

@csrf_exempt
@require_http_methods(["POST"])
def material_webhook_receiver(request):
    """
    完善后的 Webhook 接收端：支持安全校验、自动补全分类
    """
    # 【新增】安全性校验：验证 Webhook Secret
    webhook_secret = request.headers.get('X-Webhook-Secret')
    expected_secret = getattr(settings, 'WEBHOOK_SECRET_KEY', None)
    
    if not expected_secret or webhook_secret != expected_secret:
        logger.warning(f"Webhook 拒绝访问：无效的 Secret Key。来源IP: {request.META.get('REMOTE_ADDR')}")
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=401)

    try:
        payload = json.loads(request.body)
        event_type = payload.get('event_type')
        data = payload.get('data', {})
        remote_id = data.get('id')

        if not event_type or not remote_id:
            return JsonResponse({'status': 'error', 'message': 'Invalid payload structure'}, status=400)

        # 分流处理
        if event_type.startswith('material_'):
            return _handle_material_event(event_type, remote_id)
        elif event_type.startswith('type_'):
            return _handle_type_event(event_type, remote_id)
        
        return JsonResponse({'status': 'error', 'message': 'Unknown event type'}, status=400)

    except Exception as e:
        logger.exception(f"Webhook 严重处理异常: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

def _get_or_sync_category(remote_category_id):
    try:
        category = CatalogCategory.objects.get(remote_type_id=remote_category_id)
        return category
    except CatalogCategory.DoesNotExist:
        logger.info(f"本地缺失分类 ID {remote_category_id}，正在尝试从远程 API 同步...")
        remote_type_data = client._get(f'types/{remote_category_id}/')
        if remote_type_data:
            category, created = CatalogCategory.objects.get_or_create(
                remote_type_id=remote_category_id,
                defaults={
                    'name': remote_type_data.get('name', '未命名分类'),
                    'is_active': True
                }
            )
            return category
    return None

def _handle_material_event(event_type, remote_id):
    if event_type == 'material_deleted':
        CatalogProduct.objects.filter(remote_material_id=remote_id).delete()
        return JsonResponse({'status': 'success', 'action': 'deleted'})

    remote_data = client.get_material_detail(remote_id)
    if not remote_data:
        return JsonResponse({'status': 'error', 'message': 'Remote data fetch failed'}, status=404)

    remote_cat_id = remote_data.get('category', {}).get('id')
    local_category = _get_or_sync_category(remote_cat_id)
    
    if not local_category:
        return JsonResponse({'status': 'error', 'message': f'Category {remote_cat_id} synchronization failed'}, status=500)

    product, created = CatalogProduct.objects.update_or_create(
        remote_material_id=remote_id,
        defaults={
            'category': local_category,
            'display_name': remote_data.get('grade_name', '未知牌号'),
        }
    )
    
    return JsonResponse({
        'status': 'success', 
        'action': 'synced', 
        'is_new': created,
        'display_name': product.display_name
    })

def _handle_type_event(event_type, remote_id):
    if event_type == 'type_deleted':
        CatalogCategory.objects.filter(remote_type_id=remote_id).delete()
        return JsonResponse({'status': 'success', 'action': 'category_deleted'})

    remote_type_data = client._get(f'types/{remote_id}/')
    if remote_type_data:
        category, created = CatalogCategory.objects.update_or_create(
            remote_type_id=remote_id,
            defaults={'name': remote_type_data.get('name')}
        )
        return JsonResponse({'status': 'success', 'action': 'category_synced', 'is_new': created})
    
    return JsonResponse({'status': 'error', 'message': 'Remote category data fetch failed'}, status=404)
