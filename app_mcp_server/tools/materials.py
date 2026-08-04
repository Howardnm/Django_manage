from asgiref.sync import sync_to_async
from django.db.models import Q
from app_material.models import MaterialLibrary
from app_formula.models import LabFormula
from app_mcp_server.core.registry import mcp_site
from app_mcp_server.serializers import serialize_material, serialize_formula

@mcp_site.register(
    name="search_material_library",
    description="Search for finished materials in the library. Returns a list of grade names and basic info.",
    parameters={
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "Keyword to search in grade name or manufacturer"},
            "category": {"type": "string", "description": "Filter by material category (PA66, ABS...)"}
        }
    }
)
async def search_material_library(keyword: str = "", category: str = ""):
    @sync_to_async(thread_sensitive=False)
    def query():
        qs = MaterialLibrary.objects.select_related('category').all()
        if keyword:
            qs = qs.filter(Q(grade_name__icontains=keyword) | Q(manufacturer__icontains=keyword))
        if category:
            qs = qs.filter(category__name__icontains=category)
        
        return [serialize_material(m) for m in qs[:20]]
    
    return await query()

@mcp_site.register(
    name="get_material_and_formulas",
    description="Get detailed performance data and associated lab experiment formulas for a material grade.",
    parameters={
        "type": "object",
        "properties": {
            "grade_name": {"type": "string", "description": "The exact grade name (e.g., 'PA66-GF30-V0')"}
        },
        "required": ["grade_name"]
    }
)
async def get_material_and_formulas(grade_name: str):
    @sync_to_async(thread_sensitive=False)
    def query():
        try:
            material = MaterialLibrary.objects.select_related('category').prefetch_related('properties').get(grade_name=grade_name)
            formulas = LabFormula.objects.filter(project__material=material).prefetch_related('bom_lines', 'test_results')
            
            data = serialize_material(material)
            data["associated_formulas_history"] = [serialize_formula(f) for f in formulas]
            
            return data
        except MaterialLibrary.DoesNotExist:
            return f"Error: Material '{grade_name}' not found."
            
    return await query()
