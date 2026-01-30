from django.contrib import admin
from .models import (
    MaterialType, ApplicationScenario, OEM, Salesperson,
    MetricCategory, TestConfig, MaterialLibrary, MaterialDataPoint,
    MaterialFile, Customer, ProjectRepository, ProjectFile
)

# ==========================================
# 1. 基础配置管理 (Config)
# ==========================================
@admin.register(MaterialType)
class MaterialTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'classification', 'description')
    search_fields = ('name', 'classification')
    list_filter = ('classification',)

@admin.register(ApplicationScenario)
class ApplicationScenarioAdmin(admin.ModelAdmin):
    list_display = ('name', 'requirements')
    search_fields = ('name',)

@admin.register(OEM)
class OEMAdmin(admin.ModelAdmin):
    list_display = ('name', 'short_name', 'description')
    search_fields = ('name', 'short_name')

@admin.register(Salesperson)
class SalespersonAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'email')
    search_fields = ('name', 'phone', 'email')

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

# ==========================================
# 2. 材料库管理 (核心)
# ==========================================

class MaterialDataPointInline(admin.TabularInline):
    model = MaterialDataPoint
    extra = 1
    autocomplete_fields = ['test_config']

class MaterialFileInline(admin.TabularInline):
    model = MaterialFile
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
    list_display = ('material', 'file_type', 'description', 'uploaded_at')
    list_filter = ('file_type', 'uploaded_at')
    search_fields = ('material__grade_name', 'description')
    autocomplete_fields = ['material']

# ==========================================
# 3. 客户库管理
# ==========================================
@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'short_name', 'contact_name', 'phone', 'tech_contact')
    search_fields = ('company_name', 'short_name', 'contact_name')

# ==========================================
# 4. 项目档案管理
# ==========================================

class ProjectFileInline(admin.TabularInline):
    model = ProjectFile
    extra = 1

@admin.register(ProjectRepository)
class ProjectRepositoryAdmin(admin.ModelAdmin):
    list_display = ('project', 'customer', 'oem', 'salesperson', 'material', 'updated_at')
    search_fields = ('project__name', 'customer__company_name', 'oem__name', 'product_name')
    list_filter = ('salesperson', 'updated_at')
    autocomplete_fields = ['project', 'customer', 'oem', 'salesperson', 'material']
    inlines = [ProjectFileInline]

@admin.register(ProjectFile)
class ProjectFileAdmin(admin.ModelAdmin):
    list_display = ('repository', 'file_type', 'description', 'uploaded_at')
    list_filter = ('file_type', 'uploaded_at')
    search_fields = ('repository__project__name', 'description')
    autocomplete_fields = ['repository']
