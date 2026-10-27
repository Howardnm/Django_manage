"""BOM API 的入参。维护行保持字符串，日期不在这里改写。"""

from rest_framework import serializers


_MATERIAL_NAME_LIMIT = 40


class MaterialNameQuerySerializer(serializers.Serializer):
    """重复的 matnr 查询参数。去重后至少 1 个、最多 40 个。"""

    matnr = serializers.ListField(
        child=serializers.CharField(max_length=40, allow_blank=False),
        allow_empty=False,
    )

    def validate_matnr(self, value):
        codes = []
        seen = set()
        for code in value:
            code = code.strip()
            if not code or code in seen:
                continue
            seen.add(code)
            codes.append(code)
        if not codes:
            raise serializers.ValidationError("至少要有一个物料号")
        if len(codes) > _MATERIAL_NAME_LIMIT:
            raise serializers.ValidationError("一次最多查 40 个物料号")
        return codes


class BomListQuerySerializer(serializers.Serializer):
    matnr = serializers.CharField(max_length=40)
    werks = serializers.CharField(max_length=4)


class BomKeySerializer(serializers.Serializer):
    """URL 上的 BOM 主键：物料、工厂、用途、备选。"""

    matnr = serializers.CharField(max_length=40)
    werks = serializers.CharField(max_length=4)
    stlan = serializers.CharField(max_length=1)
    stlal = serializers.CharField(max_length=2)


class BomDetailQuerySerializer(serializers.Serializer):
    datuv = serializers.DateField(input_formats=["%Y-%m-%d"])
    emeng = serializers.DecimalField(
        max_digits=13, decimal_places=3, required=False,
    )


class BomLineSerializer(serializers.Serializer):
    """T_MAIN 的一行。抬头四个字段不在这里，由 URL 或外层写入。"""

    posnr = serializers.CharField()
    postp = serializers.CharField()
    idnrk = serializers.CharField()
    menge = serializers.CharField()
    meins = serializers.CharField()

    bmeng = serializers.CharField(required=False, allow_blank=True, default="")
    potx1 = serializers.CharField(required=False, allow_blank=True, default="")
    ewahr = serializers.CharField(required=False, allow_blank=True, default="")
    stktx = serializers.CharField(required=False, allow_blank=True, default="")
    ztext = serializers.CharField(required=False, allow_blank=True, default="")
    stlst = serializers.CharField(required=False, allow_blank=True, default="")
    ausch = serializers.CharField(required=False, allow_blank=True, default="")
    # CHAR 10，格式未在真实写入里核对过，不能用 DateField。
    datuv = serializers.CharField(required=False, allow_blank=True, max_length=10, default="")


class BomWriteSerializer(serializers.Serializer):
    matnr = serializers.CharField(max_length=40)
    werks = serializers.CharField(max_length=4)
    stlan = serializers.CharField(max_length=1)
    stlal = serializers.CharField(max_length=2)
    lines = BomLineSerializer(many=True)

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("至少一行")
        return value


class BomUpdateSerializer(serializers.Serializer):
    """修改的抬头只认 URL。body 里的物料、工厂、用途、备选忽略。"""

    lines = BomLineSerializer(many=True)

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("至少一行")
        return value
