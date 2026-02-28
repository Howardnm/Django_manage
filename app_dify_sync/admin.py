from django.contrib import admin
from .models import DifySyncRecord

@admin.register(DifySyncRecord)
class DifySyncRecordAdmin(admin.ModelAdmin):
    list_display = (
        'content_object',
        'status',
        'dify_dataset_id',
        'dify_document_id',
        'last_sync_at',
        'updated_at',
    )
    list_filter = ('status', 'content_type', 'last_sync_at')
    search_fields = ('dify_document_id', 'object_id')
    list_per_page = 25

    # 将所有字段设为只读，因为这些记录由系统自动管理
    readonly_fields = [field.name for field in DifySyncRecord._meta.get_fields()]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # 允许查看详情，但不允许编辑
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        # 允许管理员手动删除同步记录（例如，用于强制重新同步）
        return True
