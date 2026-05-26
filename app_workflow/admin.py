from django.contrib import admin
from .models import WorkflowDefinition, WorkflowInstance, WorkflowTask, ApprovalHistory


@admin.register(WorkflowDefinition)
class WorkflowDefinitionAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'created_by', 'created_at', 'updated_at')
    search_fields = ('name',)


@admin.register(WorkflowInstance)
class WorkflowInstanceAdmin(admin.ModelAdmin):
    list_display = ('definition', 'status', 'started_by', 'started_at', 'completed_at', 'canceled_by')
    list_filter = ('status',)
    raw_id_fields = ('started_by', 'canceled_by')


@admin.register(WorkflowTask)
class WorkflowTaskAdmin(admin.ModelAdmin):
    list_display = ('task_name', 'instance', 'assigned_to', 'status', 'due_date', 'created_at')
    list_filter = ('status',)


@admin.register(ApprovalHistory)
class ApprovalHistoryAdmin(admin.ModelAdmin):
    list_display = ('instance', 'approver', 'action', 'timestamp')
    list_filter = ('action',)
