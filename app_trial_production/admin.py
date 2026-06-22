from django.contrib import admin
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
    list_display = ['production_order', 'operator', 'status', 'total_output', 'created_at']
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
    list_display = ['pk', 'workflow_definition', 'updated_at']
