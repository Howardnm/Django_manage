"""MCP 工具返回值信封：成功与失败两侧的统一契约。

失败**不**用逃逸异常表达。SDK 会把逃到协议层的异常压成
`CallToolResult(content=[TextContent("Error executing tool X: ...")], is_error=True)`
—— 没有 structuredContent；非 ToolError 的异常连原因都会丢（只剩通用一句）。
工具改为返回 `ToolErrorOut`，agent 能读到 error_code / message / hint 并据此决策。

本模块只依赖 stdlib + mcp，不 import serializers / models，保持 access 层轻量。
"""
import functools
import logging
from typing import Literal, TypedDict

from mcp.server.mcpserver.exceptions import ToolError

logger = logging.getLogger(__name__)


class ToolErrorOut(TypedDict):
    """所有工具失败时返回的信封。`ok` 恒为 False，是 agent 的判别字段。"""

    ok: Literal[False]
    error_code: str
    message: str
    hint: str


# 错误码 → (给 agent 看的中文说明, 给 agent 的操作建议)
_CODES: dict[str, tuple[str, str]] = {
    "NO_IDENTITY": (
        "此通道未启用身份认证",
        "请改用 HTTP /mcp 并携带 Authorization: Bearer <JWT 或个人 API Key>；Stdio 通道不提供身份。",
    ),
    "ACCOUNT_UNAVAILABLE": (
        "账号不可用",
        "当前账号已停用或不存在，请联系管理员确认账号状态。",
    ),
    "TOOL_NOT_ALLOWED": (
        "无权调用该工具",
        "当前 Token 未授权调用本工具（tool claim 不匹配）。请申请该工具的调用权限，或改用个人 API Key。",
    ),
    "NO_MODULE_ACCESS": (
        "无权访问该模块",
        "你的角色 / 用户等级 / 权限码不满足该模块的准入要求。请联系管理员开通该模块权限；不要绕道其他工具查询。",
    ),
    "NO_PERMISSION": (
        "无权访问该记录",
        "该记录存在，但不在你的可见范围内（部门或工作组隔离）。这是权限问题，不是参数问题；"
        "请不要用其他编号反复试探，改为请管理员调整你的数据权限。",
    ),
    "NOT_FOUND": (
        "未找到该记录",
        "该编号 / 名称在系统中不存在。请核对参数，或先用搜索类工具拿到准确的编号。",
    ),
    "INVALID_ARGUMENT": (
        "参数不合法",
        "请检查参数类型与必填项后重试。",
    ),
    "INTERNAL": (
        "服务内部错误",
        "请稍后重试；若持续失败，请联系管理员并提供调用时间与参数。",
    ),
}


class ToolFailure(ToolError):
    """带错误码的工具失败。

    继承 ToolError：万一逃逸（例如漏套 safe_tool），退化行为与改造前一致，
    仍是一条 MCP 工具错误，不会变成协议级异常。
    """

    def __init__(self, error_code: str, message: str = "", hint: str = ""):
        self.error_code = error_code
        self.message = message or _CODES.get(error_code, ("", ""))[0]
        self.hint = hint or _CODES.get(error_code, ("", ""))[1]
        super().__init__(self.message)


def error_out(error_code: str, message: str = "", hint: str = "") -> ToolErrorOut:
    """构造失败信封。message / hint 缺省时从错误码表补。"""
    default_message, default_hint = _CODES.get(error_code, ("", ""))
    return {
        "ok": False,
        "error_code": error_code,
        "message": message or default_message or error_code,
        "hint": hint or default_hint,
    }


def search_ok(data: list, empty_hint: str = "", total=None, has_more: bool = False) -> dict:
    """列表 / 搜索类工具的成功信封。

    total 是**匹配总数**（不只是返回条数），让 agent 能区分三种情况：
    检索到 0 条 / 被 limit 截断 / 拿全了。被权限挡住走 error_out，不在这个信封里。

    limit=None 时不做额外 COUNT，total 就等于 len(data)、has_more 恒为 False，
    与加 limit 之前的行为完全一致。
    """
    returned = len(data)
    result = {
        "ok": True,
        "data": data,
        "total": returned if total is None else total,
        "returned": returned,
        "has_more": has_more,
    }
    if not data and empty_hint:
        result["hint"] = empty_hint
    elif has_more:
        result["hint"] = more_hint(result["total"], returned)
    return result


def more_hint(total: int, returned: int) -> str:
    return (
        f"共匹配 {total} 条，本次只返回前 {returned} 条。"
        "请用更精确的 keyword 缩小范围，或调大 limit。"
    )


def validate_limit(limit):
    """limit 只允许 None（不限）或 >= 1 的整数。"""
    if limit is None:
        return None
    if limit < 1:
        raise ToolFailure(
            "INVALID_ARGUMENT",
            f"limit 必须是 >= 1 的整数（收到 {limit}）。不传 limit 表示不限制条数。",
        )
    return limit


def safe_tool(fn):
    """兜底装饰器：把工具里抛出的异常转成结构化信封。

    必须放在 @mcp.tool(...) **下面**（内层），这样注册的是本 wrapper；
    functools.wraps 保留 __wrapped__，SDK 仍能从原函数读到签名 / 注解 / docstring。
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ToolFailure as exc:
            logger.info(
                "MCP tool problem tool=%s code=%s message=%s",
                fn.__name__, exc.error_code, exc.message,
            )
            return error_out(exc.error_code, exc.message, exc.hint)
        except Exception:
            logger.exception("MCP tool crashed tool=%s", fn.__name__)
            return error_out("INTERNAL")

    return wrapper
