import sys
import importlib
from django.core.management.base import BaseCommand
from ...models import CatalogCategory, CatalogProduct
from ...services.material_api import client # 更新导入路径
import requests
from django.conf import settings

# 强制重新加载模块，确保运行的是最新代码
if 'app_catalog.services.material_api' in sys.modules:
    importlib.reload(sys.modules['app_catalog.services.material_api'])

class Command(BaseCommand):
    help = '通过 API 从远程材料库同步基础数据（分类与产品索引）'

    def handle(self, *args, **options):
        print("\n[DEBUG sync_catalog] --- 开始 API 同步任务 ---")
        self.stdout.write(self.style.MIGRATE_HEADING("开始 API 同步任务..."))

        base_url = getattr(settings, 'REMOTE_API_BASE_URL', 'http://127.0.0.1:8000/api/material/')
        self.stdout.write(f"使用的远程 API 基地址: {base_url}")
        if not base_url.startswith('http'):
            self.stdout.write(self.style.ERROR("错误: REMOTE_API_BASE_URL 配置不正确。"))
            return
        
        # 检查 INTERNAL_API_TOKEN 是否配置
        api_token = getattr(settings, 'INTERNAL_API_TOKEN', None)
        if not api_token:
            self.stdout.write(self.style.ERROR("错误: settings.INTERNAL_API_TOKEN 未配置，API 请求可能失败。"))
            # return # 不直接返回，让它尝试请求，看是否是 AllowAny

        self.stdout.write("正在从 API 获取材料类型...")
        self._sync_categories()

        self.stdout.write("正在从 API 获取物料列表（支持分页）...")
        self._sync_products()

        self.stdout.write(self.style.SUCCESS('API 同步任务全部完成！'))

    def _sync_categories(self):
        """同步物料类型分类"""
        url_endpoint = 'types/'
        page_count = 0
        current_page_url = url_endpoint
        while current_page_url:
            page_count += 1
            self.stdout.write(f"  - 正在获取分类第 {page_count} 页...")
            data = client._get(current_page_url) # client._get 已经处理了 headers
            
            if data is None or 'results' not in data:
                self.stdout.write(self.style.ERROR(f"    分类 API 返回空数据或格式不正确，停止同步。"))
                break

            for mt in data['results']:
                category, created = CatalogCategory.objects.update_or_create(
                    remote_type_id=mt['id'],
                    defaults={
                        'name': mt['name'], 
                        'is_active': True
                    }
                )
                status = "创建" if created else "更新"
                self.stdout.write(self.style.SUCCESS(f'      [+] {status}分类: {category.name}'))
            
            current_page_url = data.get('next')

    def _sync_products(self):
        """同步物料产品索引"""
        url_endpoint = 'materials/'
        page_count = 0
        current_page_url = url_endpoint
        while current_page_url:
            page_count += 1
            self.stdout.write(f"  - 正在获取物料第 {page_count} 页...")
            data = client.get_material_list() # client.get_material_list 已经处理了 headers
            
            if data is None or 'results' not in data:
                self.stdout.write(self.style.ERROR(f"    物料 API 返回空数据或格式不正确，停止同步。"))
                break

            for mat in data['results']:
                try:
                    local_category = CatalogCategory.objects.get(remote_type_id=mat['category']['id'])
                    product, created = CatalogProduct.objects.update_or_create(
                        remote_material_id=mat['id'],
                        defaults={
                            'category': local_category,
                            'display_name': mat['grade_name'],
                        }
                    )
                    status = "同步新产品" if created else "更新产品索引"
                    self.stdout.write(self.style.SUCCESS(f'      [+] {status}: {product.display_name}'))
                except CatalogCategory.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f'      [!] 跳过 {mat["grade_name"]}: 本地未找到分类'))
            
            current_page_url = data.get('next')

    # _direct_get 方法不再需要，因为 client._get 已经兼容了完整 URL
    # def _direct_get(self, url):
    #     try:
    #         response = requests.get(url, timeout=10)
    #         response.raise_for_status()
    #         return response.json()
    #     except Exception as e:
    #         self.stdout.write(self.style.ERROR(f"    分页请求失败: {e}"))
    #         return None
