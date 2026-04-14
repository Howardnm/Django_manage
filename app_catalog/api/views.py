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
    完善后的 Webhook 接收端：支持物料、场景、特征的全方位动态同步
    """
    # 1. 安全校验
    webhook_secret = request.headers.get('X-Webhook-Secret')
    if not webhook_secret or webhook_secret != getattr(settings, 'WEBHOOK_SECRET_KEY', ''):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=401)

    try:
        payload = json.loads(request.body)
        event_type = payload.get('event_type')
        event_data = payload.get('data', {})
        remote_id = event_data.get('id')
        model_type = event_data.get('model', 'material')

        if not event_type or not remote_id:
            return JsonResponse({'status': 'error', 'message': 'Invalid payload'}, status=400)

        # 2. 分流处理事件
        # A. 维度数据更新 (场景名称/特征名称修改)
        if event_type == 'dimension_updated':
            if model_type == 'scenario':
                MirrorScenario.objects.update_or_create(remote_id=remote_id, defaults={'name': event_data['name']})
            elif model_type == 'characteristic':
                MirrorCharacteristic.objects.update_or_create(remote_id=remote_id, defaults={'name': event_data['name']})
            _clear_catalog_caches()
            return JsonResponse({'status': 'success', 'action': 'dimension_updated'})

        # B. 物料删除
        if event_type == 'material_deleted':
            CatalogProduct.objects.filter(remote_material_id=remote_id).delete()
            _clear_catalog_caches()
            return JsonResponse({'status': 'success', 'action': 'deleted'})

        # C. 物料新增或内容/关联变更
        if event_type in ['material_created', 'material_updated']:
            return _sync_material_full_relations(remote_id)
            
        return JsonResponse({'status': 'success', 'message': 'Event ignored'})

    except Exception as e:
        logger.exception(f"Webhook 处理失败: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

def _sync_material_full_relations(remote_id):
    """
    物料深度同步逻辑：抓取详情并同步本地镜像表和 M2M 关系
    """
    remote_data = client.get_material_detail(remote_id)
    if not remote_data:
        return JsonResponse({'status': 'error', 'message': 'Fetch remote detail failed'}, status=404)

    try:
        with transaction.atomic():
            # 1. 同步分类
            remote_cat = remote_data.get('category', {})
            local_category, _ = CatalogCategory.objects.get_or_create(
                remote_type_id=remote_cat.get('id'),
                defaults={'name': remote_cat.get('name', '未分类')}
            )

            # 2. 同步物料主体 (包含描述镜像)
            product, _ = CatalogProduct.objects.update_or_create(
                remote_material_id=remote_id,
                defaults={
                    'display_name': remote_data.get('grade_name'),
                    'category': local_category,
                    'description': remote_data.get('description', ''),
                }
            )

            # 3. 同步 M2M 场景关系 (自动补全镜像表)
            sce_objs = []
            for s in remote_data.get('scenarios', []):
                s_obj, _ = MirrorScenario.objects.update_or_create(
                    remote_id=s['id'],
                    defaults={'name': s['name']}
                )
                sce_objs.append(s_obj)
            product.scenarios.set(sce_objs)

            # 4. 同步 M2M 特征关系 (自动补全镜像表)
            char_objs = []
            for c in remote_data.get('characteristics', []):
                char_obj, _ = MirrorCharacteristic.objects.update_or_create(
                    remote_id=c['id'],
                    defaults={'name': c['name']}
                )
                char_objs.append(char_obj)
            product.characteristics.set(char_objs)

        _clear_catalog_caches()
        return JsonResponse({'status': 'success', 'action': 'fully_synced', 'id': product.id})
    except Exception as e:
        logger.error(f"Material relation sync failed for ID {remote_id}: {e}")
        raise e

def _clear_catalog_caches():
    """统一清理手册系统的所有导航与详情缓存"""
    from django.core.cache import cache
    cache.delete('catalog_nav_tree_structured_v1')
    cache.delete('catalog_scenarios')
