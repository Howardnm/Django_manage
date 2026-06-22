from django.contrib import admin
from app_mold_injection.models import InjectionTask, MoldRequirement, MoldType


@admin.register(InjectionTask)
class InjectionTaskAdmin(admin.ModelAdmin):
    list_display = ['id', 'production_order', 'source', 'status', 'operator', 'created_at']
    list_filter = ['status', 'source']
    search_fields = ['production_order__code', 'sample_inventory__trial_code']


@admin.register(MoldRequirement)
class MoldRequirementAdmin(admin.ModelAdmin):
    list_display = ['injection_task', 'mold', 'specimen_quantity']


@admin.register(MoldType)
class MoldTypeAdmin(admin.ModelAdmin):
    list_display = ['mold_code', 'name', 'standard', 'cavity_count', 'status']
    list_filter = ['standard', 'mold_type', 'status']
    search_fields = ['mold_code', 'name']
