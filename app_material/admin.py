from django.contrib import admin

from app_material.models import MaterialType, ApplicationScenario, MetricCategory, TestConfig, MaterialDataPoint, MaterialFile, MaterialLibrary


@admin.register(MaterialType)
class MaterialTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'classification', 'description')
    search_fields = ('name', 'classification')
    list_filter = ('classification',)


@admin.register(ApplicationScenario)
class ApplicationScenarioAdmin(admin.ModelAdmin):
    list_display = ('name', 'requirements')
    search_fields = ('name',)


@admin.register(MetricCategory)
class MetricCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'order')
    ordering = ('order',)


@admin.register(TestConfig)
class TestConfigAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'standard', 'condition', 'unit', 'data_type', 'order')
    list_filter = ('category', 'data_type')
    search_fields = ('name', 'standard')
    ordering = ('category__order', 'order')


class MaterialDataPointInline(admin.TabularInline):
    model = MaterialDataPoint
    extra = 1
    autocomplete_fields = ['test_config']


class MaterialFileInline(admin.TabularInline):
    model = MaterialFile
    fields = ('file', 'name', 'file_type', 'version', 'description')
    extra = 1


@admin.register(MaterialLibrary)
class MaterialLibraryAdmin(admin.ModelAdmin):
    list_display = ('grade_name', 'manufacturer', 'category', 'flammability', 'created_at')
    search_fields = ('grade_name', 'manufacturer')
    list_filter = ('category', 'flammability', 'scenarios', 'created_at')
    filter_horizontal = ('scenarios',)
    inlines = [MaterialDataPointInline, MaterialFileInline]
    autocomplete_fields = ['category']


@admin.register(MaterialDataPoint)
class MaterialDataPointAdmin(admin.ModelAdmin):
    list_display = ('material', 'test_config', 'value', 'value_text')
    search_fields = ('material__grade_name', 'test_config__name')
    list_filter = ('test_config__category',)
    autocomplete_fields = ['material', 'test_config']


@admin.register(MaterialFile)
class MaterialFileAdmin(admin.ModelAdmin):
    list_display = ('name', 'material', 'file_type', 'version', 'uploaded_at')
    list_filter = ('file_type', 'uploaded_at')
    search_fields = ('material__grade_name', 'name', 'description')
    autocomplete_fields = ['material']
