import requests
import logging
from django.conf import settings
from functools import lru_cache

logger = logging.getLogger(__name__)

class MaterialApiClient:
    """远程材料库 API 客户端，支持跨系统解耦调用"""
    
    def __init__(self):
        self.base_url = getattr(settings, 'REMOTE_API_BASE_URL', 'http://127.0.0.1:8000/api/material/')
        self.timeout = getattr(settings, 'REMOTE_API_TIMEOUT', 10)
        self.api_token = getattr(settings, 'INTERNAL_API_TOKEN', '') # 获取 Token
        
        self.headers = {
            'Accept': 'application/json',
            'X-Internal-Client': 'Catalog-App',
            'X-Internal-Api-Token': self.api_token # 携带安全 Token
        }

    def _get(self, endpoint, params=None):
        # 兼容完整 URL (分页) 和 相对路径 (Endpoint)
        if endpoint.startswith('http'):
            url = endpoint
        else:
            url = f"{self.base_url}{endpoint.strip('/')}/"

        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API 请求失败 [{url}]: {str(e)}")
            return None

    def get_material_list(self, **kwargs):
        """获取物料列表及基本信息"""
        return self._get('materials/', params=kwargs)

    def get_material_detail(self, material_id):
        """实时获取物料的完整详细数据，包含分组属性和文件 URL"""
        return self._get(f'materials/{material_id}/')

    @lru_cache(maxsize=128)
    def get_scenarios(self):
        """获取应用场景分类 (使用 LRU 缓存减少 API 调用)"""
        return self._get('scenarios/')

# 全局单例客户端
client = MaterialApiClient()
