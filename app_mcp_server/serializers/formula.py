from rest_framework import serializers

from app_formula.models import FormulaBOM, FormulaTestResult, LabFormula

from .base import FloatDecimalField, NADateField, as_plain, blank_to_none


class FormulaBOMSerializer(serializers.ModelSerializer):
    raw_material = serializers.CharField(source="raw_material.name", read_only=True)
    model = serializers.CharField(source="raw_material.model_name", read_only=True)
    category = serializers.CharField(source="raw_material.category.name", read_only=True)
    percentage = FloatDecimalField()
    feeding_port = serializers.CharField(source="get_feeding_port_display", read_only=True)
    weighing_scale = serializers.CharField(source="get_weighing_scale_display", read_only=True)

    class Meta:
        model = FormulaBOM
        fields = (
            "raw_material", "model", "category", "percentage",
            "feeding_port", "weighing_scale", "is_pre_mix",
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["model"] = blank_to_none(data.get("model"))
        return data


class FormulaTestResultSerializer(serializers.ModelSerializer):
    item = serializers.CharField(source="test_config.name", read_only=True)
    unit = serializers.CharField(source="test_config.unit", read_only=True)
    standard = serializers.CharField(source="test_config.standard", read_only=True)
    value = serializers.SerializerMethodField()

    class Meta:
        model = FormulaTestResult
        fields = ("item", "value", "unit", "standard")

    def get_value(self, obj):
        """数值优先，否则用它记录的文本；两者都没有 → None。

        以前两者皆空时给 "N/A"，agent 分不清"没测"和"测出来就是 N/A"。
        """
        if obj.value is not None:
            return float(obj.value)
        return blank_to_none(obj.value_text)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["unit"] = blank_to_none(data.get("unit"))
        return data


class FormulaSerializer(serializers.ModelSerializer):
    material_type = serializers.CharField(source="material_type.name", read_only=True)
    # 成本不落库，实时算。调用方（MCP tool）应先预热 FormulaCostCalculator，
    # 否则每个配方会各自装载一次价格。
    cost_predicted = serializers.SerializerMethodField()
    bom = FormulaBOMSerializer(source="bom_lines", many=True, read_only=True)
    test_results = serializers.SerializerMethodField()
    description = serializers.CharField(read_only=True)
    created_at = NADateField()

    class Meta:
        model = LabFormula
        fields = (
            "code", "version", "name", "material_type", "cost_predicted",
            "bom", "test_results", "description", "created_at",
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["description"] = blank_to_none(data.get("description"))
        return data

    def get_cost_predicted(self, obj):
        """最新单价加权的 BOM 预测成本；任一行缺价 → None。"""
        value = obj.cost('latest')
        return float(value) if value is not None else None

    def get_test_results(self, obj):
        results = [
            res for res in obj.test_results.all()
            if res.production_order_id is None
        ]
        return FormulaTestResultSerializer(results, many=True).data


def serialize_formula(formula):
    """Full Formula Serialization including BOM and detailed Test Results."""
    return as_plain(FormulaSerializer(formula).data)
