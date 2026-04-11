import logging
from typing import Any, Dict
from .base import format_date

logger = logging.getLogger("app_mcp_server.serializers.material")

def serialize_material(material) -> Dict[str, Any]:
    """Serialize material base info, performance data and associated files."""
    try:
        # 适配重构后的模型方法
        grouped_props = material.get_grouped_properties() if hasattr(material, 'get_grouped_properties') else []
        
        # 转换为更易于 AI 处理的打平字典格式
        flattened_props = {}
        for group in grouped_props:
            for item in group.get('items', []):
                key = f"{item['name']} ({item['standard']})"
                val = f"{item['value']} {item['unit']}".strip()
                flattened_props[key] = val

        files = []
        if hasattr(material, 'additional_files'):
            for f in material.additional_files.all():
                files.append({
                    "name": f.name,
                    "type": f.get_file_type_display(),
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
            "properties_summary": flattened_props, # 打平的属性，方便 AI 提取
            "grouped_properties": grouped_props,   # 分组的详细属性
            "files": files,
            "created_at": format_date(material.created_at)
        }
    except Exception as e:
        logger.exception(f"Error serializing material: {e}")
        return {"error": f"Material serialization failed: {str(e)}"}
