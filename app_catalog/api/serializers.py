from collections import defaultdict

from django.urls import reverse
from rest_framework import serializers

from app_catalog.selectors import attachment_for
from app_material.models.material import (
    ApplicationScenario,
    MaterialCharacteristic,
    MaterialDataPoint,
    MaterialLibrary,
    MaterialProcessingCondition,
    MaterialType,
    TestConfig,
)


class MaterialTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaterialType
        fields = ('id', 'name', 'classification', 'description')


class ApplicationScenarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplicationScenario
        fields = ('id', 'name', 'requirements')


class MaterialCharacteristicSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaterialCharacteristic
        fields = ('id', 'name', 'description')


class TestConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestConfig
        fields = ('id', 'name', 'name_en', 'standard', 'condition', 'unit', 'data_type', 'order')


class MaterialDataPointSerializer(serializers.ModelSerializer):
    test_config = TestConfigSerializer(read_only=True)
    unit = serializers.CharField(source='test_config.unit', read_only=True)

    class Meta:
        model = MaterialDataPoint
        fields = (
            'id', 'test_config', 'value', 'value_text', 'unit', 'remark',
            'min_value', 'max_value', 'min_value_text', 'max_value_text',
        )


class MaterialLightSerializer(serializers.ModelSerializer):
    """材料列表。"""

    pk = serializers.IntegerField(source='id', read_only=True)
    display_name = serializers.CharField(source='grade_name', read_only=True)
    category = MaterialTypeSerializer(read_only=True)
    scenarios = ApplicationScenarioSerializer(many=True, read_only=True)
    characteristics = MaterialCharacteristicSerializer(many=True, read_only=True)
    published_at = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        model = MaterialLibrary
        fields = (
            'pk', 'display_name', 'grade_name', 'manufacturer', 'sap_material_code',
            'category', 'scenarios', 'characteristics',
            'flammability', 'material_color_name', 'pantone_code', 'rgb_value',
            'description', 'published_at',
        )


class MaterialProcessingConditionSerializer(serializers.ModelSerializer):
    """典型加工条件。不带内部主键和材料外键。"""

    class Meta:
        model = MaterialProcessingCondition
        fields = (
            'melt_temp_value', 'melt_temp_range',
            'barrel_rear_value', 'barrel_rear_range',
            'barrel_center_value', 'barrel_center_range',
            'barrel_front_value', 'barrel_front_range',
            'mold_temp_value', 'mold_temp_range',
            'temp_limit_value', 'temp_limit_range',
            'injection_speed_value', 'injection_speed_range',
            'pre_dry_value', 'pre_dry_range',
        )


class MaterialDetailSerializer(MaterialLightSerializer):
    """详情。物性和文档链接对持有服务端密钥的调用方始终返回。"""

    file_tds = serializers.SerializerMethodField()
    file_msds = serializers.SerializerMethodField()
    file_rohs = serializers.SerializerMethodField()
    grouped_properties = serializers.SerializerMethodField()
    processing_condition = serializers.SerializerMethodField()

    class Meta(MaterialLightSerializer.Meta):
        fields = MaterialLightSerializer.Meta.fields + (
            'file_tds', 'file_msds', 'file_rohs',
            'grouped_properties', 'processing_condition',
        )

    def get_processing_condition(self, obj):
        """没填加工条件时一对一访问会抛异常，详情应返回 null 而不是 500。"""
        try:
            condition = obj.processing_condition
        except MaterialProcessingCondition.DoesNotExist:
            return None
        return MaterialProcessingConditionSerializer(condition).data

    def _file_url(self, obj, file_type, category):
        if attachment_for(obj, category) is None:
            return None
        path = reverse(
            'app_catalog:material_download',
            kwargs={'pk': obj.pk, 'file_type': file_type},
        )
        request = self.context.get('request')
        if request is None:
            return path
        return request.build_absolute_uri(path)

    def get_file_tds(self, obj):
        return self._file_url(obj, 'tds', 'TDS')

    def get_file_msds(self, obj):
        return self._file_url(obj, 'msds', 'MSDS')

    def get_file_rohs(self, obj):
        return self._file_url(obj, 'rohs', 'RoHS')

    def get_grouped_properties(self, obj):
        grouped = defaultdict(list)
        points = list(obj.properties.all())
        for point in points:
            grouped[point.test_config.category.name].append(
                MaterialDataPointSerializer(point, context=self.context).data
            )
        result = []
        seen = []
        for point in points:
            cat_name = point.test_config.category.name
            if cat_name not in seen:
                result.append({'category_name': cat_name, 'items': grouped[cat_name]})
                seen.append(cat_name)
        return result
