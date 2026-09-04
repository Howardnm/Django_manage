from django.db.models import Q
from mcp.server.mcpserver.exceptions import ToolError

from app_mcp_server.core.server import READ_ONLY, mcp
from app_mcp_server.serializers import serialize_project, serialize_project_full
from app_mcp_server.serializers.types import ProjectDetailOut, ProjectListOut
from app_project.models import Project


@mcp.tool(annotations=READ_ONLY)
def search_projects(keyword: str = "", is_terminated: bool = False) -> list[ProjectListOut]:
    """Search for projects by name, manager, customer, or OEM. Returns a list of matching projects with basic info."""
    qs = Project.objects.select_related(
        "manager", "repository", "repository__customer", "repository__oem",
    )
    if keyword:
        qs = qs.filter(
            Q(name__icontains=keyword)
            | Q(manager__username__icontains=keyword)
            | Q(repository__customer__short_name__icontains=keyword)
            | Q(repository__oem__name__icontains=keyword)
        )
    qs = qs.filter(is_terminated=is_terminated)
    return [serialize_project(p) for p in qs[:20]]


@mcp.tool(annotations=READ_ONLY)
def get_project_details(project_id: int | None = None, project_name: str = "") -> ProjectDetailOut:
    """Get complete project info, including progress timeline, business archive (Customer/OEM), and associated files."""
    if not project_id and not project_name:
        raise ToolError("Please provide project_id or project_name.")

    qs = Project.objects.select_related(
        "manager", "material",
        "repository", "repository__customer", "repository__oem", "repository__salesperson",
    ).prefetch_related("nodes")

    if project_id:
        project = qs.filter(id=project_id).first()
        if not project:
            raise ToolError(f"Project with ID {project_id} not found.")
    else:
        project = qs.filter(name__icontains=project_name).first()
        if not project:
            raise ToolError(f"Project with name {project_name!r} not found.")

    return serialize_project_full(project)
