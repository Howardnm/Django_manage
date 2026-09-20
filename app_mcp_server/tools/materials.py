import logging

from django.db.models import Q
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError

from app_formula.mixins import FormulaAccessMixin
from app_formula.models import LabFormula
from app_material.mixins import MaterialAccessMixin
from app_material.models import MaterialLibrary
from app_mcp_server.access import gated_get, gated_qs
from app_mcp_server.core.server import READ_ONLY, mcp
from app_mcp_server.serializers import serialize_formula, serialize_material
from app_mcp_server.serializers.types import MaterialOut, MaterialWithFormulasOut

logger = logging.getLogger(__name__)

_MATERIAL_PERM = "app_material.view_materiallibrary"
_FORMULA_PERM = "app_formula.view_labformula"


def _material_qs():
    return MaterialLibrary.objects.select_related("category").prefetch_related(
        "properties__test_config__category",
    )


@mcp.tool(annotations=READ_ONLY)
def search_material_library(
    ctx: Context, keyword: str = "", category: str = "",
) -> list[MaterialOut]:
    """Search for finished materials in the library. Returns a list of grade names and basic info."""
    qs = gated_qs(
        ctx, "search_material_library", _material_qs(), MaterialAccessMixin, _MATERIAL_PERM,
    )
    if keyword:
        qs = qs.filter(Q(grade_name__icontains=keyword) | Q(manufacturer__icontains=keyword))
    if category:
        qs = qs.filter(category__name__icontains=category)
    return [serialize_material(m) for m in qs]


@mcp.tool(annotations=READ_ONLY)
def get_material_and_formulas(ctx: Context, grade_name: str) -> MaterialWithFormulasOut:
    """Get detailed performance data and associated lab experiment formulas for a material grade."""
    material = gated_get(
        ctx, "get_material_and_formulas", _material_qs(),
        MaterialAccessMixin, _MATERIAL_PERM, grade_name=grade_name,
    )

    formula_qs = LabFormula.objects.filter(project__material=material).prefetch_related(
        "bom_lines__raw_material__category",
        "test_results__test_config",
    )
    try:
        formula_qs = gated_qs(
            ctx, "get_material_and_formulas", formula_qs, FormulaAccessMixin, _FORMULA_PERM,
        )
        formulas = list(formula_qs)
    except ToolError:
        logger.debug(
            "MCP formula gate denied, returning empty list grade=%s",
            grade_name,
        )
        formulas = []

    data = serialize_material(material)
    data["associated_formulas_history"] = [serialize_formula(f) for f in formulas]
    return data
