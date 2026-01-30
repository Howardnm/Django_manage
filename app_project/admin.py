from django.contrib import admin
from .models import Project, ProjectNode

# 1. 项目节点内联
class ProjectNodeInline(admin.TabularInline):
    model = ProjectNode
    extra = 0
    fields = ('stage', 'round', 'order', 'status', 'remark', 'updated_at')
    readonly_fields = ('updated_at',)
    ordering = ('order',)

# 2. 项目主表 Admin
@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'manager', 'current_stage', 'progress_percent', 'is_terminated', 'created_at')
    list_filter = ('current_stage', 'is_terminated', 'created_at', 'manager')
    search_fields = ('name', 'manager__username', 'description')
    readonly_fields = ('created_at', 'current_stage', 'progress_percent', 'is_terminated', 'latest_remark')
    inlines = [ProjectNodeInline]
    
    fieldsets = (
        ('基本信息', {
            'fields': ('name', 'manager', 'description')
        }),
        ('进度概览 (自动更新)', {
            'fields': ('current_stage', 'progress_percent', 'is_terminated', 'latest_remark', 'created_at')
        }),
    )

# 3. 项目节点 Admin (可选)
@admin.register(ProjectNode)
class ProjectNodeAdmin(admin.ModelAdmin):
    list_display = ('project', 'stage', 'round', 'order', 'status', 'updated_at')
    list_filter = ('stage', 'status', 'updated_at')
    search_fields = ('project__name', 'remark')
    ordering = ('project', 'order')
