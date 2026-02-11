from django.contrib import admin
from .models import Document, Category, Tag, DocumentContent

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


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    inlines = [DocumentContentInline]

    list_display = (
        'title', 'author', 'document_type', 'category', 'processing_status', 
        'published_at', 'uploaded_by', 'created_at'
    )
    list_filter = ('processing_status', 'document_type', 'category', 'published_at', 'created_at')
    
    # 关键修改：搜索现在只针对高效的 search_vector 字段
    search_fields = ('search_vector',)
    
    filter_horizontal = ('tags', 'related_documents')
    
    readonly_fields = (
        'file_size', 'mime_type', 'page_count', 'processing_error', 
        'processed_at', 'embedding', 'created_at', 'updated_at',
        'search_vector' # 将 search_vector 也设为只读
    )
    
    fieldsets = (
        ('核心信息', {
            'fields': ('title', 'author', 'description', 'document_type', 'category', 'tags')
        }),
        ('文件与来源', {
            'fields': ('original_file', 'source', 'published_at', 'related_documents')
        }),
        ('处理状态与元数据 (自动生成)', {
            'classes': ('collapse',),
            'fields': (
                'processing_status', 'processing_error', 'processed_at', 
                'file_size', 'mime_type', 'page_count', 'embedding', 'search_vector'
            )
        }),
        ('管理信息', {
            'fields': ('uploaded_by', 'created_at', 'updated_at')
        }),
    )

    def save_formset(self, request, form, formset, change):
        """
        确保在保存内联表单时，能正确触发 Document 的 save 方法，从而更新 search_vector。
        """
        # 先保存主对象 Document
        form.instance.save()
        # 然后保存内联对象 DocumentContent
        formset.save()
        # DocumentContent 的 save 方法会再次调用 Document 的 save，确保 search_vector 被更新
        
    def save_model(self, request, obj, form, change):
        """
        确保在只修改 Document 时，也能触发 search_vector 的更新。
        """
        super().save_model(request, obj, form, change)
        # obj.save() 已经被调用，会自动更新 search_vector
