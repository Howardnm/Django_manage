import logging
from typing import Any, Dict
from .base import format_date

logger = logging.getLogger("app_mcp_server.serializers.material")

def serialize_material(material) -> Dict[str, Any]:
    """Serialize material base info, performance data and associated files."""
    try:
        properties = material.get_properties_dict() if hasattr(material, 'get_properties_dict') else {}
        files = []
        if hasattr(material, 'additional_files'):
            for f in material.additional_files.all():
                files.append({
                    "name": f.name,
                    "type": f.get_file_type_display() if hasattr(f, 'get_file_type_display') else "File",
                    "version": f.version,
                    "uploaded_at": format_date(f.uploaded_at)
                })

        return {
            "id": material.id,
            "grade_name": material.grade_name,
            "manufacturer": material.manufacturer or "Unknown",
            "category": material.category.name if material.category else "General",
            "flammability": material.flammability or "N/A",
            "description": material.description or "",
            "properties": properties,
            "files": files,
            "created_at": format_date(material.created_at)
        }
    except Exception as e:
        logger.error(f"Error serializing material: {e}")
        return {"error": "Material serialization failed"}
