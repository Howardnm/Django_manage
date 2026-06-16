from django.contrib import admin
from .models import ResearchProject, ResearchProjectNode

# 1. 预研项目节点内联
class ResearchProjectNodeInline(admin.TabularInline):
    model = ResearchProjectNode
    extra = 0
    fields = ('stage', 'round', 'order', 'status', 'remark', 'updated_at')
    readonly_fields = ('updated_at',)
    ordering = ('order',)

# 2. 预研项目主表 Admin
@admin.register(ResearchProject)
class ResearchProjectAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'manager', 'current_stage', 'progress_percent', 'is_terminated', 'created_at')
    list_filter = ('current_stage', 'is_terminated', 'created_at', 'manager')
    search_fields = ('name', 'code', 'manager__username', 'description')
    readonly_fields = ('code', 'created_at', 'current_stage', 'progress_percent', 'is_terminated', 'latest_remark')
    inlines = [ResearchProjectNodeInline]

    fieldsets = (
        ('基本信息', {
            'fields': ('name', 'code', 'manager', 'description')
        }),
        ('进度概览 (自动更新)', {
            'fields': ('current_stage', 'progress_percent', 'is_terminated', 'latest_remark', 'created_at')
        }),
    )

# 3. 预研项目节点 Admin (可选，方便单独管理)
@admin.register(ResearchProjectNode)
class ResearchProjectNodeAdmin(admin.ModelAdmin):
    list_display = ('project', 'stage', 'round', 'order', 'status', 'updated_at')
    list_filter = ('stage', 'status', 'updated_at')
    search_fields = ('project__name', 'remark')
    ordering = ('project', 'order')
