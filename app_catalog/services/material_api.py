import requests
import logging
from django.conf import settings
from functools import lru_cache

logger = logging.getLogger(__name__)

class MaterialApiClient:
    def __init__(self):
        self.base_url = getattr(settings, 'REMOTE_API_BASE_URL', 'http://127.0.0.1:8000/api/material/')
        self.timeout = getattr(settings, 'REMOTE_API_TIMEOUT', 10)
        self.api_token = getattr(settings, 'INTERNAL_API_TOKEN', '')
        self.headers = {
            'Accept': 'application/json',
            'X-Internal-Client': 'Catalog-App',
            'X-Internal-Api-Token': self.api_token
        }

    def _post(self, endpoint, data=None):
        url = f"{self.base_url}{endpoint.strip('/')}/"
        try:
            return requests.post(url, json=data, headers=self.headers, timeout=self.timeout)
        except Exception as e:
            logger.error(f"API POST 失败 [{url}]: {str(e)}")
            return None

    def _get(self, endpoint, params=None):
        # 核心修正：如果 endpoint 已经包含 query 参数（如 materials/?page=2），不要补斜杠
        if endpoint.startswith('http'):
            url = endpoint
        elif '?' in endpoint:
            url = f"{self.base_url}{endpoint.lstrip('/')}"
        else:
            url = f"{self.base_url}{endpoint.strip('/')}/"

        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"API GET 失败 [{url}]: {str(e)}")
            return None

    def get_material_list(self, **kwargs): return self._get('materials/', params=kwargs)
    def get_material_detail(self, material_id): return self._get(f'materials/{material_id}/')
    @lru_cache(maxsize=128)
    def get_scenarios(self): return self._get('scenarios/')
    def verify_member_credentials(self, username, password):
        payload = {'username': username, 'password': password}
        response = self._post('auth/verify/', data=payload)
        if response and response.status_code == 200: return response.json()
        elif response:
            try: return response.json()
            except: return {'status': 'error', 'message': f'Server error {response.status_code}'}
        return {'status': 'error', 'message': 'Connection failed'}

client = MaterialApiClient()
