from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import (
    ProductionOrder, ProductionOrderFormulaDetail,
    ExtrusionTask,
    SampleInventory, TrialProductionConfig,
)


@admin.register(ProductionOrder)
class ProductionOrderAdmin(admin.ModelAdmin):
    list_display = ['code', 'trial_code', 'project', 'status', 'creator', 'created_at']
    list_filter = ['status']
    search_fields = ['code', 'trial_code']


@admin.register(ProductionOrderFormulaDetail)
class ProductionOrderFormulaDetailAdmin(admin.ModelAdmin):
    list_display = ['production_order', 'formula', 'planned_quantity', 'needs_color_matching']
    list_filter = ['needs_color_matching']


@admin.register(ExtrusionTask)
class ExtrusionTaskAdmin(admin.ModelAdmin):
    list_display = ['production_order', 'operator', 'status', 'created_at']
    list_filter = ['status']
    search_fields = ['production_order__code', 'production_order__trial_code']


@admin.register(SampleInventory)
class SampleInventoryAdmin(admin.ModelAdmin):
    list_display = ['trial_code', 'type', 'sub_type', 'status', 'quantity',
                    'specimen_count', 'storage_location']
    list_filter = ['type', 'sub_type', 'status']
    search_fields = ['trial_code']


@admin.register(TrialProductionConfig)
class TrialProductionConfigAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'workflow_display', 'updated_at']

    def has_add_permission(self, request):
        """禁止新增（单例模式）"""
        return False

    def has_delete_permission(self, request, obj=None):
        """禁止删除"""
        return False

    def workflow_display(self, obj):
        if obj.workflow_definition:
            return format_html(
                '<span class="badge bg-blue-lt">{}</span>',
                obj.workflow_definition.name
            )
        return mark_safe('<span class="badge bg-secondary-lt">未配置（排产单无需审批）</span>')
    workflow_display.short_description = '审批流程'
