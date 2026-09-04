from rest_framework import serializers

from app_material.models import MaterialLibrary

from .base import AttachmentBriefSerializer, NADateField, as_plain, attachments_for, json_number


class MaterialSerializer(serializers.ModelSerializer):
    manufacturer = serializers.CharField(default="Unknown", allow_blank=True, read_only=True)
    category = serializers.CharField(source="category.name", default="General", read_only=True)
    flammability = serializers.CharField(default="N/A", allow_blank=True, read_only=True)
    description = serializers.CharField(default="", allow_blank=True, read_only=True)
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
        data = super().to_representation(instance)
        data["manufacturer"] = data.get("manufacturer") or "Unknown"
        data["flammability"] = data.get("flammability") or "N/A"
        data["description"] = data.get("description") or ""
        return data

    def get_grouped_properties(self, obj):
        cached = getattr(obj, "_mcp_grouped_properties", None)
        if cached is None:
            if hasattr(obj, "get_grouped_properties"):
                cached = []
                for group in obj.get_grouped_properties():
                    items = []
                    for item in group.get("items", []):
                        raw = item.get("value")
                        items.append({
                            **item,
                            "value": raw if isinstance(raw, str) else json_number(raw),
                            "min_value": json_number(item.get("min_value")),
                            "max_value": json_number(item.get("max_value")),
                        })
                    cached.append({"category_name": group["category_name"], "items": items})
            else:
                cached = []
            obj._mcp_grouped_properties = cached
        return cached

    def get_properties_summary(self, obj):
        flattened = {}
        for group in self.get_grouped_properties(obj):
            for item in group.get("items", []):
                key = f"{item['name']} ({item['standard']})"
                val = f"{item['value']} {item['unit']}".strip()
                flattened[key] = val
        return flattened

    def get_files(self, obj):
        try:
            return AttachmentBriefSerializer(attachments_for(obj), many=True).data
        except Exception:
            return []


def serialize_material(material):
    """Serialize material base info, performance data and associated files."""
    return as_plain(MaterialSerializer(material).data)
