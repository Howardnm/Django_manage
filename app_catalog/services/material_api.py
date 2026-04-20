import requests
import logging
from django.conf import settings
from functools import lru_cache

logger = logging.getLogger(__name__)

class MaterialApiClient:
    """
    电子手册 API 客户端服务：
    负责与主系统进行安全、可靠的远程数据通信。
    采用“低代码方法名”设计，视图层只需关心业务动作。
    """
    
    def __init__(self):
        # 1. 自动从系统配置中提取锚点
        self.base_url = getattr(settings, 'REMOTE_API_BASE_URL', 'http://127.0.0.1:8000/api/material/')
        self.timeout = getattr(settings, 'REMOTE_API_TIMEOUT', 15) # 稍微延长超时时间
        self.api_token = getattr(settings, 'INTERNAL_API_TOKEN', '')
        
        # 2. 注入标准安全请求头
        self.headers = {
            'Accept': 'application/json',
            'X-Internal-Client': 'Catalog-Portal-v2',
            'X-Internal-Api-Token': self.api_token
        }

    # --- 底层通信引擎 (模块化) ---

    def _execute_request(self, method, endpoint, **kwargs):
        """通用请求执行器：含异常处理与日志"""
        # 构建完整 URL (支持分页链接穿透)
        if endpoint.startswith('http'):
            url = endpoint
        else:
            url = f"{self.base_url}{endpoint.strip('/')}/"

        try:
            # 自动注入 headers，除非 kwargs 另有定义
            if 'headers' not in kwargs:
                kwargs['headers'] = self.headers
            
            # 设置默认超时
            kwargs.setdefault('timeout', self.timeout)

            response = requests.request(method, url, **kwargs)
            
            # 特殊处理流式响应
            if kwargs.get('stream'):
                return response
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Remote API [{method}] failed on {url}: {e}")
            return None

    # --- 业务语义化方法 (低代码调用点) ---

    def get_paged_materials(self, **filters):
        """获取物料列表 (支持分页和筛选参数)"""
        return self._execute_request('GET', 'materials/', params=filters)

    def fetch_material_details(self, material_id):
        """抓取单个物料的完整画像"""
        return self._execute_request('GET', f'materials/{material_id}/')

    @lru_cache(maxsize=1) # 静态维度数据，极高缓存价值
    def get_all_scenarios(self):
        """获取所有应用场景配置"""
        return self._execute_request('GET', 'scenarios/')

    def verify_credentials(self, username, password):
        """会员身份远程鉴权"""
        payload = {'username': username, 'password': password}
        # 此处不直接返回 None，而是返回包含错误信息的 dict，便于前端反馈
        response = self._execute_request('POST', 'auth/verify/', json=payload)
        return response or {'status': 'error', 'message': '与主系统通信失败，请检查网络'}

    def request_file_stream(self, material_id, file_type):
        """向主系统申请加密文件流"""
        endpoint = f"materials/{material_id}/download/{file_type.lower()}/"
        # 使用流式传输
        return self._execute_request('GET', endpoint, stream=True)

# 导出单例，全局复用长连接
client = MaterialApiClient()
