from django.contrib import admin
from .models import *


# ==========================================
# 1. 基础配置管理 (Config)
# ==========================================
@admin.register(MetricCategory)
class MetricCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'order')
    ordering = ('order',)


@admin.register(TestConfig)
class TestConfigAdmin(admin.ModelAdmin):
    list_display = ('name', 'standard', 'condition', 'unit', 'category', 'order')
    list_filter = ('category',)
    search_fields = ('name', 'standard')
    ordering = ('category__order', 'order')


# ==========================================
# 2. 材料库管理 (核心)
# ==========================================

# 定义性能数据的内联编辑 (像 Excel 一样在材料页编辑属性)
class MaterialDataPointInline(admin.TabularInline):
    model = MaterialDataPoint
    extra = 0  # 默认不显示空行
    autocomplete_fields = ['test_config']  # 如果配置项很多，开启搜索自动补全


# 定义额外文件的内联编辑
class MaterialFileInline(admin.TabularInline):
    model = MaterialFile
    extra = 0


@admin.register(MaterialLibrary)
class MaterialLibraryAdmin(admin.ModelAdmin):
    # 【修复】删除了 density 等旧字段
    list_display = ('grade_name', 'manufacturer', 'category', 'created_at')
    search_fields = ('grade_name', 'manufacturer')
    list_filter = ('category', 'scenarios')

    # 加上内联，方便在后台查看和录入 EAV 数据
    inlines = [MaterialDataPointInline, MaterialFileInline]

    # 启用多选框的水平过滤控件 (针对 scenarios)
    filter_horizontal = ('scenarios',)


# ==========================================
# 3. 项目档案管理
# ==========================================

class ProjectFileInline(admin.TabularInline):
    model = ProjectFile
    extra = 0


@admin.register(ProjectRepository)
class ProjectRepositoryAdmin(admin.ModelAdmin):
    list_display = ('project', 'customer', 'oem', 'material', 'updated_at')
    search_fields = ('project__name', 'customer__company_name')
    # 可以在档案里直接管理文件
    inlines = [ProjectFileInline]


# ==========================================
# 4. 其他主数据
# ==========================================
@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'contact_name', 'phone')
    search_fields = ('company_name',)


admin.site.register(MaterialType)
admin.site.register(ApplicationScenario)
admin.site.register(OEM)
admin.site.register(Salesperson)