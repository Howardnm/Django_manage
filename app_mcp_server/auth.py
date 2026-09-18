"""MCP Streamable HTTP 的 RS256 JWT 鉴权。

身份只信验签后的 payload，再映射到本系统 User。不在这里校验 `tool`
（握手 initialize / tools/list 没有工具名）。
"""
import logging
from functools import lru_cache

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

_REQUIRED_CLAIMS = ["exp", "iat", "sub"]


class JwtAuthError(Exception):
    """验签或用户映射失败。对外一律 401，不区分原因。"""


def _normalize_pem(raw: str) -> str:
    """环境变量里的 PEM 常用字面 \\n，转成真正换行。"""
    return (raw or "").strip().replace("\\n", "\n")


def clear_public_key_cache():
    """测试用：清掉公钥进程缓存。"""
    _load_public_key.cache_clear()


@lru_cache(maxsize=1)
def _load_public_key(path: str, key: str) -> str:
    """PATH 优先于 KEY。读不到或为空则返回空串（调用方 fail-closed）。"""
    if path:
        try:
            with open(path, encoding="utf-8") as fh:
                return fh.read().strip()
        except OSError:
            logger.error("MCP JWT public key file unreadable: %s", path)
            return ""
    return _normalize_pem(key)


def get_public_key() -> str:
    """PATH 优先于 KEY。进程内按 (path, key) 缓存。"""
    path = getattr(settings, "MCP_JWT_PUBLIC_KEY_PATH", "") or ""
    key = getattr(settings, "MCP_JWT_PUBLIC_KEY", "") or ""
    return _load_public_key(path, key)


def _bearer_token(authorization: str | None) -> str | None:
    """RFC 6750：从 `Authorization: Bearer <token>` 取出 token。"""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or " " in token.strip():
        return None
    return token.strip() or None


def verify_jwt(token: str) -> dict:
    """RS256 验签。拒绝 alg=none / HS256，校验 exp/iat/sub。不校验 iss/aud。"""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as copilot_exc:
        raise JwtAuthError("invalid token") from copilot_exc

    if header.get("alg") != "RS256":
        raise JwtAuthError("invalid token")

    public_key = get_public_key()
    if not public_key:
        raise JwtAuthError("invalid token")

    try:
        return jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            leeway=int(getattr(settings, "MCP_JWT_LEEWAY", 30) or 0),
            options={
                "require": _REQUIRED_CLAIMS,
                "verify_aud": False,
            },
        )
    except jwt.PyJWTError as copilot_exc:
        raise JwtAuthError("invalid token") from copilot_exc


def resolve_user(payload: dict):
    """email（strip + iexact）优先；缺失再用 employeeNo / sub 查 username。

    不创建用户，不按 JWT departmentName 改部门。未映射或停用 → 失败。
    """
    User = get_user_model()
    qs = User.objects.select_related("user_type", "department").filter(is_active=True)

    email = payload.get("email")
    if isinstance(email, str) and email.strip():
        user = qs.filter(email__iexact=email.strip()).first()
        if user:
            return user
        raise JwtAuthError("invalid token")

    username = payload.get("employeeNo") or payload.get("sub")
    if isinstance(username, str) and username.strip():
        user = qs.filter(username=username.strip()).first()
        if user:
            return user
    raise JwtAuthError("invalid token")


def authenticate_http(request):
    """抽出 Bearer、验签、映射用户，并把身份挂到 request.state。

    Returns: User
    Raises: JwtAuthError
    """
    token = _bearer_token(request.headers.get("authorization"))
    if not token:
        raise JwtAuthError("invalid token")

    payload = verify_jwt(token)
    user = resolve_user(payload)
    request.state.mcp_jwt = payload
    request.state.mcp_user_id = user.pk
    return user
