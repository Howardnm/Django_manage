"""服务端 API 密钥：生成、哈希校验。明文只在生成时返回一次。

与个人 MCP Key 的差别：expires_at 为空表示永不过期，且钥匙不绑定登录账号。
"""
import hashlib
import hmac
import secrets
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

SERVICE_API_KEY_PREFIX = "cat_"
LAST_USED_TOUCH = timedelta(hours=1)


def hash_service_api_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(key) -> str:
    """写入新的哈希与前缀，不保存。返回明文一次。"""
    token = SERVICE_API_KEY_PREFIX + secrets.token_urlsafe(32)
    key.key_hash = hash_service_api_key(token)
    key.key_prefix = token[:12]
    return token


def create_service_api_key(name: str, expires_at=None):
    """创建一把钥匙。expires_at 为空则永不过期。返回 (对象, 明文)。"""
    from app_user.models import ServiceApiKey

    key = ServiceApiKey(name=name, expires_at=expires_at, is_active=True)
    token = issue_token(key)
    key.save()
    return key, token


def rotate_service_api_key(key) -> str:
    """换新明文，旧密钥立即失效。"""
    token = issue_token(key)
    key.save(update_fields=["key_hash", "key_prefix"])
    return token


def authenticate_service_api_key(token: str):
    """有效则返回 ServiceApiKey，否则 None。不记录明文。"""
    from app_user.models import ServiceApiKey

    if not token or not token.startswith(SERVICE_API_KEY_PREFIX):
        return None
    digest = hash_service_api_key(token)
    key = ServiceApiKey.objects.filter(key_hash=digest).first()
    if key is None:
        return None
    if not hmac.compare_digest(key.key_hash or "", digest):
        return None
    if not key.is_active:
        return None
    if key.expires_at is not None and key.expires_at <= timezone.now():
        return None
    _touch_last_used(key)
    return key


def _touch_last_used(key):
    """成功鉴权后最多一小时写一次，避免 CRM 每次请求都更新。"""
    from app_user.models import ServiceApiKey

    now = timezone.now()
    cutoff = now - LAST_USED_TOUCH
    ServiceApiKey.objects.filter(pk=key.pk).filter(
        Q(last_used_at__isnull=True) | Q(last_used_at__lt=cutoff)
    ).update(last_used_at=now)
