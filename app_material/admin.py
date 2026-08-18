from django.contrib import admin
from .models.material import (MaterialType, ApplicationScenario, MetricCategory, TestConfig,
                    MaterialDataPoint, MaterialLibrary, MaterialCharacteristic)

@admin.register(MaterialCharacteristic)
class MaterialCharacteristicAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)

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
    list_display = ('name', 'name_en', 'category', 'standard', 'condition', 'unit', 'data_type', 'order')
    list_filter = ('category', 'data_type')
    search_fields = ('name', 'name_en', 'standard')
    ordering = ('category__order', 'order')

class MaterialDataPointInline(admin.TabularInline):
    model = MaterialDataPoint
    extra = 1
    autocomplete_fields = ['test_config']

@admin.register(MaterialLibrary)
class MaterialLibraryAdmin(admin.ModelAdmin):
    list_display = ('grade_name', 'manufacturer', 'category', 'creator', 'flammability', 'is_published', 'created_at')
    list_editable = ('is_published',)
    search_fields = ('grade_name', 'manufacturer', 'creator__username')
    list_filter = ('is_published', 'category', 'flammability', 'scenarios', 'characteristics', 'created_at')
    filter_horizontal = ('scenarios', 'characteristics')
    inlines = [MaterialDataPointInline]
    autocomplete_fields = ['category']
