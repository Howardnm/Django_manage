"""MCP Streamable HTTP 的 RS256 JWT 鉴权。

身份只信验签后的 payload，再映射到本系统 User。不在这里校验 `tool`
（握手 initialize / tools/list 没有工具名）。

失败原因只写日志，对外一律 JwtAuthError("invalid token")。
不记录原始 JWT / Authorization / PEM。
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


def _client_ip(request) -> str:
    client = getattr(request, "client", None)
    host = getattr(client, "host", None)
    return host or "-"


def verify_jwt(token: str) -> dict:
    """RS256 验签。拒绝 alg=none / HS256，校验 exp/iat/sub。不校验 iss/aud。"""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        logger.warning("MCP JWT verify failed: malformed jwt")
        raise JwtAuthError("invalid token") from exc

    alg = header.get("alg")
    if alg != "RS256":
        logger.warning("MCP JWT verify failed: alg=%s (expected RS256)", alg)
        raise JwtAuthError("invalid token")

    public_key = get_public_key()
    if not public_key:
        logger.warning("MCP JWT verify failed: empty public key")
        raise JwtAuthError("invalid token")

    try:
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            leeway=int(getattr(settings, "MCP_JWT_LEEWAY", 30) or 0),
            options={
                "require": _REQUIRED_CLAIMS,
                "verify_aud": False,
            },
        )
    except jwt.ExpiredSignatureError as exc:
        logger.warning("MCP JWT verify failed: expired")
        raise JwtAuthError("invalid token") from exc
    except (jwt.InvalidIssuedAtError, jwt.ImmatureSignatureError) as exc:
        logger.warning("MCP JWT verify failed: iat")
        raise JwtAuthError("invalid token") from exc
    except jwt.MissingRequiredClaimError as exc:
        logger.warning("MCP JWT verify failed: missing claim %s", getattr(exc, "claim", "?"))
        raise JwtAuthError("invalid token") from exc
    except jwt.InvalidSignatureError as exc:
        logger.warning("MCP JWT verify failed: invalid signature")
        raise JwtAuthError("invalid token") from exc
    except jwt.PyJWTError as exc:
        logger.warning("MCP JWT verify failed: %s", type(exc).__name__)
        raise JwtAuthError("invalid token") from exc

    logger.debug(
        "MCP JWT verified sub=%s email=%s employeeNo=%s tool=%s",
        payload.get("sub"),
        payload.get("email"),
        payload.get("employeeNo"),
        payload.get("tool"),
    )
    return payload


def resolve_user(payload: dict):
    """email（strip + iexact）优先；缺失再用 employeeNo / sub 查 username。

    不创建用户，不按 JWT departmentName 改部门。未映射或停用 → 失败。
    查询不预滤 is_active，以便日志区分 unknown / inactive。
    """
    User = get_user_model()
    qs = User.objects.select_related("user_type", "department")

    email = payload.get("email")
    if isinstance(email, str) and email.strip():
        email = email.strip()
        user = qs.filter(email__iexact=email).first()
        if user is None:
            logger.warning(
                "MCP JWT user mapping failed: unknown email=%s (no employeeNo/sub fallback)",
                email,
            )
            raise JwtAuthError("invalid token")
        if not user.is_active:
            logger.warning(
                "MCP JWT user mapping failed: inactive user pk=%s username=%s",
                user.pk, user.username,
            )
            raise JwtAuthError("invalid token")
        return user

    if isinstance(payload.get("employeeNo"), str) and payload["employeeNo"].strip():
        key, username = "employeeNo", payload["employeeNo"].strip()
    elif isinstance(payload.get("sub"), str) and payload["sub"].strip():
        key, username = "sub", payload["sub"].strip()
    else:
        logger.warning("MCP JWT user mapping failed: no email/employeeNo/sub")
        raise JwtAuthError("invalid token")

    user = qs.filter(username=username).first()
    if user is None:
        logger.warning("MCP JWT user mapping failed: unknown %s=%s", key, username)
        raise JwtAuthError("invalid token")
    if not user.is_active:
        logger.warning(
            "MCP JWT user mapping failed: inactive user pk=%s username=%s",
            user.pk, user.username,
        )
        raise JwtAuthError("invalid token")
    return user


def authenticate_http(request):
    """抽出 Bearer、验签、映射用户，并把身份挂到 request.state。

    Returns: User
    Raises: JwtAuthError
    """
    authorization = request.headers.get("authorization")
    token = _bearer_token(authorization)
    if not token:
        if authorization:
            logger.warning("MCP JWT auth failed: malformed authorization")
        else:
            logger.warning("MCP JWT auth failed: missing bearer")
        raise JwtAuthError("invalid token")

    payload = verify_jwt(token)
    user = resolve_user(payload)
    request.state.mcp_jwt = payload
    request.state.mcp_user_id = user.pk
    logger.info(
        "MCP JWT authenticated user_id=%s username=%s email=%s tool=%s client=%s",
        user.pk, user.username, user.email, payload.get("tool"), _client_ip(request),
    )
    return user
