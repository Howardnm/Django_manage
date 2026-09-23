"""只读的工具健康检查：把 agent 看不到的两类事实摊开。

1. **注册期**：哪个工具模块没加载起来、哪个工具名被丢弃、哪个工具没受
   `@safe_tool` 保护（这些以前只有服务端日志，agent 只看到"工具不存在"）。
2. **调用人的权限**：每个业务模块能不能进、卡在 L1/L2/L3 哪一层。
   agent 被权限挡住时能直接解释原因，而不是猜或反复试。

只报调用人**自己**的权限，不泄露任何业务记录。
"""
import logging

from mcp.server.mcpserver.context import Context

from app_mcp_server.access import get_mcp_user
from app_mcp_server.core import registry
from app_mcp_server.core.server import READ_ONLY, mcp
from app_mcp_server.responses import ToolErrorOut, safe_tool
from app_mcp_server.serializers.types import (
    CallerOut,
    HealthOut,
    ModuleAccessOut,
    ToolRegistryHealth,
)
from app_mcp_server.tools import formulas, materials, projects
from app_user.services.identity_service import IdentityService

logger = logging.getLogger(__name__)

# 模块表从工具模块导入 mixin 与权限码：两处各写一份必然漂移。
# （同包内引用下划线名，可接受；test_health 有断言守着一致性。）
_MODULES = (
    ("project", projects.ProjectAccessMixin, projects._PERM),
    ("formula", formulas.FormulaAccessMixin, formulas._PERM),
    ("material", materials.MaterialAccessMixin, materials._MATERIAL_PERM),
)


def _role_disabled(user) -> bool:
    """角色本身被停用。

    `UnifiedAccessMixin.has_permission()` 有这个防御检查（停用角色一律拒），
    但 `user_can()` **没有**——Admin 停用角色后，只要该角色 code 还在
    ModuleAccessConfig 的角色组里，`user_can()` 就会误判为有权，而真去调工具
    必然 NO_MODULE_ACCESS。所以这里必须自己先补上，否则健康检查会说反话。
    """
    return bool(user.user_type_id and not getattr(user.user_type, "is_active", True))


def _explain_denial(user, mixin_cls, perm) -> str:
    """归因到具体哪一层拒了。

    顺序对齐 UnifiedAccessMixin.has_permission 的 L1 → L2 → L3。
    只组合 app_user 的公开能力，不改核心权限代码。
    """
    if _role_disabled(user):
        return "L1 角色：你的用户角色已被停用。"
    if not mixin_cls.user_has_access(user):
        return (
            "L1 角色：你的用户类型不在本模块允许的角色组内；"
            "若本模块尚未配置角色组，则一律拒绝（fail-closed）。"
        )
    try:
        cfg = IdentityService.get_module_config(mixin_cls.module_code)
    except Exception as exc:
        logger.warning("MCP health: 读取模块配置失败 module=%s: %s", mixin_cls.module_code, exc)
        return "无法读取该模块的权限配置，按 fail-closed 视为无权。"
    if user.user_level < cfg["min_level"]:
        return (
            f"L2 用户等级：本模块要求等级 >= {cfg['min_level']}，"
            f"你的等级是 {user.user_level}。"
        )
    if not user.has_perm(perm):
        return f"L3 权限码：缺少 {perm}。"
    return "准入未通过，但未能归因到具体层级，请检查该模块的权限配置。"


