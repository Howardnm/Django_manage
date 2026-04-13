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
        
        # 1. 首先同步基础维度数据 (场景和特征)
        self._sync_dimensions()

        # 2. 同步材质分类
        self._sync_categories()

        # 3. 同步物料详情及多对多关系
        self._sync_products_with_relations()

        self.stdout.write(self.style.SUCCESS('\n✅ 镜像同步任务全部完成！系统已进入极速运行模式。'))

    def _sync_dimensions(self):
        """同步场景和特征属性"""
        self.stdout.write("正在同步应用场景...")
        sce_data = client.get_scenarios()
        scenarios = sce_data.get('results', []) if isinstance(sce_data, dict) else sce_data
        for s in scenarios:
            obj, created = MirrorScenario.objects.update_or_create(
                remote_id=s['id'], defaults={'name': s['name']}
            )
            self.stdout.write(f"  [Scenario] {'创建' if created else '更新'}: {s['name']}")

        self.stdout.write("正在从物料列表提取并同步特征属性...")
        # 特征属性通常没有独立 API，我们从物料列表中动态提取
        # 这里为了简化，我们会在同步物料时顺便处理，此处仅作提示

    def _sync_categories(self):
        """同步材质分类"""
        self.stdout.write("正在同步材质系列分类...")
        data = client._get('types/')
        if data and 'results' in data:
            for mt in data['results']:
                CatalogCategory.objects.update_or_create(
                    remote_type_id=mt['id'],
                    defaults={'name': mt['name'], 'is_active': True}
                )
                self.stdout.write(f"  [Category] 同步: {mt['name']}")

    def _sync_products_with_relations(self):
        """同步物料及其复杂的镜像关系"""
        self.stdout.write("正在同步物料主档及关系链 (支持分页)...")
        current_page_url = 'materials/'
        page = 0

        while current_page_url:
            page += 1
            data = client._get(current_page_url)
            if not data or 'results' not in data: break

            for mat in data['results']:
                try:
                    with transaction.atomic():
                        # A. 确保分类存在
                        local_cat, _ = CatalogCategory.objects.get_or_create(
                            remote_type_id=mat['category']['id'],
                            defaults={'name': mat['category']['name']}
                        )

                        # B. 更新物料主档 (包含描述镜像)
                        product, _ = CatalogProduct.objects.update_or_create(
                            remote_material_id=mat['id'],
                            defaults={
                                'display_name': mat['grade_name'],
                                'category': local_cat,
                                'description': mat.get('description', ''),
                            }
                        )

                        # C. 建立场景关联
                        sce_objs = []
                        for s in mat.get('scenarios', []):
                            s_obj, _ = MirrorScenario.objects.get_or_create(
                                remote_id=s['id'], defaults={'name': s['name']}
                            )
                            sce_objs.append(s_obj)
                        product.scenarios.set(sce_objs)

                        # D. 建立特征关联 (顺便同步特征主表)
                        char_objs = []
                        for c in mat.get('characteristics', []):
                            c_obj, _ = MirrorCharacteristic.objects.update_or_create(
                                remote_id=c['id'], defaults={'name': c['name']}
                            )
                            char_objs.append(c_obj)
                        product.characteristics.set(char_objs)

                    self.stdout.write(self.style.SUCCESS(f"  [Product] 已镜像: {mat['grade_name']}"))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  [!] 同步失败 {mat['grade_name']}: {str(e)}"))

            current_page_url = data.get('next')
            if current_page_url and 'http' in current_page_url:
                # 提取相对路径
                current_page_url = 'materials/' + current_page_url.split('materials/')[1]
