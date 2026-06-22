from django.contrib import admin
from app_material_testing.models import TestingTask, TrialTestResult


@admin.register(TestingTask)
class TestingTaskAdmin(admin.ModelAdmin):
    list_display = ['production_order', 'status', 'assigned_to', 'created_at']
    list_filter = ['status']
    search_fields = ['production_order__code']


@admin.register(TrialTestResult)
class TrialTestResultAdmin(admin.ModelAdmin):
    list_display = ['testing_task', 'test_config', 'formula', 'value', 'is_written_back']
    list_filter = ['is_written_back']
