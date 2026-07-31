from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import Project, ProjectNode, ProjectMember, NodeScoreRule, ProjectConfig, ProjectFieldChange

class ProjectNodeInline(admin.TabularInline):
    model = ProjectNode
    extra = 0
    fields = ['stage', 'status', 'round', 'order', 'final_score', 'updated_at']
    readonly_fields = ['updated_at']

class ProjectMemberInline(admin.TabularInline):
    model = ProjectMember
    extra = 1

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'manager', 'current_stage', 'progress_percent', 'is_terminated', 'created_at']
    list_filter = ['current_stage', 'is_terminated', 'manager']
    search_fields = ['name', 'description']
    inlines = [ProjectMemberInline, ProjectNodeInline]

@admin.register(NodeScoreRule)
class NodeScoreRuleAdmin(admin.ModelAdmin):
    list_display = ['name', 'score_value', 'trigger_stage', 'trigger_status', 'is_multiple_rounds']
    list_filter = ['trigger_status', 'trigger_stage', 'is_multiple_rounds']
    search_fields = ['name', 'description']

@admin.register(ProjectMember)
class ProjectMemberAdmin(admin.ModelAdmin):
    list_display = ['project', 'user', 'role', 'workload_share']
    list_filter = ['role', 'user']


@admin.register(ProjectConfig)
class ProjectConfigAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'node_workflow_display', 'repo_workflow_display', 'edit_workflow_display']

    def has_add_permission(self, request):
        return not ProjectConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """禁止删除"""
        return False

    def node_workflow_display(self, obj):
        if obj.default_approval_workflow:
            return format_html(
                '<span class="badge bg-blue-lt">{}</span>',
                obj.default_approval_workflow.name
            )
        return mark_safe('<span class="badge bg-secondary-lt">未配置（节点操作无需审批）</span>')
    node_workflow_display.short_description = '项目节点审批流程'

    def repo_workflow_display(self, obj):
        if obj.default_repository_approval_workflow:
            return format_html(
                '<span class="badge bg-green-lt">{}</span>',
                obj.default_repository_approval_workflow.name
            )
        return mark_safe('<span class="badge bg-secondary-lt">未配置（档案编辑直接生效）</span>')
    repo_workflow_display.short_description = '项目档案审批流程'

    def edit_workflow_display(self, obj):
        if obj.default_project_edit_approval_workflow:
            return format_html(
                '<span class="badge bg-orange-lt">{}</span>',
                obj.default_project_edit_approval_workflow.name
            )
        return mark_safe('<span class="badge bg-secondary-lt">未配置（信息编辑直接生效）</span>')
    edit_workflow_display.short_description = '项目信息编辑审批流程'


@admin.register(ProjectFieldChange)
class ProjectFieldChangeAdmin(admin.ModelAdmin):
    list_display = ['project', 'status_badge', 'submitted_by', 'submission_comment_preview', 'created_at', 'resolved_at']
    list_filter = ['status', 'created_at']
    search_fields = ['project__name', 'submission_comment']
    readonly_fields = ['project', 'code', 'name', 'grade', 'material', 'description',
                       'submitted_by', 'submission_comment', 'status', 'workflow_instance',
                       'created_at', 'resolved_at']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def status_badge(self, obj):
        color_map = {'PENDING': 'bg-purple-lt', 'APPROVED': 'bg-green-lt', 'REJECTED': 'bg-red-lt'}
        css = color_map.get(obj.status, 'bg-secondary-lt')
        return format_html('<span class="badge {}">{}</span>', css, obj.get_status_display())
    status_badge.short_description = '状态'

    def submission_comment_preview(self, obj):
        return obj.submission_comment[:50] + '…' if len(obj.submission_comment) > 50 else obj.submission_comment
    submission_comment_preview.short_description = '提交意见'
