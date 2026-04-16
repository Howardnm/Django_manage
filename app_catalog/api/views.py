import json
import logging
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.db import transaction
from django.utils import timezone # 导入 timezone
from ..models import CatalogCategory, CatalogProduct, MirrorScenario, MirrorCharacteristic, CatalogMember, VisitorLog
from ..services.material_api import client

logger = logging.getLogger(__name__)

@csrf_exempt
@require_http_methods(["POST"])
def material_webhook_receiver(request):
    webhook_secret = request.headers.get('X-Webhook-Secret')
    if not webhook_secret or webhook_secret != getattr(settings, 'WEBHOOK_SECRET_KEY', ''):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=401)

    try:
        payload = json.loads(request.body)
        event_type = payload.get('event_type')
        model_type = payload.get('model')
        event_data = payload.get('data', {})

        if not event_type or not event_data:
            return JsonResponse({'status': 'error', 'message': 'Invalid payload'}, status=400)

        if model_type == 'member' and event_type == 'member_sync':
            return _sync_member_mirror(event_data)

        if event_type == 'dimension_updated':
            remote_id = event_data.get('id')
            if model_type == 'scenario':
                MirrorScenario.objects.update_or_create(remote_id=remote_id, defaults={'name': event_data['name']})
            elif model_type == 'characteristic':
                MirrorCharacteristic.objects.update_or_create(remote_id=remote_id, defaults={'name': event_data['name']})
            _clear_catalog_caches()
            return JsonResponse({'status': 'success'})

        remote_id = event_data.get('id')
        if event_type == 'material_deleted':
            CatalogProduct.objects.filter(remote_material_id=remote_id).delete()
            _clear_catalog_caches()
            return JsonResponse({'status': 'success'})

        if event_type in ['material_created', 'material_updated']:
            return _sync_material_full_relations(remote_id)
            
        return JsonResponse({'status': 'success'})

    except Exception as e:
        logger.exception(f"Webhook 处理失败: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

def _sync_member_mirror(data):
    try:
        member, created = CatalogMember.objects.update_or_create(
            remote_member_token=data['token'],
            defaults={
                'username': data['username'],
                'display_name': data['display_name'],
                'email': data.get('email', ''),
                'role': data['role'],
                'is_active': data.get('is_active', True)
            }
        )
        return JsonResponse({'status': 'success', 'id': member.id})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

# --- 行为日志回传工具 (修复时区警告) ---
def push_member_activity_feedback(member_token, action, target_name):
    """
    将特定的会员行为立即反馈给主系统
    """
    payload = {
        'logs': [
            {
                'member_token': member_token,
                'action': action,
                'target_name': target_name,
                'timestamp': timezone.now().isoformat() # 使用带时区的时间
            }
        ]
    }
    
    try:
        url = f"{settings.REMOTE_API_BASE_URL}auth/feedback/"
        headers = {
            'X-Internal-Api-Token': settings.INTERNAL_API_TOKEN,
            'Content-Type': 'application/json'
        }
        requests.post(url, json=payload, headers=headers, timeout=5)
    except Exception as e:
        logger.error(f"Feedback push failed: {e}")

def _sync_material_full_relations(remote_id):
    remote_data = client.get_material_detail(remote_id)
    if not remote_data: return JsonResponse({'status': 'error', 'message': 'Fetch failed'}, status=404)
    with transaction.atomic():
        remote_cat = remote_data.get('category', {})
        local_category, _ = CatalogCategory.objects.get_or_create(remote_type_id=remote_cat.get('id'), defaults={'name': remote_cat.get('name', '未分类')})
        product, _ = CatalogProduct.objects.update_or_create(remote_material_id=remote_id, defaults={'display_name': remote_data.get('grade_name'), 'category': local_category, 'description': remote_data.get('description', ''), 'is_published': remote_data.get('is_published', False)})
        sce_objs = [MirrorScenario.objects.update_or_create(remote_id=s['id'], defaults={'name': s['name']})[0] for s in remote_data.get('scenarios', [])]
        product.scenarios.set(sce_objs)
        char_objs = [MirrorCharacteristic.objects.update_or_create(remote_id=c['id'], defaults={'name': c['name']})[0] for c in remote_data.get('characteristics', [])]
        product.characteristics.set(char_objs)
    _clear_catalog_caches()
    return JsonResponse({'status': 'success', 'id': product.id})

def _clear_catalog_caches():
    from django.core.cache import cache
    cache.delete('catalog_nav_tree_structured_v2')
    cache.delete('catalog_scenarios')