def _access_note(user, mixin_cls) -> str:
    """准入通过后的数据可见范围提示。

    L4/L5 是数据隔离、不是准入：能进模块不等于能看到全部记录，不说清楚的话
    agent 会把"查不到某条"误判成参数问题。但也不能说死——隔离的真实生效条件在
    `UnifiedAccessMixin.apply_isolation()`：超管跳过、等级达到 l4/l5_bypass_min_level
    跳过、模型没有匹配 owner 字段时跳过并打 WARNING。前两种这里能精确判断；
    第三种是模块配置问题（服务端已有 WARNING），所以措辞只描述模块配置本身。
    """
    if user.is_superuser:
        return "超管：跳过 L1~L5 与数据隔离，可见全部数据。"

    cfg = IdentityService.get_module_config(mixin_cls.module_code)
    layers = []
    if cfg["enforce_dept_isolation"]:
        layers.append(("部门", cfg.get("l4_bypass_min_level")))
    if cfg["enforce_group_isolation"]:
        layers.append(("工作组", cfg.get("l5_bypass_min_level")))
    if not layers:
        return "准入通过；本模块未开启数据隔离。"

    effective = [
        name for name, threshold in layers
        if not (threshold and user.user_level >= threshold)
    ]
    if not effective:
        return "准入通过；你的等级已达到本模块隔离的跳过门槛，可见全部数据。"
    # 措辞要区分两类工具：记录级 get_* 会把不可见记录报成 NO_PERMISSION，
    # 而搜索类工具的 total 只统计可见记录，被隔离的既不计数也不报错。
    # 说成后者也报 NO_PERMISSION 会让 agent 对"只有 2 个牌号"这种结论过度自信。
    return (
        f"准入通过；本模块开启了{'、'.join(effective)}隔离。"
        "记录级工具（get_*）对不可见记录返回 NO_PERMISSION；"
        "搜索类工具只统计可见记录，被隔离的记录不会出现在 total 里。"
    )


def _module_access(user, mixin_cls, perm) -> ModuleAccessOut:
    if _role_disabled(user):
        return {
            "module": mixin_cls.module_code,
            "allowed": False,
            "reason": "L1 角色：你的用户角色已被停用。",
        }
    if mixin_cls.user_can(user, perm):
        return {
            "module": mixin_cls.module_code,
            "allowed": True,
            "reason": None,
            "note": _access_note(user, mixin_cls),
        }
    return {
        "module": mixin_cls.module_code,
        "allowed": False,
        "reason": _explain_denial(user, mixin_cls, perm),
    }


def _registry_health() -> ToolRegistryHealth:
    tools = mcp.registered_tools()
    guarded = 0
    unguarded = []
    for tool in tools:
        # 两种"没受保护"：漏套 @safe_tool，或返回注解读不出 schema
        # （SDK 在自动探测模式下只 logger.info，工具照常注册但无 structured output）
        if getattr(tool.fn, "__wrapped__", None) is not None and tool.output_schema is not None:
            guarded += 1
        else:
            unguarded.append(tool.name)
    return {
        "registered": len(tools),
        "guarded": guarded,
        "unguarded": sorted(unguarded),
        "load_failures": registry.load_failures(),
        "duplicate_names": registry.duplicate_names(),
    }


def _caller(user) -> CallerOut:
    return {
        "username": user.username,
        "role": user.user_type.name if user.user_type_id else None,
        "level": user.user_level,
        "department": user.department.name if user.department_id else None,
    }


@mcp.tool(annotations=READ_ONLY)
@safe_tool
def get_mcp_health(ctx: Context) -> HealthOut | ToolErrorOut:
    """Check MCP tool registration health and your own module access. Call this when another tool fails, when a tool is missing you expected to exist, or before telling the user they cannot see some data.

    Reports which tool modules failed to load, which tool names were dropped as duplicates, which tools are not protected, and for each business module whether you pass the L1 role / L2 level / L3 permission check — with the reason when you do not. It only reports your own permissions, never business records.
    On failure returns {"ok": false, "error_code": ..., "message": ..., "hint": ...} instead of raising.
    """
    user = get_mcp_user(ctx)
    return {
        "ok": True,
        "caller": _caller(user),
        "tools": _registry_health(),
        "module_access": [
            _module_access(user, mixin_cls, perm)
            for _module_code, mixin_cls, perm in _MODULES
        ],
    }
