from django.contrib import admin
from .models import Project, ProjectNode, ProjectMember, NodeScoreRule

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
