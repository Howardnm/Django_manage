import logging
from typing import Any, Dict
from .base import format_date

logger = logging.getLogger("app_mcp_server.serializers.project")

def serialize_project(project) -> Dict[str, Any]:
    """Basic project serialization for list view."""
    try:
        return {
            "id": project.id,
            "name": project.name,
            "manager": project.manager.username if project.manager else "N/A",
            "current_stage": project.get_current_stage_display(),
            "progress_percent": project.progress_percent,
            "is_terminated": project.is_terminated,
            "created_at": format_date(project.created_at)
        }
    except Exception as e:
        logger.error(f"Error serializing basic project: {e}")
        return {"error": "Project serialization failed"}

def serialize_project_full(project) -> Dict[str, Any]:
    """Ultimate Project Serializer including Archive, Timeline and Files."""
    try:
        data = serialize_project(project)
        
        repo = getattr(project, 'repository', None)
        if repo:
            data["business_info"] = {
                "customer": repo.customer.short_name if repo.customer else "N/A",
                "oem": repo.oem.name if repo.oem else "N/A",
                "salesperson": repo.salesperson.name if repo.salesperson else "N/A",
                "product_name": repo.product_name,
                "target_material": repo.material.grade_name if repo.material else "Not Selected",
                "target_cost": float(repo.target_cost or 0)
            }
        
        nodes = []
        for node in project.nodes.all().order_by('order'):
            nodes.append({
                "stage": node.get_stage_display(),
                "round": node.round,
                "status": node.get_status_display(),
                "remark": node.remark or "",
                "updated_at": node.updated_at.strftime("%Y-%m-%d %H:%M")
            })
        data["timeline"] = nodes

        files = []
        if repo:
            for f in repo.files.all():
                files.append({
                    "name": f.name,
                    "type": f.get_file_type_display() if hasattr(f, 'get_file_type_display') else "Other",
                    "node_context": f.node.get_stage_display() if f.node else "General",
                    "uploaded_at": format_date(f.uploaded_at)
                })
        data["associated_files"] = files

        return data
    except Exception as e:
        logger.error(f"Error serializing full project: {e}")
        return {"error": "Full project serialization failed"}
