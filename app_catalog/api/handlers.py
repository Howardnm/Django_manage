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
            logger.error(f"Member sync data processing error: {e}")
            return JsonResponse({'status': 'error', 'message': f"Member processing error: {str(e)}"}, status=500)

    @staticmethod
    def handle_dimension_update(model_type, data):
        """同步公共维度数据 (场景/特征)"""
        try:
            remote_id = data.get('id')
            name = data.get('name')
            
            if model_type == 'scenario':
                MirrorScenario.objects.update_or_create(remote_id=remote_id, defaults={'name': name})
            elif model_type == 'characteristic':
                MirrorCharacteristic.objects.update_or_create(remote_id=remote_id, defaults={'name': name})
                
            WebhookHandler._clear_cache()
            return JsonResponse({'status': 'success'})
        except Exception as e:
            logger.error(f"Dimension update error: {e}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    @staticmethod
    def handle_material_delete(remote_id):
        """同步删除物料"""
        try:
            CatalogProduct.objects.filter(remote_material_id=remote_id).delete()
            WebhookHandler._clear_cache()
            return JsonResponse({'status': 'success'})
        except Exception as e:
            logger.error(f"Material delete error: {e}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    @staticmethod
    def handle_material_save(remote_id):
        """同步创建/更新物料详情及其关联关系"""
        # 低代码调用 Service
        remote_data = client.fetch_material_details(remote_id)
        
        if not remote_data:
            msg = f"Fetch failed: Main system API returned no data for ID {remote_id}"
            logger.error(msg)
            return JsonResponse({'status': 'error', 'message': msg}, status=404)

        try:
            with transaction.atomic():
                # 1. 处理分类
                remote_cat = remote_data.get('category')
                if not remote_cat:
                    # 容错：如果主系统没分类，尝试归类到未分类
                    local_category, _ = CatalogCategory.objects.get_or_create(
                        name="未分类", 
                        defaults={'remote_type_id': -1}
                    )
                else:
                    local_category, _ = CatalogCategory.objects.update_or_create(
                        remote_type_id=remote_cat.get('id'),
                        defaults={'name': remote_cat.get('name', '未分类')}
                    )

                # 2. 处理主产品 (更新 4D 字段)
                product, _ = CatalogProduct.objects.update_or_create(
                    remote_material_id=remote_id,
                    defaults={
                        'display_name': remote_data.get('grade_name', 'Unnamed'),
                        'category': local_category,
                        'description': remote_data.get('description', ''),
                        'is_published': remote_data.get('is_published', False)
                    }
                )

                # 3. 处理场景多对多
                sce_data = remote_data.get('scenarios', [])
                sce_objs = []
                for s in sce_data:
                    obj, _ = MirrorScenario.objects.get_or_create(
                        remote_id=s['id'], 
                        defaults={'name': s['name']}
                    )
                    sce_objs.append(obj)
                product.scenarios.set(sce_objs)

                # 4. 处理特征多对多
                char_data = remote_data.get('characteristics', [])
                char_objs = []
                for c in char_data:
                    obj, _ = MirrorCharacteristic.objects.get_or_create(
                        remote_id=c['id'], 
                        defaults={'name': c['name']}
                    )
                    char_objs.append(obj)
                product.characteristics.set(char_objs)

            WebhookHandler._clear_cache()
            return JsonResponse({'status': 'success', 'id': product.id})
        except Exception as e:
            logger.exception(f"Detailed database sync error for ID {remote_id}")
            return JsonResponse({'status': 'error', 'message': f"DB sync error: {str(e)}"}, status=500)

    @staticmethod
    def _clear_cache():
        """清理缓存"""
        cache.delete('catalog_nav_tree_v2')
        cache.delete('catalog_scenarios')
