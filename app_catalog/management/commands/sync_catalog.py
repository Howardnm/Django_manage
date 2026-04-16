import sys
import importlib
from django.core.management.base import BaseCommand
from ...models import CatalogCategory, CatalogProduct, MirrorScenario, MirrorCharacteristic
from ...services.material_api import client
from django.conf import settings
from django.db import transaction

class Command(BaseCommand):
    help = '从主系统 API 全量同步物料、场景、特性及分类数据，构建本地关系型镜像'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("\n--- 开始全量镜像同步任务 ---"))
        self._sync_dimensions()
        self._sync_categories()
        self._sync_products_with_relations()
        self.stdout.write(self.style.SUCCESS('\n✅ 镜像同步任务全部完成！'))

    def _sync_dimensions(self):
        self.stdout.write("正在同步应用场景...")
        sce_data = client.get_scenarios()
        scenarios = sce_data.get('results', []) if isinstance(sce_data, dict) else sce_data
        for s in scenarios:
            MirrorScenario.objects.update_or_create(remote_id=s['id'], defaults={'name': s['name']})

    def _sync_categories(self):
        self.stdout.write("正在同步材质系列分类...")
        data = client._get('types/')
        if data and 'results' in data:
            for mt in data['results']:
                CatalogCategory.objects.update_or_create(
                    remote_type_id=mt['id'], defaults={'name': mt['name'], 'is_active': True}
                )

    def _sync_products_with_relations(self):
        self.stdout.write("正在同步物料主档及关系链 (支持分页)...")
        # 初始路径
        current_path = 'materials/'
        page = 0
        
        while current_path:
            page += 1
            self.stdout.write(f"  - 正在同步第 {page} 页...")
            
            # 使用基础方法获取数据
            data = client._get(current_path)
            if not data or 'results' not in data: break

            for mat in data['results']:
                try:
                    with transaction.atomic():
                        local_cat, _ = CatalogCategory.objects.get_or_create(
                            remote_type_id=mat['category']['id'],
                            defaults={'name': mat['category']['name']}
                        )
                        # 核心修正：同步 is_published
                        product, _ = CatalogProduct.objects.update_or_create(
                            remote_material_id=mat['id'],
                            defaults={
                                'display_name': mat['grade_name'],
                                'category': local_cat,
                                'description': mat.get('description', ''),
                                'is_published': mat.get('is_published', False) # 基础同步时也记录发布状态
                            }
                        )
                        # 同步 M2M
                        sce_objs = [MirrorScenario.objects.get_or_create(remote_id=s['id'], defaults={'name': s['name']})[0] for s in mat.get('scenarios', [])]
                        product.scenarios.set(sce_objs)
                        char_objs = [MirrorCharacteristic.objects.update_or_create(remote_id=c['id'], defaults={'name': c['name']})[0] for c in mat.get('characteristics', [])]
                        product.characteristics.set(char_objs)
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"    [!] 跳过 {mat.get('grade_name')}: {e}"))

            # 关键修正：解析下一页路径，避免重复添加斜杠导致 404
            next_url = data.get('next')
            if next_url:
                # 提取 ?page=X 部分
                if '?' in next_url:
                    current_path = 'materials/?' + next_url.split('?')[1]
                else:
                    current_path = None
            else:
                current_path = None
