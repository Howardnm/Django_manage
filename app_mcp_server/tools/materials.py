from django.db.models import Q
from mcp.server.mcpserver.exceptions import ToolError

from app_formula.models import LabFormula
from app_material.models import MaterialLibrary
from app_mcp_server.core.server import READ_ONLY, mcp
from app_mcp_server.serializers import serialize_formula, serialize_material
from app_mcp_server.serializers.types import MaterialOut, MaterialWithFormulasOut


@mcp.tool(annotations=READ_ONLY)
def search_material_library(keyword: str = "", category: str = "") -> list[MaterialOut]:
    """Search for finished materials in the library. Returns a list of grade names and basic info."""
    qs = MaterialLibrary.objects.select_related("category").prefetch_related(
        "properties__test_config__category",
    )
    if keyword:
        qs = qs.filter(Q(grade_name__icontains=keyword) | Q(manufacturer__icontains=keyword))
    if category:
        qs = qs.filter(category__name__icontains=category)
    return [serialize_material(m) for m in qs[:20]]


@mcp.tool(annotations=READ_ONLY)
def get_material_and_formulas(grade_name: str) -> MaterialWithFormulasOut:
    """Get detailed performance data and associated lab experiment formulas for a material grade."""
    material = MaterialLibrary.objects.select_related("category").prefetch_related(
        "properties__test_config__category",
    ).filter(grade_name=grade_name).first()
    if not material:
        raise ToolError(f"Material {grade_name!r} not found.")

    formulas = LabFormula.objects.filter(project__material=material).prefetch_related(
        "bom_lines__raw_material__category",
        "test_results__test_config",
    )
    data = serialize_material(material)
    data["associated_formulas_history"] = [serialize_formula(f) for f in formulas]
    return data
