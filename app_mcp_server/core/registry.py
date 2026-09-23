"""MCP 工具注册期的可观测状态。

注册阶段的失败是静默的，agent 只会看到"工具不存在"：
- tools/ 或 mcp_tools.py import 失败 → 整块模块的工具不注册
- 重名工具 → SDK 丢弃后来者，只打一行 warning
- 返回注解读不出 schema → SDK 只 logger.info，工具注册成功但 output_schema 为 None

这里把上述事实记下来，由 tools/health.py 的 get_mcp_health 报给 agent。
只依赖 stdlib，避免与 core/server.py、apps.py 形成循环 import。
"""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app_mcp_server.serializers.types import ToolLoadFailure

logger = logging.getLogger(__name__)

# [{"module": str, "ok": bool, "error": str}]
LOAD_REPORT: list[dict] = []

# [{"name": str, "fn_module": str}]
DUPLICATES: list[dict] = []


def record_module(module_name: str, ok: bool, error: str = "") -> None:
    LOAD_REPORT.append({"module": module_name, "ok": ok, "error": error})


def record_duplicate(name: str, fn_module: str = "") -> None:
    DUPLICATES.append({"name": name, "fn_module": fn_module})


def load_failures() -> "list[ToolLoadFailure]":
    """只投影 ToolLoadFailure 声明的字段。

    多出来的键在直接调用工具时能溜出去、走 SDK 校验时又会被丢掉，
    两边形状不一致，所以在这里就裁干净。
    """
    return [
        {"module": entry["module"], "error": entry["error"]}
        for entry in LOAD_REPORT
        if not entry["ok"]
    ]


def duplicate_names() -> list[str]:
    return sorted({entry["name"] for entry in DUPLICATES})


def reset() -> None:
    """清空记录。`AppConfig.ready()` 开头会调一次，保证 ready() 可重复执行；
    测试也用它隔离用例之间的状态。"""
    LOAD_REPORT.clear()
    DUPLICATES.clear()
