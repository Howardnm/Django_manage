import logging

from rest_framework import serializers

from app_material.models import MaterialLibrary

from .base import (
    AttachmentBriefSerializer,
    NADateField,
    WarningMixin,
    as_plain,
    attachments_for,
    blank_to_none,
    json_number,
)
from .types import MaterialOut

logger = logging.getLogger(__name__)

# grouped_properties 里模型方法给的这些键是 blank=True 的字符列，空串 → null。
# 只在 serializer 这一层映射，不动 app_material 的模型方法（Web 端共用）。
_BLANKABLE_ITEM_KEYS = ("name_en", "unit", "condition", "min_value_text", "max_value_text")


class MaterialSerializer(WarningMixin, serializers.ModelSerializer):
    manufacturer = serializers.CharField(read_only=True)
    category = serializers.CharField(source="category.name", read_only=True)
    flammability = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    properties_summary = serializers.SerializerMethodField()
    grouped_properties = serializers.SerializerMethodField()
    files = serializers.SerializerMethodField()
    created_at = NADateField()

    class Meta:
        model = MaterialLibrary
        fields = (
            "id", "grade_name", "manufacturer", "category", "flammability",
            "description", "properties_summary", "grouped_properties",
            "files", "created_at",
        )

    def to_representation(self, instance):
        self.reset_warnings()
        data = super().to_representation(instance)
        for key in ("manufacturer", "flammability", "description"):
            data[key] = blank_to_none(data.get(key))
        return self.attach_warnings(data)

    def get_grouped_properties(self, obj):
        cached = getattr(obj, "_mcp_grouped_properties", None)
        if cached is None:
            if hasattr(obj, "get_grouped_properties"):
                cached = []
                for group in obj.get_grouped_properties():
                    items = []
                    for item in group.get("items", []):
                        raw = item.get("value")
                        normalised = {
                            **item,
                            # TEXT/SELECT 类的空字符串同样是"没有值"
                            "value": blank_to_none(raw) if isinstance(raw, str) else json_number(raw),
                            "min_value": json_number(item.get("min_value")),
                            "max_value": json_number(item.get("max_value")),
                        }
                        for key in _BLANKABLE_ITEM_KEYS:
                            normalised[key] = blank_to_none(normalised.get(key))
                        items.append(normalised)
                    cached.append({"category_name": group["category_name"], "items": items})
            else:
                cached = []
            obj._mcp_grouped_properties = cached
        return cached

    def get_properties_summary(self, obj):
        """"物性名 (标准)" → "值 单位"，无值时给 None。

        以前是 f"{value} {unit}".strip()，value 为 None 时会写出字符串 "None"，
        agent 会当成真实测量值。
        """
        flattened = {}
        for group in self.get_grouped_properties(obj):
            for item in group.get("items", []):
                key = f"{item['name']} ({item['standard']})"
                if key in flattened:
                    # 键只由"名称 (标准)"构成，不同分类下的同名同标准物性会撞车。
                    # 静默覆盖等于丢数据，所以出声；完整数据在 grouped_properties 里没丢。
                    self.add_warning(
                        f"物性摘要的键「{key}」重复出现，只保留了最后一条；"
                        "完整数据请读 grouped_properties。",
                    )
                value = item.get("value")
                if value is None:
                    # 没有值就是没有值。带上单位（"MPa"）会让 agent 当成真实测量值。
                    flattened[key] = None
                    continue
                unit = item.get("unit")
                flattened[key] = f"{value} {unit}".strip() if unit else str(value)
        return flattened

    def get_files(self, obj):
        """读取失败返回 None + warning，与"确实没有附件"（[]）区分开。"""
        try:
            return AttachmentBriefSerializer(attachments_for(obj), many=True).data
        except Exception as exc:
            logger.warning(
                "MCP attachment serialization failed material=%s: %s", obj.pk, exc,
                exc_info=True,
            )
            self.add_warning(
                f"附件列表读取失败（{type(exc).__name__}），files 为 null 不代表该牌号没有附件。",
            )
            return None


def serialize_material(material) -> MaterialOut:
    """Serialize material base info, performance data and associated files."""
    return as_plain(MaterialSerializer(material).data)
