import requests
import time
import uuid
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

# --- 从 settings.py 读取并验证配置 ---
DIFY_CONFIG = settings.DIFY_SYNC_CONFIG
DIFY_API_KEY = DIFY_CONFIG.get('API_KEY')
DIFY_API_BASE_URL = DIFY_CONFIG.get('API_BASE_URL')
USE_MOCK_API = DIFY_CONFIG.get('USE_MOCK_API', False)

if not USE_MOCK_API:
    if not DIFY_API_KEY or 'YOUR_DIFY_API_KEY' in DIFY_API_KEY:
        raise ImproperlyConfigured("请在 settings.py 的 DIFY_SYNC_CONFIG 中配置一个有效的 API Key。")
    if not DIFY_API_BASE_URL:
        raise ImproperlyConfigured("请在 settings.py 的 DIFY_SYNC_CONFIG 中配置 DIFY_API_BASE_URL。")

# --- 模拟 API 调用 ---
def mock_api_call(success_rate=0.95, is_create_dataset=False):
    time.sleep(0.5)
    if time.time() % 100 < success_rate * 100:
        if is_create_dataset:
            return True, {"id": f"dataset-mock-{uuid.uuid4().hex[:12]}", "name": "Mock Dataset"}
        return True, "模拟操作成功"
    else:
        return False, "模拟API请求失败"

# --- API 客户端函数 ---

def create_dataset_in_dify(api_key: str, name: str) -> (bool, dict):
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = f"{DIFY_API_BASE_URL}/datasets"
    payload = {"name": name}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return True, response.json()
    except requests.exceptions.RequestException as e:
        return False, str(e)


def create_document_in_dify(api_key: str, dataset_id: str, name: str, text: str, doc_id: int) -> (bool, str):
    """在 Dify 数据集中通过文本创建一个新文档"""
    if USE_MOCK_API:
        success, _ = mock_api_call()
        return (True, f"doc_{uuid.uuid4().hex}") if success else (False, "模拟创建文档失败")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = f"{DIFY_API_BASE_URL}/datasets/{dataset_id}/document/create-by-text"
    payload = {
        "name": name,
        "text": text,
        "indexing_technique": "high_quality",
        "process_rule": {"mode": "automatic"}
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return True, response.json().get("id")
    except requests.exceptions.RequestException as e:
        try:
            error_detail = e.response.json()
            return False, f"{e} | 详情: {error_detail}"
        except:
            return False, str(e)


def update_document_in_dify(api_key: str, dataset_id: str, document_id: str, name: str, text: str) -> (bool, str):
    """更新 Dify 数据集中的一个现有文档"""
    if USE_MOCK_API:
        return mock_api_call()

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    # 关键修复：使用您文档中指定的、用于更新的端点和 POST 方法
    url = f"{DIFY_API_BASE_URL}/datasets/{dataset_id}/documents/{document_id}/update-by-text"
    payload = {"name": name, "text": text}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return True, "更新成功"
    except requests.exceptions.RequestException as e:
        return False, str(e)


def delete_document_in_dify(api_key: str, dataset_id: str, document_id: str) -> (bool, str):
    """从 Dify 数据集中删除一个文档"""
    if USE_MOCK_API:
        return mock_api_call()

    # 关键修复：确保删除请求也使用了正确的认证头
    headers = {"Authorization": f"Bearer {api_key}"}
    url = f"{DIFY_API_BASE_URL}/datasets/{dataset_id}/documents/{document_id}"
    try:
        response = requests.delete(url, headers=headers, timeout=30)
        response.raise_for_status()
        return True, "删除成功"
    except requests.exceptions.RequestException as e:
        return False, str(e)
