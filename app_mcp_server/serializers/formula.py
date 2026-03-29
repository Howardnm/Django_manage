import logging
from typing import Any, Dict
from .base import format_date

logger = logging.getLogger("app_mcp_server.serializers.formula")

def serialize_formula(formula) -> Dict[str, Any]:
    """Full Formula Serialization including BOM and detailed Test Results."""
    try:
        bom_lines = []
        for line in formula.bom_lines.all():
            rm = line.raw_material
            bom_lines.append({
                "raw_material": rm.name if rm else "Unknown",
                "model": rm.model_name if rm else "N/A",
                "category": rm.category.name if rm and rm.category else "N/A",
                "percentage": float(line.percentage or 0),
                "feeding_port": line.get_feeding_port_display() if hasattr(line, 'get_feeding_port_display') else "Main",
                "weighing_scale": line.get_weighing_scale_display() if hasattr(line, 'get_weighing_scale_display') else "A",
                "is_pre_mix": line.is_pre_mix
            })

        test_results = []
        for res in formula.test_results.all():
            test_results.append({
                "item": res.test_config.name,
                "value": float(res.value) if res.value is not None else (res.value_text or "N/A"),
                "unit": res.test_config.unit,
                "standard": res.test_config.standard
            })

        return {
            "code": formula.code,
            "name": formula.name,
            "material_type": formula.material_type.name if formula.material_type else "N/A",
            "cost_predicted": float(formula.cost_predicted or 0),
            "bom": bom_lines,
            "test_results": test_results,
            "description": formula.description or "",
            "created_at": format_date(formula.created_at)
        }
    except Exception as e:
        logger.error(f"Error serializing formula: {e}")
        return {"error": "Formula serialization failed"}
