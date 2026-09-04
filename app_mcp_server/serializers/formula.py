from rest_framework import serializers

from app_formula.models import FormulaBOM, FormulaTestResult, LabFormula

from .base import FloatDecimalField, NADateField, as_plain


class FormulaBOMSerializer(serializers.ModelSerializer):
    raw_material = serializers.CharField(source="raw_material.name", default="Unknown", read_only=True)
    model = serializers.CharField(source="raw_material.model_name", default="N/A", read_only=True)
    category = serializers.CharField(source="raw_material.category.name", default="N/A", read_only=True)
    percentage = FloatDecimalField()
    feeding_port = serializers.CharField(source="get_feeding_port_display", default="Main", read_only=True)
    weighing_scale = serializers.CharField(source="get_weighing_scale_display", default="A", read_only=True)

    class Meta:
        model = FormulaBOM
        fields = (
            "raw_material", "model", "category", "percentage",
            "feeding_port", "weighing_scale", "is_pre_mix",
        )


class FormulaTestResultSerializer(serializers.ModelSerializer):
    item = serializers.CharField(source="test_config.name", read_only=True)
    unit = serializers.CharField(source="test_config.unit", read_only=True)
    standard = serializers.CharField(source="test_config.standard", read_only=True)
    value = serializers.SerializerMethodField()

    class Meta:
        model = FormulaTestResult
        fields = ("item", "value", "unit", "standard")

    def get_value(self, obj):
        if obj.value is not None:
            return float(obj.value)
        return obj.value_text or "N/A"


class FormulaSerializer(serializers.ModelSerializer):
    material_type = serializers.CharField(source="material_type.name", default="N/A", read_only=True)
    cost_predicted = FloatDecimalField()
    bom = FormulaBOMSerializer(source="bom_lines", many=True, read_only=True)
    test_results = serializers.SerializerMethodField()
    description = serializers.CharField(default="", allow_blank=True, read_only=True)
    created_at = NADateField()

    class Meta:
        model = LabFormula
        fields = (
            "code", "version", "name", "material_type", "cost_predicted",
            "bom", "test_results", "description", "created_at",
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["description"] = data.get("description") or ""
        return data

    def get_test_results(self, obj):
        results = [
            res for res in obj.test_results.all()
            if res.production_order_id is None
        ]
        return FormulaTestResultSerializer(results, many=True).data


def serialize_formula(formula):
    """Full Formula Serialization including BOM and detailed Test Results."""
    return as_plain(FormulaSerializer(formula).data)
