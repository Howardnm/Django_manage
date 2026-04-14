import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.db import transaction
from ..models import CatalogCategory, CatalogProduct, MirrorScenario, MirrorCharacteristic
from ..services.material_api import client

logger = logging.getLogger(__name__)

@csrf_exempt
@require_http_methods(["POST"])
def material_webhook_receiver(request):
    """
    完善后的 Webhook 接收端：支持主系统直接控制发布状态
    """
    webhook_secret = request.headers.get('X-Webhook-Secret')
    if not webhook_secret or webhook_secret != getattr(settings, 'WEBHOOK_SECRET_KEY', ''):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=401)

    try:
        payload = json.loads(request.body)
        event_type = payload.get('event_type')
        event_data = payload.get('data', {})
        remote_id = event_data.get('id')

        if not event_type or not remote_id:
            return JsonResponse({'status': 'error', 'message': 'Invalid payload'}, status=400)

        if event_type == 'dimension_updated':
            # 处理场景/特征名称更新
            model_type = event_data.get('model')
            if model_type == 'scenario':
                MirrorScenario.objects.update_or_create(remote_id=remote_id, defaults={'name': event_data['name']})
            elif model_type == 'characteristic':
                MirrorCharacteristic.objects.update_or_create(remote_id=remote_id, defaults={'name': event_data['name']})
            _clear_catalog_caches()
            return JsonResponse({'status': 'success'})

        if event_type == 'material_deleted':
            CatalogProduct.objects.filter(remote_material_id=remote_id).delete()
            _clear_catalog_caches()
            return JsonResponse({'status': 'success'})

        if event_type in ['material_created', 'material_updated']:
            return _sync_with_remote_status(remote_id)
            
        return JsonResponse({'status': 'success'})

    except Exception as e:
        logger.exception(f"Webhook 处理失败: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

def _sync_with_remote_status(remote_id):
    """
    核心同步逻辑：将主系统的 is_published 状态镜像到本地
    """
    remote_data = client.get_material_detail(remote_id)
    if not remote_data:
        return JsonResponse({'status': 'error', 'message': 'Fetch remote failed'}, status=404)

    with transaction.atomic():
        # 1. 分类同步
        remote_cat = remote_data.get('category', {})
        local_category, _ = CatalogCategory.objects.get_or_create(
            remote_type_id=remote_cat.get('id'),
            defaults={'name': remote_cat.get('name', '未分类')}
        )

        # 2. 产品主表同步 (核心：同步 is_published)
        product, _ = CatalogProduct.objects.update_or_create(
            remote_material_id=remote_id,
            defaults={
                'display_name': remote_data.get('grade_name'),
                'category': local_category,
                'description': remote_data.get('description', ''),
                'is_published': remote_data.get('is_published', False) # 自动同步发布状态
            }
        )

        # 3. 场景关联同步
        sce_objs = []
        for s in remote_data.get('scenarios', []):
            s_obj, _ = MirrorScenario.objects.update_or_create(remote_id=s['id'], defaults={'name': s['name']})
            sce_objs.append(s_obj)
        product.scenarios.set(sce_objs)

        # 4. 特征关联同步
        char_objs = []
        for c in remote_data.get('characteristics', []):
            char_obj, _ = MirrorCharacteristic.objects.update_or_create(remote_id=c['id'], defaults={'name': c['name']})
            char_objs.append(char_obj)
        product.characteristics.set(char_objs)

    _clear_catalog_caches()
    return JsonResponse({'status': 'success', 'id': product.id})

def _clear_catalog_caches():
    from django.core.cache import cache
    cache.delete('catalog_nav_tree_structured_v1')
    cache.delete('catalog_nav_tree_mirror_v1')
    cache.delete('catalog_scenarios')
