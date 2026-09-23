import logging

from django.db.models import Q
from mcp.server.mcpserver.context import Context

from app_formula.mixins import FormulaAccessMixin
from app_formula.models import LabFormula
from app_material.mixins import MaterialAccessMixin
from app_material.models import MaterialLibrary
from app_mcp_server.access import gated_get, gated_qs
from app_mcp_server.core.server import READ_ONLY, mcp
from app_mcp_server.responses import (
    ToolErrorOut,
    ToolFailure,
    safe_tool,
    search_ok,
    validate_limit,
)
from app_mcp_server.serializers import serialize_formula, serialize_material
from app_mcp_server.serializers.types import (
    MaterialSearchOut,
    MaterialWithFormulasOut,
)

logger = logging.getLogger(__name__)

_MATERIAL_PERM = "app_material.view_materiallibrary"
_FORMULA_PERM = "app_formula.view_labformula"

_EMPTY_HINT = (
    "已在你的可见范围内检索，没有匹配的牌号。"
    "可尝试放宽 keyword，或去掉 category 过滤后重试。"
)

# 配方被挡住时的说明：不能让 agent 把"被权限挡住"读成"这个牌号没有配方"
_FORMULAS_DENIED_NOTE = (
    "该牌号存在关联配方，但你无权访问配方模块，已省略。"
    "这不代表它没有实验配方；如需查看，请申请配方模块的权限。"
)


def _formulas_hidden_note(total, hidden):
    return (
        f"该牌号有 {total} 条关联配方，其中 {hidden} 条不在你的可见范围内，已省略。"
        "这不代表它没有实验配方；如需查看，请申请配方模块的数据权限。"
    )


def _material_qs():
    return MaterialLibrary.objects.select_related("category").prefetch_related(
        "properties__test_config__category",
    )


@mcp.tool(annotations=READ_ONLY)
@safe_tool
def search_material_library(
    ctx: Context, keyword: str = "", category: str = "", limit: int | None = None,
) -> MaterialSearchOut | ToolErrorOut:
    """Search for finished materials in the library. Returns a list of grade names and basic info.

    Returns {"ok": true, "data": [...], "total": N, "returned": N, "has_more": bool}. Omit limit to get all matches; pass limit to cap the rows. A search with no matches still returns ok=true with total=0 and a hint explaining that.
    On failure returns {"ok": false, "error_code": ..., "message": ..., "hint": ...} instead of raising — read error_code and hint before telling the user nothing was found.
    """
    limit = validate_limit(limit)
    qs = gated_qs(
        ctx, "search_material_library", _material_qs(), MaterialAccessMixin, _MATERIAL_PERM,
    )
    if keyword:
        qs = qs.filter(Q(grade_name__icontains=keyword) | Q(manufacturer__icontains=keyword))
    if category:
        qs = qs.filter(category__name__icontains=category)

    total = qs.count() if limit is not None else None
    if limit is not None:
        qs = qs[:limit]
    data = [serialize_material(m) for m in qs]
    return search_ok(
        data,
        empty_hint=_EMPTY_HINT,
        total=total,
        has_more=total > len(data) if total is not None else False,
    )


@mcp.tool(annotations=READ_ONLY)
@safe_tool
def get_material_and_formulas(
    ctx: Context, grade_name: str,
) -> MaterialWithFormulasOut | ToolErrorOut:
    """Get detailed performance data and associated lab experiment formulas for a material grade.

    associated_formulas_history may be shorter than associated_formulas_total when some formulas are outside your data scope; associated_formulas_hidden carries the count and associated_formulas_note explains it. Absent fields on the material are null.
    On failure returns {"ok": false, "error_code": ..., "message": ..., "hint": ...} instead of raising.
    """
    material = gated_get(
        ctx, "get_material_and_formulas", _material_qs(),
        MaterialAccessMixin, _MATERIAL_PERM, grade_name=grade_name,
    )

    formula_qs = LabFormula.objects.filter(project__material=material).prefetch_related(
        "bom_lines__raw_material__category",
        "test_results__test_config",
    )

    data = serialize_material(material)
    try:
        isolated = gated_qs(
            ctx, "get_material_and_formulas", formula_qs, FormulaAccessMixin, _FORMULA_PERM,
        )
    except ToolFailure as exc:
        # 只降级"配方模块准入没过"这一种。身份 / 工具授权失败必须照常上抛——
        # 否则会变成 fail-open：把无权访问包装成一份看起来正常的材料数据。
        if exc.error_code != "NO_MODULE_ACCESS":
            raise
        # 材料数据本身有效，所以不整体降级成错误信封，
        # 而是保留数据 + 说清列表为空是权限所致。
        logger.info("MCP formula gate denied, material still returned grade=%s", grade_name)
        data["associated_formulas_history"] = []
        data["associated_formulas_note"] = _FORMULAS_DENIED_NOTE
        return data

    # L4/L5 隔离是静默过滤、不抛异常，所以要靠计数才能发现"被挡住了"
    formulas = list(isolated)
    data["associated_formulas_history"] = [serialize_formula(f) for f in formulas]

    total = formula_qs.count()
    hidden = total - len(formulas)
    if hidden:
        logger.info(
            "MCP formula rows hidden by isolation grade=%s hidden=%s visible=%s",
            grade_name, hidden, len(formulas),
        )
        data["associated_formulas_total"] = total
        data["associated_formulas_hidden"] = hidden
        data["associated_formulas_note"] = _formulas_hidden_note(total, hidden)
    return data
