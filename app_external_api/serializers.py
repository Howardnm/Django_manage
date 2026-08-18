from collections import defaultdict

from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from app_attachment.models import Attachment
from app_material.models.material import (
    MaterialType, ApplicationScenario, TestConfig,
    MaterialLibrary, MaterialDataPoint, MaterialCharacteristic,
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
        fields = ('id', 'test_config', 'value', 'value_text', 'unit', 'remark')


class MaterialLightSerializer(serializers.ModelSerializer):
    """材料列表轻量序列化：供目录列表页渲染。"""
    pk = serializers.IntegerField(source='id', read_only=True)
    display_name = serializers.CharField(source='grade_name', read_only=True)
    category = MaterialTypeSerializer(read_only=True)
    scenarios = ApplicationScenarioSerializer(many=True, read_only=True)
    characteristics = MaterialCharacteristicSerializer(many=True, read_only=True)
    published_at = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        model = MaterialLibrary
        fields = (
            'pk', 'display_name', 'grade_name', 'manufacturer',
            'category', 'scenarios', 'characteristics',
            'description', 'published_at',
        )


class MaterialDetailSerializer(MaterialLightSerializer):
    """材料详情序列化：在列表字段基础上追加性能分组与文件下载链接。"""
    file_tds = serializers.SerializerMethodField()
    file_msds = serializers.SerializerMethodField()
    file_rohs = serializers.SerializerMethodField()
    grouped_properties = serializers.SerializerMethodField()

    class Meta(MaterialLightSerializer.Meta):
        fields = MaterialLightSerializer.Meta.fields + (
            'flammability', 'file_tds', 'file_msds', 'file_rohs', 'grouped_properties',
        )

    def _is_member(self):
        return bool(self.context.get('is_member'))

    def _attachment_url(self, obj, category):
        if not self._is_member():
            return None
        request = self.context.get('request')
        if not request:
            return None
        ct = ContentType.objects.get_for_model(obj)
        att = Attachment.objects.filter(
            content_type=ct, object_id=obj.pk,
            category=category, is_deleted=False,
        ).first()
        return request.build_absolute_uri(att.file.url) if att and att.file else None

    def get_file_tds(self, obj):
        return self._attachment_url(obj, 'TDS')

    def get_file_msds(self, obj):
        return self._attachment_url(obj, 'MSDS')

    def get_file_rohs(self, obj):
        return self._attachment_url(obj, 'RoHS')

    def get_grouped_properties(self, obj):
        if not self._is_member():
            return []
        grouped = defaultdict(list)
        points = obj.properties.select_related('test_config', 'test_config__category').order_by(
            'test_config__category__order', 'test_config__order'
        )
        for point in points:
            grouped[point.test_config.category.name].append(
                MaterialDataPointSerializer(point, context=self.context).data
            )
        result, seen = [], []
        for point in points:
            cat_name = point.test_config.category.name
            if cat_name not in seen:
                result.append({'category_name': cat_name, 'items': grouped[cat_name]})
                seen.append(cat_name)
        return result
