from rest_framework import serializers
from ..models.material import (MaterialType, ApplicationScenario, MetricCategory, TestConfig, 
                                MaterialLibrary, MaterialDataPoint, MaterialFile, MaterialCharacteristic)
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

class MaterialFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaterialFile
        fields = '__all__'

class MaterialLibrarySerializer(serializers.ModelSerializer):
    category = MaterialTypeSerializer(read_only=True)
    scenarios = ApplicationScenarioSerializer(many=True, read_only=True)
    # 新增：特征属性序列化
    characteristics = MaterialCharacteristicSerializer(many=True, read_only=True)
    
    grouped_properties = serializers.SerializerMethodField()
    file_tds = serializers.SerializerMethodField()
    file_msds = serializers.SerializerMethodField()
    file_rohs = serializers.SerializerMethodField()

    class Meta:
        model = MaterialLibrary
        fields = (
            'id', 'grade_name', 'manufacturer', 'category', 'scenarios', 'characteristics',
            'flammability', 'description', 'file_tds', 'file_msds', 'file_rohs',
            'created_at', 'grouped_properties'
        )

    def _get_absolute_url(self, obj, field_name):
        file_field = getattr(obj, field_name)
        if file_field and hasattr(file_field, 'url'):
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(file_field.url)
            return file_field.url
        return None

    def get_file_tds(self, obj): return self._get_absolute_url(obj, 'file_tds')
    def get_file_msds(self, obj): return self._get_absolute_url(obj, 'file_msds')
    def get_file_rohs(self, obj): return self._get_absolute_url(obj, 'file_rohs')

    def get_grouped_properties(self, obj):
        grouped = defaultdict(list)
        points = obj.properties.all().order_by('test_config__category__order', 'test_config__order')
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
