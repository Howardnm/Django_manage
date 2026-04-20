import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings

# 使用绝对导入，防止在 management 命令中出现路径解析错误
from app_catalog.models.catalog import CatalogCategory, CatalogProduct, MirrorScenario, MirrorCharacteristic
from app_catalog.services.material_api import client

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    """
    运行命令：python manage.py sync_catalog
    功能：从主系统 API 全量抓取并构建本地关系型镜像。
    安全：自动使用 settings.INTERNAL_API_TOKEN 进行鉴权。
    """
    help = '从主系统 API 全量同步物料、场景、特性及分类数据'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("\n🚀 开始全量镜像同步任务 (4D 安全架构接入)..."))
        
        # 1. 同步公共维度
        self._sync_scenarios()
        self._sync_categories()
        
        # 2. 同步物料主档 (含关系链)
        self._sync_products_paged()
        
        self.stdout.write(self.style.SUCCESS('\n✅ 镜像同步任务全部完成！'))

    def _sync_scenarios(self):
        self.stdout.write("   -> 正在同步应用场景数据...")
        data = client.get_all_scenarios()
        # 处理 DRF 返回的列表或带 results 的字典
        scenarios = data.get('results', []) if isinstance(data, dict) else (data or [])
        
        count = 0
        for s in scenarios:
            MirrorScenario.objects.update_or_create(
                remote_id=s['id'], 
                defaults={'name': s['name']}
            )
            count += 1
        self.stdout.write(f"      [OK] 已同步 {count} 个场景")

    def _sync_categories(self):
        self.stdout.write("   -> 正在同步材质分类 (MaterialType)...")
        # 直接通过底层执行器获取
        data = client._execute_request('GET', 'types/')
        types = data.get('results', []) if data else []
        
        for t in types:
            CatalogCategory.objects.update_or_create(
                remote_type_id=t['id'], 
                defaults={'name': t['name'], 'is_active': True}
            )
        self.stdout.write(f"      [OK] 已同步 {len(types)} 个分类")

    def _sync_products_paged(self):
        self.stdout.write("   -> 正在同步物料主档及关系链 (支持 API 分页)...")
        
        # 初始获取第一页
        response_data = client.get_paged_materials()
        page_count = 0
        
        while response_data:
            page_count += 1
            results = response_data.get('results', [])
            self.stdout.write(f"      正在处理第 {page_count} 页数据 ({len(results)} 条)...")

            for mat in results:
                try:
                    with transaction.atomic():
                        # A. 确保分类本地存在
                        remote_cat = mat.get('category', {})
                        if not remote_cat:
                            continue
                            
                        local_cat, _ = CatalogCategory.objects.get_or_create(
                            remote_type_id=remote_cat['id'],
                            defaults={'name': remote_cat.get('name', '未分类')}
                        )

                        # B. 更新物料主表 (增加 is_published 支持)
                        product, _ = CatalogProduct.objects.update_or_create(
                            remote_material_id=mat['id'],
                            defaults={
                                'display_name': mat['grade_name'],
                                'category': local_cat,
                                'description': mat.get('description', ''),
                                'is_published': mat.get('is_published', False)
                            }
                        )

                        # C. 处理多对多关系镜像 (场景)
                        sce_objs = []
                        for s in mat.get('scenarios', []):
                            obj, _ = MirrorScenario.objects.get_or_create(
                                remote_id=s['id'], 
                                defaults={'name': s['name']}
                            )
                            sce_objs.append(obj)
                        product.scenarios.set(sce_objs)

                        # D. 处理多对多关系镜像 (特征)
                        char_objs = []
                        for c in mat.get('characteristics', []):
                            obj, _ = MirrorCharacteristic.objects.update_or_create(
                                remote_id=c['id'], 
                                defaults={'name': c['name']}
                            )
                            char_objs.append(obj)
                        product.characteristics.set(char_objs)

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"      [!] 跳过牌号 {mat.get('grade_name')}: {e}"))

            # 检查是否有下一页
            next_link = response_data.get('next')
            if next_link:
                # 再次调用 API 获取下一页，Service 内部会自动处理绝对 URL
                response_data = client._execute_request('GET', next_link)
            else:
                response_data = None
