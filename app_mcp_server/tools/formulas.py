from django.db.models import Q
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError

from app_formula.mixins import FormulaAccessMixin
from app_formula.models import LabFormula
from app_mcp_server.access import gated_qs
from app_mcp_server.core.server import READ_ONLY, mcp
from app_mcp_server.serializers import serialize_formula
from app_mcp_server.serializers.types import FormulaOut

_PERM = "app_formula.view_labformula"


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
def search_formulas(ctx: Context, keyword: str = "") -> list[FormulaOut]:
    """Search for lab formulas by code or name. Returns matching formulas including BOM and test results."""
    qs = gated_qs(ctx, "search_formulas", _formula_qs(), FormulaAccessMixin, _PERM)
    if keyword:
        qs = qs.filter(Q(code__icontains=keyword) | Q(name__icontains=keyword))
    return [serialize_formula(f) for f in _prime_costs(list(qs))]


@mcp.tool(annotations=READ_ONLY)
def get_formula_detail(ctx: Context, code: str, version: int | None = None) -> FormulaOut:
    """Get a lab formula by experiment code. Same code may have multiple versions; omit version to get the latest."""
    qs = gated_qs(
        ctx, "get_formula_detail", _formula_qs().filter(code=code), FormulaAccessMixin, _PERM,
    )
    if version is not None:
        formula = qs.filter(version=version).first()
    else:
        formula = qs.order_by("-version").first()
    if not formula:
        raise ToolError("未找到或无权访问")
    return serialize_formula(formula)
