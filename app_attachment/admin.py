from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html

from .cleanup import ORPHAN_GRACE, delete_orphan_files, scan_orphan_files
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

    def get_urls(self):
        custom_urls = [
            path(
                'orphan-files/',
                self.admin_site.admin_view(self.orphan_files_view),
                name='app_attachment_attachment_orphan_files',
            ),
        ]
        return custom_urls + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        url = reverse('admin:app_attachment_attachment_orphan_files')
        self.message_user(
            request,
            format_html('<a href="{}">清理无记录的孤儿文件</a>', url),
        )
        return super().changelist_view(request, extra_context)

    def orphan_files_view(self, request):
        if request.method == 'POST':
            if not self.has_delete_permission(request):
                raise PermissionDenied
            result = delete_orphan_files()
            self.message_user(
                request,
                (
                    f"已删除 {result['deleted']} 个孤儿文件，"
                    f"跳过 {result['skipped_recent']} 个未满宽限的文件。"
                ),
            )
            if result['failed']:
                self.message_user(
                    request,
                    f"{result['failed']} 个文件删除失败，详见日志。",
                    level='warning',
                )
            return redirect('admin:app_attachment_attachment_orphan_files')

        if not self.has_view_permission(request):
            raise PermissionDenied
        deletable, recent = scan_orphan_files()
        context = {
            **self.admin_site.each_context(request),
            'title': '清理孤儿文件',
            'opts': self.model._meta,
            'deletable': deletable,
            'recent': recent,
            'total_size': sum(item['size'] for item in deletable),
            'can_delete': self.has_delete_permission(request),
            'grace_minutes': int(ORPHAN_GRACE.total_seconds() // 60),
        }
        return render(request, 'admin/app_attachment/orphan_files.html', context)
