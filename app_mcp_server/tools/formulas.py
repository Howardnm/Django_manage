from django.db.models import Q
from mcp.server.mcpserver.exceptions import ToolError

from app_formula.models import LabFormula
from app_mcp_server.core.server import READ_ONLY, mcp
from app_mcp_server.serializers import serialize_formula
from app_mcp_server.serializers.types import FormulaOut


def _formula_qs():
    return LabFormula.objects.select_related("material_type", "creator").prefetch_related(
        "bom_lines__raw_material__category",
        "test_results__test_config",
    )


@mcp.tool(annotations=READ_ONLY)
def search_formulas(keyword: str = "") -> list[FormulaOut]:
    """Search for lab formulas by code or name. Returns matching formulas including BOM and test results."""
    qs = _formula_qs()
    if keyword:
        qs = qs.filter(Q(code__icontains=keyword) | Q(name__icontains=keyword))
    return [serialize_formula(f) for f in qs[:10]]


@mcp.tool(annotations=READ_ONLY)
def get_formula_detail(code: str, version: int | None = None) -> FormulaOut:
    """Get a lab formula by experiment code. Same code may have multiple versions; omit version to get the latest."""
    qs = _formula_qs().filter(code=code)
    if version is not None:
        formula = qs.filter(version=version).first()
        if not formula:
            raise ToolError(f"Formula {code!r} version {version} not found.")
    else:
        formula = qs.order_by("-version").first()
        if not formula:
            raise ToolError(f"Formula with code {code!r} not found.")
    return serialize_formula(formula)
