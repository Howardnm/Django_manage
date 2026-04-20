import logging
from django.db import transaction
from django.http import JsonResponse
from django.core.cache import cache
from ..models import CatalogCategory, CatalogProduct, MirrorScenario, MirrorCharacteristic, CatalogMember
from ..services.material_api import client

logger = logging.getLogger(__name__)

class WebhookHandler:
    """
    模块化 Webhook 处理器：解耦不同类型的同步逻辑
    """
    
    @staticmethod
    def handle_member_sync(data):
        """同步会员基础资料"""
        try:
            member, _ = CatalogMember.objects.update_or_create(
                remote_member_token=data['token'],
                defaults={
                    'display_name': data.get('display_name', ''),
                    'role': data.get('role', 'CUSTOMER'),
                    'is_active': data.get('is_active', True)
                }
            )
            return JsonResponse({'status': 'success', 'id': member.id})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f"Member sync failed: {str(e)}"}, status=500)

    @staticmethod
    def handle_dimension_update(model_type, data):
        """同步公共维度数据 (场景/特征)"""
        remote_id = data.get('id')
        name = data.get('name')
        
        if model_type == 'scenario':
            MirrorScenario.objects.update_or_create(remote_id=remote_id, defaults={'name': name})
        elif model_type == 'characteristic':
            MirrorCharacteristic.objects.update_or_create(remote_id=remote_id, defaults={'name': name})
            
        WebhookHandler._clear_cache()
        return JsonResponse({'status': 'success'})

    @staticmethod
    def handle_material_delete(remote_id):
        """同步删除物料"""
        CatalogProduct.objects.filter(remote_material_id=remote_id).delete()
        WebhookHandler._clear_cache()
        return JsonResponse({'status': 'success'})

    @staticmethod
    def handle_material_save(remote_id):
        """同步创建/更新物料详情及其关联关系"""
        remote_data = client.get_material_detail(remote_id)
        if not remote_data:
            return JsonResponse({'status': 'error', 'message': 'Fetch material detail failed'}, status=404)

        try:
            with transaction.atomic():
                # 1. 处理分类
                remote_cat = remote_data.get('category', {})
                local_category, _ = CatalogCategory.objects.get_or_create(
                    remote_type_id=remote_cat.get('id'),
                    defaults={'name': remote_cat.get('name', '未分类')}
                )

                # 2. 处理主产品
                product, _ = CatalogProduct.objects.update_or_create(
                    remote_material_id=remote_id,
                    defaults={
                        'display_name': remote_data.get('grade_name'),
                        'category': local_category,
                        'description': remote_data.get('description', ''),
                        'is_published': remote_data.get('is_published', False)
                    }
                )

                # 3. 处理场景多对多
                sce_objs = [
                    MirrorScenario.objects.update_or_create(remote_id=s['id'], defaults={'name': s['name']})[0] 
                    for s in remote_data.get('scenarios', [])
                ]
                product.scenarios.set(sce_objs)

                # 4. 处理特征多对多
                char_objs = [
                    MirrorCharacteristic.objects.update_or_create(remote_id=c['id'], defaults={'name': c['name']})[0] 
                    for c in remote_data.get('characteristics', [])
                ]
                product.characteristics.set(char_objs)

            WebhookHandler._clear_cache()
            return JsonResponse({'status': 'success', 'id': product.id})
        except Exception as e:
            logger.exception("Material relations sync failed")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    @staticmethod
    def _clear_cache():
        """清理前端导航树和统计缓存"""
        cache.delete('catalog_nav_tree_structured_v2')
        cache.delete('catalog_scenarios')
