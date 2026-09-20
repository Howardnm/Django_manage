"""MCP 工具侧身份与 L1~L5 过滤。

身份只读 ASGI 验签后写入的 request.state（mcp_user_id / mcp_jwt）。
不要读 ctx.headers：SDK 标明那是客户端输入。
同步工具跑在 anyio.to_thread 里，不要用 ContextVar。
"""
import logging
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from mcp.server.mcpserver.exceptions import ToolError

from app_mcp_server.auth import claims_json

logger = logging.getLogger(__name__)

_STDIO_DENIED = "此通道未启用身份认证"
_TOOL_DENIED = "无权调用该工具"
_ACCESS_DENIED = "无权访问"
_NOT_FOUND = "未找到或无权访问"


def _request_state(ctx):
    try:
        request_context = ctx.request_context
    except (AttributeError, ValueError):
        return None
    request = getattr(request_context, "request", None)
    if request is None:
        return None
    return getattr(request, "state", None)


def get_mcp_user(ctx):
    """从 request.state.mcp_user_id 再取一次 User（确认仍 is_active）。

    Stdio 或缺失 state → ToolError，不返回全表。
    """
    state = _request_state(ctx)
    user_id = getattr(state, "mcp_user_id", None) if state is not None else None
    if not user_id:
        logger.warning("MCP access denied: stdio or missing identity state")
        raise ToolError(_STDIO_DENIED)

    User = get_user_model()
    user = (
        User.objects.select_related("user_type", "department")
        .filter(pk=user_id, is_active=True)
        .first()
    )
    if not user:
        logger.warning("MCP access denied: user gone or inactive mcp_user_id=%s", user_id)
        raise ToolError(_ACCESS_DENIED)
    return user


def require_tool(ctx, tool_name: str):
    """校验 JWT `tool` claim 等于当前工具函数名。不认通配。"""
    user = get_mcp_user(ctx)
    state = _request_state(ctx)
    payload = getattr(state, "mcp_jwt", None) or {}
    actual = payload.get("tool")
    if actual != tool_name:
        logger.warning(
            "MCP access denied: tool claim mismatch expected=%s actual=%s user=%s claims=%s",
            tool_name, actual or "", user.username, claims_json(payload),
        )
        raise ToolError(_TOOL_DENIED)
    return user


def gated_qs(ctx, tool_name, qs, mixin_cls, perm):
    """L1/L2/L3 准入后走 mixin.get_queryset()（L4/L5 + 项目成员穿透）。"""
    user = require_tool(ctx, tool_name)
    mixin = mixin_cls()
    mixin.request = SimpleNamespace(user=user)
    mixin.permission_required = perm
    mixin.queryset = qs
    if not mixin.has_permission():
        state = _request_state(ctx)
        payload = getattr(state, "mcp_jwt", None) if state is not None else None
        logger.warning(
            "MCP access denied: L1/L3 user=%s mixin=%s perm=%s tool=%s claims=%s",
            user.username, mixin_cls.__name__, perm, tool_name, claims_json(payload),
        )
        raise ToolError(_ACCESS_DENIED)
    state = _request_state(ctx)
    payload = getattr(state, "mcp_jwt", None) if state is not None else None
    logger.info(
        "MCP tool call user=%s tool=%s perm=%s mixin=%s claims=%s",
        user.username, tool_name, perm, mixin_cls.__name__, claims_json(payload),
    )
    return mixin.get_queryset()


def gated_get(ctx, tool_name, qs, mixin_cls, perm, **filters):
    """隔离后再 filter。不存在与无权用同一句，避免泄露存在性。"""
    isolated = gated_qs(ctx, tool_name, qs, mixin_cls, perm)
    obj = isolated.filter(**filters).first()
    if not obj:
        state = _request_state(ctx)
        user_id = getattr(state, "mcp_user_id", None) if state is not None else None
        payload = getattr(state, "mcp_jwt", None) if state is not None else None
        logger.debug(
            "MCP gated_get empty tool=%s user_id=%s filters=%s claims=%s",
            tool_name, user_id, filters, claims_json(payload),
        )
        raise ToolError(_NOT_FOUND)
    return obj
