from django.db.models import Q
from mcp.server.mcpserver.context import Context

from app_mcp_server.access import gated_get, gated_qs, require_tool
from app_mcp_server.core.server import READ_ONLY, mcp
from app_mcp_server.responses import (
    ToolErrorOut,
    ToolFailure,
    safe_tool,
    search_ok,
    validate_limit,
)
from app_mcp_server.serializers import serialize_project, serialize_project_full
from app_mcp_server.serializers.types import ProjectDetailOut, ProjectSearchOut
from app_project.mixins import ProjectAccessMixin
from app_project.models import Project

_PERM = "app_project.view_project"

_EMPTY_HINT = (
    "已在你的可见范围内检索，没有匹配的项目。"
    "可尝试放宽 keyword，或去掉 is_terminated 过滤后重试。"
)


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
@safe_tool
def search_projects(
    ctx: Context, keyword: str = "", is_terminated: bool | None = None,
    limit: int | None = None,
) -> ProjectSearchOut | ToolErrorOut:
    """Search for projects by name, manager, customer, or OEM. Returns all matching projects (including terminated) unless is_terminated is set.

    Returns {"ok": true, "data": [...], "total": N, "returned": N, "has_more": bool}. Omit limit to get all matches; pass limit to cap the rows. A search with no matches still returns ok=true with total=0 and a hint explaining that.
    On failure returns {"ok": false, "error_code": ..., "message": ..., "hint": ...} instead of raising — read error_code and hint before telling the user nothing was found.
    """
    limit = validate_limit(limit)
    qs = gated_qs(ctx, "search_projects", _project_list_qs(), ProjectAccessMixin, _PERM)
    if keyword:
        qs = qs.filter(
            Q(name__icontains=keyword)
            | Q(manager__username__icontains=keyword)
            | Q(repository__customer__short_name__icontains=keyword)
            | Q(repository__oem__name__icontains=keyword)
        )
    if is_terminated is not None:
        qs = qs.filter(is_terminated=is_terminated)

    total = qs.count() if limit is not None else None
    if limit is not None:
        qs = qs[:limit]
    data = [serialize_project(p) for p in qs]
    return search_ok(
        data,
        empty_hint=_EMPTY_HINT,
        total=total,
        has_more=total > len(data) if total is not None else False,
    )


@mcp.tool(annotations=READ_ONLY)
@safe_tool
def get_project_details(
    ctx: Context, project_id: int | None = None, project_name: str = "",
) -> ProjectDetailOut | ToolErrorOut:
    """Get complete project info, including progress timeline, business archive (Customer/OEM), and associated files.

    On failure returns {"ok": false, "error_code": ..., "message": ..., "hint": ...} instead of raising. error_code tells you whether the project does not exist (NOT_FOUND) or exists but is outside your data scope (NO_PERMISSION).
    """
    require_tool(ctx, "get_project_details")
    if not project_id and not project_name:
        raise ToolFailure("INVALID_ARGUMENT", "必须提供 project_id 或 project_name 之一。")

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
