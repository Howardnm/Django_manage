from django.db.models import Q
from mcp.server.mcpserver.context import Context

from app_formula.mixins import FormulaAccessMixin
from app_formula.models import LabFormula
from app_mcp_server.access import gated_qs, raise_empty
from app_mcp_server.core.server import READ_ONLY, mcp
from app_mcp_server.responses import (
    ToolErrorOut,
    safe_tool,
    search_ok,
    validate_limit,
)
from app_mcp_server.serializers import serialize_formula
from app_mcp_server.serializers.types import FormulaOut, FormulaSearchOut

_PERM = "app_formula.view_labformula"

_EMPTY_HINT = (
    "已在你的可见范围内检索，没有匹配的配方。"
    "可尝试用配方编号或名称的片段作为 keyword。"
)


def _formula_qs():
    return LabFormula.objects.select_related("material_type", "creator").prefetch_related(
        "bom_lines__raw_material__category",
        "test_results__test_config",
    )


def _prime_costs(formulas):
    """预热成本计算器 —— 成本不落库，序列化时实时算；
    不预热的话每个配方都会各自装载一次价格（N+1）。"""
    from app_formula.services import FormulaCostCalculator
    FormulaCostCalculator.for_formulas(formulas)
    return formulas


@mcp.tool(annotations=READ_ONLY)
@safe_tool
def search_formulas(
    ctx: Context, keyword: str = "", limit: int | None = None,
) -> FormulaSearchOut | ToolErrorOut:
    """Search for lab formulas by code or name. Returns matching formulas including BOM and test results.

    Returns {"ok": true, "data": [...], "total": N, "returned": N, "has_more": bool}. Omit limit to get all matches; pass limit to cap the rows. A search with no matches still returns ok=true with total=0 and a hint explaining that.
    On failure returns {"ok": false, "error_code": ..., "message": ..., "hint": ...} instead of raising — read error_code and hint before telling the user nothing was found.
    """
    limit = validate_limit(limit)
    qs = gated_qs(ctx, "search_formulas", _formula_qs(), FormulaAccessMixin, _PERM)
    if keyword:
        qs = qs.filter(Q(code__icontains=keyword) | Q(name__icontains=keyword))

    total = qs.count() if limit is not None else None
    if limit is not None:
        qs = qs[:limit]
    data = [serialize_formula(f) for f in _prime_costs(list(qs))]
    return search_ok(
        data,
        empty_hint=_EMPTY_HINT,
        total=total,
        has_more=total > len(data) if total is not None else False,
    )


@mcp.tool(annotations=READ_ONLY)
@safe_tool
def get_formula_detail(
    ctx: Context, code: str, version: int | None = None,
) -> FormulaOut | ToolErrorOut:
    """Get a lab formula by experiment code. Same code may have multiple versions; omit version to get the latest.

    On failure returns {"ok": false, "error_code": ..., "message": ..., "hint": ...} instead of raising. error_code tells you whether the code/version does not exist (NOT_FOUND) or exists but is outside your data scope (NO_PERMISSION).
    """
    base_qs = _formula_qs().filter(code=code)
    isolated = gated_qs(ctx, "get_formula_detail", base_qs, FormulaAccessMixin, _PERM)

    if version is not None:
        formula = isolated.filter(version=version).first()
        filters = {"code": code, "version": version}
    else:
        formula = isolated.order_by("-version").first()
        filters = {"code": code}
    if not formula:
        raise_empty(ctx, "get_formula_detail", base_qs, filters)
    return serialize_formula(formula)
