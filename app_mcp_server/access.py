"""MCP 工具侧身份与 L1~L5 过滤。

身份只读 ASGI 验签后写入的 request.state（mcp_user_id / mcp_jwt）。
不要读 ctx.headers：SDK 标明那是客户端输入。
同步工具跑在 anyio.to_thread 里，不要用 ContextVar。

失败一律抛 ToolFailure（带 error_code），由 safe_tool 转成结构化信封交给 agent，
不返回空值、不让异常逃到协议层。
"""
import json
import logging
from types import SimpleNamespace
from typing import NoReturn

from django.contrib.auth import get_user_model

from app_mcp_server.auth import claims_json
from app_mcp_server.responses import ToolFailure

logger = logging.getLogger(__name__)


def _request_state(ctx):
    try:
        request_context = ctx.request_context
    except (AttributeError, ValueError):
        return None
    request = getattr(request_context, "request", None)
    if request is None:
        return None
    return getattr(request, "state", None)


def _tool_arguments_json(ctx) -> str:
    """tools/call 的 arguments，给日志用。不是 Authorization / JWT。"""
    arguments = None
    try:
        request_context = ctx.request_context
    except (AttributeError, ValueError):
        request_context = None
    params = getattr(request_context, "params", None) if request_context is not None else None
    if isinstance(params, dict):
        arguments = params.get("arguments")
    elif params is not None:
        arguments = getattr(params, "arguments", None)
    if arguments is None:
        input_params = getattr(ctx, "_input_params", None)
        arguments = getattr(input_params, "arguments", None)
    if not isinstance(arguments, dict):
        return "{}"
    return json.dumps(arguments, ensure_ascii=False, default=str, sort_keys=True)


def get_mcp_user(ctx):
    """从 request.state.mcp_user_id 再取一次 User（确认仍 is_active）。

    Stdio 或缺失 state → NO_IDENTITY，不返回全表。
    """
    state = _request_state(ctx)
    user_id = getattr(state, "mcp_user_id", None) if state is not None else None
    if not user_id:
        logger.warning("MCP access denied: stdio or missing identity state")
        raise ToolFailure("NO_IDENTITY")

    User = get_user_model()
    user = (
        User.objects.select_related("user_type", "department")
        .filter(pk=user_id, is_active=True)
        .first()
    )
    if not user:
        logger.warning("MCP access denied: user gone or inactive mcp_user_id=%s", user_id)
        raise ToolFailure("ACCOUNT_UNAVAILABLE")
    return user


def require_tool(ctx, tool_name: str):
    """JWT 要求 `tool` claim 等于函数名；个人 API Key 跳过 claim，仍走 L1~L5。

    "是不是 API Key" 读 `request.state.mcp_auth_kind`（ASGI 鉴权时写入的带外信号），
    不读 JWT claim —— claim 由签发方决定，用它当鉴权分支等于把越权边界交给签发方。
    """
    user = get_mcp_user(ctx)
    state = _request_state(ctx)
    if getattr(state, "mcp_auth_kind", None) == "api_key":
        return user
    payload = getattr(state, "mcp_jwt", None) or {}
    actual = payload.get("tool")
    if actual != tool_name:
        logger.warning(
            "MCP access denied: tool claim mismatch expected=%s actual=%s user=%s args=%s claims=%s",
            tool_name, actual or "", user.username, _tool_arguments_json(ctx), claims_json(payload),
        )
        raise ToolFailure("TOOL_NOT_ALLOWED")
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
            "MCP access denied: L1/L3 user=%s mixin=%s perm=%s tool=%s args=%s claims=%s",
            user.username, mixin_cls.__name__, perm, tool_name,
            _tool_arguments_json(ctx), claims_json(payload),
        )
        raise ToolFailure("NO_MODULE_ACCESS")
    state = _request_state(ctx)
    payload = getattr(state, "mcp_jwt", None) if state is not None else None
    logger.info(
        "MCP tool call user=%s tool=%s perm=%s mixin=%s args=%s claims=%s",
        user.username, tool_name, perm, mixin_cls.__name__,
        _tool_arguments_json(ctx), claims_json(payload),
    )
    return mixin.get_queryset()


def raise_empty(ctx, tool_name, base_qs, filters) -> NoReturn:
    """隔离后为空：区分「记录存在但不可见」与「确实不存在」。

    base_qs 是**未**做 L4/L5 隔离的原始 queryset。按调用人要求如实告知无权，
    好过一句含糊的「未找到或无权访问」让 agent 换编号反复试探。
    注意：调用人层面的准入（L1~L3）在 gated_qs 里、任何查询之前就已经拦下，
    所以无模块权限的人走不到这里，探测不到任何记录。
    """
    state = _request_state(ctx)
    user_id = getattr(state, "mcp_user_id", None) if state is not None else None
    payload = getattr(state, "mcp_jwt", None) if state is not None else None
    exists = base_qs.filter(**filters).exists()
    logger.info(
        "MCP record %s tool=%s user_id=%s filters=%s args=%s claims=%s",
        "hidden" if exists else "absent",
        tool_name, user_id, filters, _tool_arguments_json(ctx), claims_json(payload),
    )
    if exists:
        raise ToolFailure("NO_PERMISSION")
    raise ToolFailure("NOT_FOUND")


def gated_get(ctx, tool_name, qs, mixin_cls, perm, **filters):
    """隔离后再 filter。查不到时区分「无权」与「不存在」。"""
    isolated = gated_qs(ctx, tool_name, qs, mixin_cls, perm)
    obj = isolated.filter(**filters).first()
    if not obj:
        raise_empty(ctx, tool_name, qs, filters)
    return obj
