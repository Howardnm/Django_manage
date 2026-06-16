from rest_framework import serializers
from app_material.models.material import (MaterialType, ApplicationScenario, MetricCategory, TestConfig,
                                MaterialLibrary, MaterialDataPoint, MaterialCharacteristic)
from django.contrib.contenttypes.models import ContentType
from app_attachment.models import Attachment
from collections import defaultdict

class MaterialCharacteristicSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaterialCharacteristic
        fields = '__all__'

class MaterialTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaterialType
        fields = '__all__'

class ApplicationScenarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplicationScenario
        fields = '__all__'

class MetricCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MetricCategory
        fields = '__all__'

class TestConfigSerializer(serializers.ModelSerializer):
    category = MetricCategorySerializer(read_only=True)
    class Meta:
        model = TestConfig
        fields = '__all__'

class MaterialDataPointSerializer(serializers.ModelSerializer):
    test_config = TestConfigSerializer(read_only=True)
    class Meta:
        model = MaterialDataPoint
        fields = ('id', 'test_config', 'value', 'value_text', 'remark')


# ==========================================
# 新附件序列化器（替代旧 MaterialFileSerializer）
# ==========================================
class AttachmentFileSerializer(serializers.ModelSerializer):
    material_id = serializers.IntegerField(source='object_id')
    file_type = serializers.CharField(source='category')
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = [
            'id', 'material_id', 'display_name', 'file_type',
            'file_url', 'version', 'description', 'uploaded_at',
            'file_size',
        ]

    def get_file_url(self, obj):
        request = self.context.get('request')
        if request and obj.file:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url if obj.file else None


class MaterialLibrarySerializer(serializers.ModelSerializer):
    category = MaterialTypeSerializer(read_only=True)
    scenarios = ApplicationScenarioSerializer(many=True, read_only=True)
    characteristics = MaterialCharacteristicSerializer(many=True, read_only=True)

    grouped_properties = serializers.SerializerMethodField()
    file_tds = serializers.SerializerMethodField()
    file_msds = serializers.SerializerMethodField()
    file_rohs = serializers.SerializerMethodField()

    class Meta:
        model = MaterialLibrary
        fields = (
            'id', 'grade_name', 'manufacturer', 'category', 'scenarios', 'characteristics',
            'is_published',
            'flammability', 'description', 'file_tds', 'file_msds', 'file_rohs',
            'created_at', 'grouped_properties'
        )

    def _get_attachment_url(self, obj, category):
        """从 Attachment 表获取指定分类文件的下载 URL"""
        request = self.context.get('request')
        if not request:
            return None

        ct = ContentType.objects.get_for_model(obj)
        att = Attachment.objects.filter(
            content_type=ct, object_id=obj.pk,
            category=category, is_deleted=False,
        ).first()
        if att and att.file:
            return request.build_absolute_uri(att.file.url)
        return None

    def get_file_tds(self, obj):
        return self._get_attachment_url(obj, 'TDS')

    def get_file_msds(self, obj):
        return self._get_attachment_url(obj, 'MSDS')

    def get_file_rohs(self, obj):
        return self._get_attachment_url(obj, 'RoHS')

    def get_grouped_properties(self, obj):
        grouped = defaultdict(list)
        points = obj.properties.select_related('test_config', 'test_config__category').order_by(
            'test_config__category__order', 'test_config__order'
        )
        for point in points:
            cat_name = point.test_config.category.name
            grouped[cat_name].append(MaterialDataPointSerializer(point, context=self.context).data)

        result = []
        seen_cats = []
        for point in points:
            cat_name = point.test_config.category.name
            if cat_name not in seen_cats:
                result.append({'category_name': cat_name, 'items': grouped[cat_name]})
                seen_cats.append(cat_name)
        return result
