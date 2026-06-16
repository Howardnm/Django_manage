from asgiref.sync import sync_to_async
from django.db.models import Q
from app_project.models import Project
from app_mcp_server.core.registry import mcp_site
from app_mcp_server.serializers import serialize_project, serialize_project_full

@mcp_site.register(
    name="search_projects",
    description="Search for projects by name, manager, customer, or OEM. Returns a list of matching projects with basic info.",
    parameters={
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "Keyword to search in project name, manager, or customer name"},
            "is_terminated": {"type": "boolean", "description": "Whether the project has been terminated"}
        }
    }
)
async def search_projects(keyword: str = "", is_terminated: bool = False):
    @sync_to_async
    def query():
        qs = Project.objects.select_related('manager', 'repository', 'repository__customer', 'repository__oem').all()
        if keyword:
            qs = qs.filter(
                Q(name__icontains=keyword) | 
                Q(manager__username__icontains=keyword) |
                Q(repository__customer__short_name__icontains=keyword) |
                Q(repository__oem__name__icontains=keyword)
            )
        
        if is_terminated:
            qs = qs.filter(is_terminated=True)
        else:
            qs = qs.filter(is_terminated=False)
            
        return [serialize_project(p) for p in qs[:20]]
    
    return await query()

@mcp_site.register(
    name="get_project_details",
    description="Get complete project info, including progress timeline, business archive (Customer/OEM), and associated files.",
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "integer", "description": "The unique ID of the project"},
            "project_name": {"type": "string", "description": "Alternatively, search by exact project name"}
        }
    }
)
async def get_project_details(project_id: int = None, project_name: str = ""):
    @sync_to_async
    def query():
        try:
            qs = Project.objects.select_related('manager', 'repository', 'repository__customer', 'repository__oem', 'repository__salesperson') \
                                .prefetch_related('nodes')
            
            if project_id:
                project = qs.get(id=project_id)
            elif project_name:
                project = qs.filter(name__icontains=project_name).first()
                if not project:
                    return f"Error: Project with name '{project_name}' not found."
            else:
                return "Error: Please provide project_id or project_name."
                
            return serialize_project_full(project)
        except Project.DoesNotExist:
            return f"Error: Project with ID {project_id} not found."

    return await query()
