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
    Webhook 接收端：实现结构化关系镜像同步
    """
    webhook_secret = request.headers.get('X-Webhook-Secret')
    expected_secret = getattr(settings, 'WEBHOOK_SECRET_KEY', None)
    
    if not expected_secret or webhook_secret != expected_secret:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=401)

    try:
        payload = json.loads(request.body)
        event_type = payload.get('event_type')
        data = payload.get('data', {})
        remote_id = data.get('id')

        if not event_type or not remote_id:
            return JsonResponse({'status': 'error', 'message': 'Invalid payload'}, status=400)

        if event_type == 'material_deleted':
            CatalogProduct.objects.filter(remote_material_id=remote_id).delete()
            return JsonResponse({'status': 'success', 'action': 'deleted'})

        if event_type in ['material_created', 'material_updated']:
            return _sync_material_relations(remote_id)
            
        return JsonResponse({'status': 'success', 'message': 'Ignored event type'})

    except Exception as e:
        logger.exception(f"Webhook 处理失败: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

def _sync_material_relations(remote_id):
    """
    关系同步核心逻辑
    """
    remote_data = client.get_material_detail(remote_id)
    if not remote_data:
        return JsonResponse({'status': 'error', 'message': 'Fetch remote detail failed'}, status=404)

    with transaction.atomic():
        # 1. 处理分类
        remote_cat = remote_data.get('category', {})
        local_category, _ = CatalogCategory.objects.get_or_create(
            remote_type_id=remote_cat.get('id'),
            defaults={'name': remote_cat.get('name', '未分类')}
        )

        # 2. 处理物料主表
        product, created = CatalogProduct.objects.update_or_create(
            remote_material_id=remote_id,
            defaults={
                'display_name': remote_data.get('grade_name'),
                'category': local_category,
                'description': remote_data.get('description', ''),
            }
        )

        # 3. 处理镜像场景关系 (M2M)
        scenario_objs = []
        for s in remote_data.get('scenarios', []):
            sce_obj, _ = MirrorScenario.objects.update_or_create(
                remote_id=s['id'],
                defaults={'name': s['name']}
            )
            scenario_objs.append(sce_obj)
        product.scenarios.set(scenario_objs)

        # 4. 处理镜像特征关系 (M2M)
        char_objs = []
        for c in remote_data.get('characteristics', []):
            char_obj, _ = MirrorCharacteristic.objects.update_or_create(
                remote_id=c['id'],
                defaults={'name': c['name']}
            )
            char_objs.append(char_obj)
        product.characteristics.set(char_objs)

    # 5. 清理缓存
    from django.core.cache import cache
    cache.delete('catalog_nav_tree_mirror_v1')
    cache.delete('catalog_nav_tree_optimized')

    return JsonResponse({'status': 'success', 'action': 'synced', 'id': product.id})
