from django.contrib import admin
from .models import Notification

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        'recipient', 
        'actor', 
        'verb', 
        'target', 
        'unread', 
        'timestamp'
    )
    list_filter = ('unread', 'timestamp')
    search_fields = ('recipient__username', 'actor__username', 'verb')
    
    # 将所有字段设为只读，因为通知是系统生成的，不应手动修改
    readonly_fields = [field.name for field in Notification._meta.get_fields()]

    def has_add_permission(self, request):
        # 禁止在后台手动添加通知
        return False

    def has_change_permission(self, request, obj=None):
        # 允许查看，但禁止编辑
        # 如果您希望完全禁止进入修改页面，可以返回 False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        # 允许管理员删除通知
        return True
