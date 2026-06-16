from django.contrib import admin

from .models import Attachment


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = [
        'display_name', 'category', 'content_type', 'object_id',
        'uploader', 'uploaded_at', 'file_size', 'is_deleted',
    ]
    list_filter = ['category', 'content_type', 'is_deleted', 'uploaded_at']
    search_fields = ['display_name', 'description']
    readonly_fields = ['file_size', 'uploaded_at']
    date_hierarchy = 'uploaded_at'
