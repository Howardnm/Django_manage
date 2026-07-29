import logging
from typing import Any, Dict
from .base import format_date

logger = logging.getLogger(__name__)

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
        try:
            from django.contrib.contenttypes.models import ContentType
            from app_attachment.models import Attachment
            ct = ContentType.objects.get_for_model(material)
            atts = Attachment.objects.filter(
                content_type=ct, object_id=material.pk, is_deleted=False
            ).order_by('-uploaded_at')
            for att in atts:
                files.append({
                    "name": att.display_name,
                    "type": att.category,
                    "version": att.version,
                    "uploaded_at": format_date(att.uploaded_at)
                })
        except Exception:
            pass

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
