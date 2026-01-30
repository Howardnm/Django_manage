from django.contrib import admin
from .models import LabFormula, FormulaBOM, FormulaTestResult

# 1. BOM 明细内联
class FormulaBOMInline(admin.TabularInline):
    model = FormulaBOM
    extra = 0
    fields = ('feeding_port', 'weighing_scale', 'raw_material', 'percentage', 'is_pre_mix', 'pre_mix_order', 'pre_mix_time', 'is_tail')
    ordering = ('feeding_port', 'weighing_scale', 'raw_material__category__order', 'raw_material__name')

# 2. 测试结果内联
class FormulaTestResultInline(admin.TabularInline):
    model = FormulaTestResult
    extra = 0
    fields = ('test_config', 'value', 'value_text', 'test_date', 'remark', 'file_report')
    ordering = ('test_config__category__order', 'test_config__order')

# 3. 实验配方主表 Admin
@admin.register(LabFormula)
class LabFormulaAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'material_type', 'creator', 'cost_predicted', 'cost_actual', 'created_at')
    list_filter = ('material_type', 'creator', 'created_at')
    search_fields = ('code', 'name', 'description', 'creator__username')
    readonly_fields = ('code', 'created_at', 'cost_predicted')
    inlines = [FormulaBOMInline, FormulaTestResultInline]
    
    fieldsets = (
        ('基本信息', {
            'fields': ('code', 'name', 'material_type', 'process', 'creator', 'description')
        }),
        ('关联信息', {
            'fields': ('research_projects', 'related_materials')
        }),
        ('成本信息', {
            'fields': ('cost_predicted', 'cost_actual')
        }),
    )
    
    # 优化多对多字段的选择框
    filter_horizontal = ('research_projects', 'related_materials')

# 4. BOM 明细 Admin (可选)
@admin.register(FormulaBOM)
class FormulaBOMAdmin(admin.ModelAdmin):
    list_display = ('formula', 'raw_material', 'percentage', 'feeding_port', 'weighing_scale')
    list_filter = ('feeding_port', 'weighing_scale')
    search_fields = ('formula__name', 'raw_material__name')

# 5. 测试结果 Admin (可选)
@admin.register(FormulaTestResult)
class FormulaTestResultAdmin(admin.ModelAdmin):
    list_display = ('formula', 'test_config', 'value', 'value_text', 'test_date')
    list_filter = ('test_config__category', 'test_date')
    search_fields = ('formula__name', 'test_config__name')
