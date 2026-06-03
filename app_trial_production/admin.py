from django.contrib import admin
from .models import (
    ProductionOrder, MoldType, ExtrusionRecord,
    ProductionOutput, SampleSplit, SampleInventory,
    InjectionMoldingOrder, MoldRequirement, SpecimenInventory,
    TestingOrder, TrialTestResult,
)


@admin.register(ProductionOrder)
class ProductionOrderAdmin(admin.ModelAdmin):
    list_display = ['code', 'trial_code', 'project', 'status', 'creator', 'created_at']
    list_filter = ['status']
    search_fields = ['code', 'trial_code']


@admin.register(MoldType)
class MoldTypeAdmin(admin.ModelAdmin):
    list_display = ['mold_code', 'name', 'standard', 'cavity_count', 'status']


@admin.register(ExtrusionRecord)
class ExtrusionRecordAdmin(admin.ModelAdmin):
    list_display = ['production_order', 'throughput', 'screw_speed', 'created_at']


@admin.register(ProductionOutput)
class ProductionOutputAdmin(admin.ModelAdmin):
    list_display = ['production_order', 'total_output', 'created_at']


@admin.register(SampleSplit)
class SampleSplitAdmin(admin.ModelAdmin):
    list_display = ['production_order', 'destination', 'quantity']


@admin.register(SampleInventory)
class SampleInventoryAdmin(admin.ModelAdmin):
    list_display = ['production_order', 'quantity', 'status', 'customer_name']


@admin.register(InjectionMoldingOrder)
class InjectionMoldingOrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'production_order', 'status', 'assigned_operator', 'created_at']


@admin.register(MoldRequirement)
class MoldRequirementAdmin(admin.ModelAdmin):
    list_display = ['injection_order', 'mold', 'specimen_quantity']


@admin.register(SpecimenInventory)
class SpecimenInventoryAdmin(admin.ModelAdmin):
    list_display = ['injection_order', 'mold', 'quantity_produced', 'quantity_qualified', 'status']


@admin.register(TestingOrder)
class TestingOrderAdmin(admin.ModelAdmin):
    list_display = ['production_order', 'status', 'assigned_to', 'created_at']


@admin.register(TrialTestResult)
class TrialTestResultAdmin(admin.ModelAdmin):
    list_display = ['testing_order', 'test_config', 'value', 'is_written_back']
