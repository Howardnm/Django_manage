"""个人 MCP API Key：生成、哈希校验。明文只在生成时返回一次。"""
import hashlib
import hmac
import secrets
from datetime import timedelta

from django.utils import timezone

MCP_API_KEY_TTL_DAYS = 90
MCP_API_KEY_PREFIX = "mcp_"


class McpApiKeyDisabled(Exception):
    """用户未开通个人 MCP API Key。"""


def hash_mcp_api_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_mcp_api_key(user) -> str:
    """覆盖该用户现有 key，返回明文一次。未开通则拒绝。"""
    if not user.mcp_api_key_enabled:
        raise McpApiKeyDisabled("MCP API Key is disabled for this user")
    token = MCP_API_KEY_PREFIX + secrets.token_urlsafe(32)
    user.mcp_api_key_hash = hash_mcp_api_key(token)
    user.mcp_api_key_prefix = token[:12]
    user.mcp_api_key_expires_at = timezone.now() + timedelta(days=MCP_API_KEY_TTL_DAYS)
    user.save(update_fields=[
        "mcp_api_key_hash", "mcp_api_key_prefix", "mcp_api_key_expires_at",
    ])
    return token


def authenticate_mcp_api_key(token: str):
    """有效且未过期、已开通则返回 User，否则 None。不打明文。"""
    from django.contrib.auth import get_user_model

    if not token or not token.startswith(MCP_API_KEY_PREFIX):
        return None
    digest = hash_mcp_api_key(token)
    User = get_user_model()
    user = User.objects.filter(mcp_api_key_hash=digest).first()
    if user is None:
        return None
    if not hmac.compare_digest(user.mcp_api_key_hash or "", digest):
        return None
    if not user.mcp_api_key_enabled or not user.is_active:
        return None
    expires = user.mcp_api_key_expires_at
    if expires is None or expires <= timezone.now():
        return None
    return user
