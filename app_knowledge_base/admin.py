from django.contrib import admin
from .models import Document, Category, Tag

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'document_type', 'category', 'uploaded_by', 'created_at', 'updated_at')
    list_filter = ('document_type', 'category', 'created_at')
    search_fields = ('title', 'description', 'content')
    filter_horizontal = ('tags',)
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('title', 'description', 'document_type', 'category', 'tags')
        }),
        ('文件与内容', {
            'fields': ('original_file', 'content', 'embedding')
        }),
        ('元数据', {
            'fields': ('uploaded_by', 'created_at', 'updated_at')
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        # embedding 字段通常是程序生成的，不建议手动编辑
        return self.readonly_fields + ('embedding',)
