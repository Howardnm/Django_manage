from django.contrib import admin
from django.utils.html import format_html
from django.core.serializers.json import DjangoJSONEncoder
import json

from .models import Document, Category, Tag, DocumentContent, AgentTask, AgentActionLog

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

class DocumentContentInline(admin.StackedInline):
    model = DocumentContent
    can_delete = False
    verbose_name_plural = '文本内容'
    classes = ('collapse',)

class AgentTaskInline(admin.TabularInline):
    """内联显示关联的AI任务，方便快速查看"""
    model = AgentTask
    extra = 0  # 不显示额外空行
    fields = ('task_type', 'status', 'created_at', 'completed_at')
    readonly_fields = fields
    can_delete = False
    show_change_link = True # 允许点击进入任务详情
    verbose_name_plural = '关联的AI任务'


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    inlines = [DocumentContentInline, AgentTaskInline]

    list_display = (
        'title', 'author', 'document_type', 'category', 'processing_status', 
        'published_at', 'uploaded_by', 'created_at'
    )
    list_filter = ('processing_status', 'document_type', 'category', 'published_at', 'created_at')
    search_fields = ('search_vector',)
    filter_horizontal = ('tags', 'related_documents')
    
    readonly_fields = (
        'file_size', 'mime_type', 'page_count', 'processing_error', 
        'processed_at', 'embedding', 'created_at', 'updated_at',
        'search_vector', 'pretty_structured_data'
    )
    
    fieldsets = (
        ('核心信息', {'fields': ('title', 'author', 'description', 'document_type', 'category', 'tags')}),
        ('文件与来源', {'fields': ('original_file', 'source', 'published_at', 'related_documents')}),
        ('AI提取的结构化数据', {
            'classes': ('collapse',),
            'fields': ('pretty_structured_data', 'structured_data') # structured_data 用于编辑
        }),
        ('处理状态与元数据', {
            'classes': ('collapse',),
            'fields': (
                'processing_status', 'processing_error', 'processed_at', 
                'file_size', 'mime_type', 'page_count', 'embedding', 'search_vector'
            )
        }),
        ('管理信息', {'fields': ('uploaded_by', 'created_at', 'updated_at')}),
    )

    @admin.display(description='结构化数据 (格式化预览)')
    def pretty_structured_data(self, obj):
        """将JSON字段格式化输出，提高可读性"""
        if obj.structured_data:
            pretty_json = json.dumps(obj.structured_data, cls=DjangoJSONEncoder, indent=4, ensure_ascii=False)
            return format_html('<pre>{}</pre>', pretty_json)
        return "无"

    def get_fieldsets(self, request, obj=None):
        """动态隐藏 structured_data 编辑框，只显示预览"""
        fieldsets = super().get_fieldsets(request, obj)
        # 移除原始的 structured_data 编辑框，只保留 pretty_structured_data 预览
        # 如果需要编辑，可以从下面的 tuple 中移除 'structured_data'
        fieldsets[2][1]['fields'] = ('pretty_structured_data',)
        return fieldsets


@admin.register(AgentTask)
class AgentTaskAdmin(admin.ModelAdmin):
    list_display = ('document', 'task_type', 'status', 'created_at', 'completed_at')
    list_filter = ('status', 'task_type', 'created_at')
    search_fields = ('document__title',)
    readonly_fields = ('created_at', 'started_at', 'completed_at')


@admin.register(AgentActionLog)
class AgentActionLogAdmin(admin.ModelAdmin):
    list_display = ('document', 'agent_name', 'action_type', 'status', 'created_at', 'duration_ms')
    list_filter = ('agent_name', 'action_type', 'status', 'created_at')
    search_fields = ('document__title', 'prompt', 'result')
    readonly_fields = [f.name for f in AgentActionLog._meta.fields] # 所有字段只读

    def has_add_permission(self, request):
        return False # 不允许手动添加日志

    def has_change_permission(self, request, obj=None):
        return False # 不允许手动修改日志
