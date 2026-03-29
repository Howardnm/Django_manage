from asgiref.sync import sync_to_async
from django.db.models import Q
from app_formula.models import LabFormula
from app_mcp_server.core.registry import mcp_site
from app_mcp_server.serializers import serialize_formula

@mcp_site.register(
    name="search_formulas",
    description="Search for lab formulas by code or name. Returns a list of matching formulas with basic info.",
    parameters={
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "Keyword to search in formula code or name"}
        }
    }
)
async def search_formulas(keyword: str = ""):
    @sync_to_async
    def query():
        qs = LabFormula.objects.select_related('material_type').all()
        if keyword:
            qs = qs.filter(Q(code__icontains=keyword) | Q(name__icontains=keyword))
        
        return [serialize_formula(f) for f in qs[:10]]
    
    return await query()

@mcp_site.register(
    name="get_formula_detail",
    description="Get detailed information about a specific formula including BOM composition and cost.",
    parameters={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "The exact experiment code of the formula (e.g., 'L20231001-01')"}
        },
        "required": ["code"]
    }
)
async def get_formula_detail(code: str):
    @sync_to_async
    def query():
        try:
            formula = LabFormula.objects.select_related('material_type', 'creator').get(code=code)
            return serialize_formula(formula)
        except LabFormula.DoesNotExist:
            return f"Error: Formula with code '{code}' not found."
            
    return await query()
