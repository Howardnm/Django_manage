from django.db.models import Q
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError

from app_mcp_server.access import gated_get, gated_qs, require_tool
from app_mcp_server.core.server import READ_ONLY, mcp
from app_mcp_server.serializers import serialize_project, serialize_project_full
from app_mcp_server.serializers.types import ProjectDetailOut, ProjectListOut
from app_project.mixins import ProjectAccessMixin
from app_project.models import Project

_PERM = "app_project.view_project"


def _project_list_qs():
    return Project.objects.select_related(
        "manager", "repository", "repository__customer", "repository__oem",
    )


def _project_detail_qs():
    return Project.objects.select_related(
        "manager", "material",
        "repository", "repository__customer", "repository__oem", "repository__salesperson",
    ).prefetch_related("nodes")


@mcp.tool(annotations=READ_ONLY)
def search_projects(
    ctx: Context, keyword: str = "", is_terminated: bool = False,
) -> list[ProjectListOut]:
    """Search for projects by name, manager, customer, or OEM. Returns a list of matching projects with basic info."""
    qs = gated_qs(ctx, "search_projects", _project_list_qs(), ProjectAccessMixin, _PERM)
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
def get_project_details(
    ctx: Context, project_id: int | None = None, project_name: str = "",
) -> ProjectDetailOut:
    """Get complete project info, including progress timeline, business archive (Customer/OEM), and associated files."""
    require_tool(ctx, "get_project_details")
    if not project_id and not project_name:
        raise ToolError("Please provide project_id or project_name.")

    qs = _project_detail_qs()
    if project_id:
        project = gated_get(
            ctx, "get_project_details", qs, ProjectAccessMixin, _PERM, id=project_id,
        )
    else:
        project = gated_get(
            ctx, "get_project_details", qs, ProjectAccessMixin, _PERM,
            name__icontains=project_name,
        )
    return serialize_project_full(project)
