"""电子手册数据网关。

所有数据均实时从主系统对外接口（app_external_api）拉取，本地零落库。
采用实例服务 + 构造注入设计，失败抛 UpstreamError 由视图层转友好提示。
"""
import logging

import requests
from django.conf import settings
from django.utils import timezone

from .catalog_cache import CatalogCache

logger = logging.getLogger(__name__)


def _canonical(params):
    """将请求参数字典规范化为稳定的缓存键片段。"""
    return '&'.join(f'{k}={v}' for k, v in sorted(params.items()))


class UpstreamError(Exception):
    """主系统接口调用失败。"""


class CatalogGateway:
    def __init__(self, base_url=None, api_token=None, timeout=None):
        self.base_url = (base_url or settings.EXTERNAL_API_BASE_URL).rstrip('/') + '/'
        self.api_token = api_token if api_token is not None else settings.INTERNAL_API_TOKEN
        self.timeout = timeout if timeout is not None else settings.REMOTE_API_TIMEOUT
        self.headers = {
            'Accept': 'application/json',
            'X-Internal-Api-Token': self.api_token,
        }

    def _request(self, method, endpoint, **kwargs):
        url = endpoint if endpoint.startswith('http') else f"{self.base_url}{endpoint.strip('/')}/"
        headers = dict(self.headers)
        headers.update(kwargs.pop('headers', {}))
        kwargs.setdefault('timeout', self.timeout)
        try:
            response = requests.request(method, url, headers=headers, **kwargs)
        except requests.RequestException as e:
            logger.error('Catalog gateway %s %s failed: %s', method, url, e)
            raise UpstreamError('与主系统通信失败，请稍后再试') from e

        if kwargs.get('stream'):
            return response

        if response.status_code >= 400:
            logger.error('Catalog gateway %s %s returned %s', method, url, response.status_code)
            raise UpstreamError(f'主系统返回异常（{response.status_code}）')
        return response.json()

    # --- 业务方法 ---

    def nav_tree(self):
        """目录导航树（L1 内存缓存，版本由主系统驱动）。"""
        return CatalogCache.get('nav_tree', lambda: self._request('GET', 'catalog/nav-tree/'))

    def materials(self, **filters):
        """已发布材料分页列表（按查询参数分片缓存）。"""
        key = f'materials:{_canonical(filters)}'
        return CatalogCache.get(key, lambda: self._request('GET', 'materials/', params=filters))

    def cache_version(self):
        """主系统数据版本号（供本地缓存做一致性校验）。"""
        data = self._request('GET', 'cache-version/')
        return data.get('version', '')

    @staticmethod
    def _member_headers(member_token):
        """将会员令牌附加到请求头（透传给主系统做会员鉴权）。"""
        return {'X-Member-Token': str(member_token)} if member_token else {}

    def material(self, material_id, member_token=None):
        """单个材料完整画像（按会员/匿名分片缓存）。"""
        shard = 'member' if member_token else 'anon'
        key = f'material:{material_id}:{shard}'
        return CatalogCache.get(
            key,
            lambda: self._request(
                'GET', f'materials/{material_id}/',
                headers=self._member_headers(member_token),
            ),
        )

    def verify(self, email, password):
        """会员身份远程鉴权：返回原始 JSON（含 4xx 错误信息），仅网络异常抛错。"""
        url = f"{self.base_url}auth/verify/"
        try:
            response = requests.post(
                url,
                json={'email': email, 'password': password},
                headers=self.headers,
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            logger.error('Catalog gateway verify failed: %s', e)
            raise UpstreamError('与主系统通信失败，请稍后再试') from e
        try:
            return response.json()
        except ValueError:
            return {'status': 'error', 'message': '主系统返回异常，请稍后再试'}

    def file_stream(self, material_id, file_type, member_token=None):
        """申请文档文件流（原始响应，由视图层转发）。"""
        endpoint = f'materials/{material_id}/download/{file_type.lower()}/'
        return self._request(
            'GET', endpoint, stream=True,
            headers=self._member_headers(member_token),
        )

    def push_feedback(self, member_token, action, target_name):
        """行为回流：降级不阻断，失败仅记日志。"""
        if not member_token:
            return False
        payload = {'logs': [{
            'member_token': member_token,
            'action': action,
            'target_name': target_name,
            'timestamp': timezone.now().isoformat(),
        }]}
        try:
            self._request('POST', 'auth/feedback/', json=payload)
            return True
        except UpstreamError:
            logger.warning('Catalog feedback push degraded (non-blocking)', exc_info=True)
            return False


_gateway = None


def get_gateway():
    """获取网关单例（惰性初始化）。"""
    global _gateway
    if _gateway is None:
        _gateway = CatalogGateway()
    return _gateway
