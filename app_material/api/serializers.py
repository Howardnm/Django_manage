"""成品 BOM 发布入参。行不在这里，由服务按配方生成。"""

from decimal import Decimal

from rest_framework import serializers


class FinishedBomQuerySerializer(serializers.Serializer):
    sap_code = serializers.CharField(max_length=50)


class FinishedBomPublishSerializer(serializers.Serializer):
    formula_id = serializers.IntegerField(min_value=1)
    werks = serializers.CharField(max_length=4)
    stlan = serializers.CharField(max_length=1)
    stlal = serializers.CharField(max_length=2)
    bmeng = serializers.IntegerField(min_value=1)
    datuv = serializers.DateField(input_formats=["%Y-%m-%d"])
    stlst = serializers.CharField(required=False, allow_blank=True, default="1")
    stktx = serializers.CharField(required=False, allow_blank=True, default="")
    ztext = serializers.CharField(required=False, allow_blank=True, default="")
    ausch = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, default=Decimal("1"),
    )
    merge_color = serializers.BooleanField(required=False, default=False)
    packaging_code = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=50,
    )
    packaging_qty = serializers.DecimalField(
        max_digits=13, decimal_places=3, required=False, allow_null=True, default=None,
    )
    mode = serializers.ChoiceField(choices=["create", "update"])

    def validate_ausch(self, value):
        if value < 0:
            raise serializers.ValidationError("不能小于 0")
        return value


class FinishedBomPackagingQuerySerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True, default="")
    werks = serializers.CharField(required=False, allow_blank=True, default="", max_length=20)
