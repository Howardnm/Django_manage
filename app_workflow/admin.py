from django.contrib import admin
from .models import WorkflowDefinition, WorkflowInstance, WorkflowTask, ApprovalHistory, WorkflowTaskConfig


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


@admin.register(WorkflowTaskConfig)
class WorkflowTaskConfigAdmin(admin.ModelAdmin):
    """Task 节点配置管理。task_id 可自由编辑，修改后需同步更新 BPMN XML 中的 userTask id。

    完整配置流程：
        第一步：app_user →「组织角色」→ 创建角色（如：组长、部门经理）
        第二步：app_user →「组织角色指派」→ 将人员指派到具体组织单元
        第三步：此处创建 Task 节点配置，关联 task_id 与组织角色
        第四步：BPMN 编辑器中将 userTask 的 id 设为与 task_id 相同的值
    """
    list_display = ('task_id', 'display_name', 'resolution_mode',
                    'org_role', 'review_group', 'is_active', 'updated_at')
    list_filter = ('resolution_mode', 'is_active', 'org_role')
    search_fields = ('task_id', 'display_name', 'description')
    list_editable = ('display_name', 'resolution_mode', 'org_role', 'is_active')
    filter_horizontal = ('workflow_definitions',)
    fieldsets = (
        ('节点标识', {
            'fields': ('task_id', 'display_name', 'description'),
        }),
        ('审批人解析策略', {
            'fields': ('resolution_mode', 'org_role', 'review_group', 'static_assignee'),
        }),
        ('关联与启用', {
            'fields': ('workflow_definitions', 'is_active'),
        }),
    )
