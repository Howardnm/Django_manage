from .models import Notification

def notifications(request):
    """
    一个上下文处理器，用于向所有模板添加未读通知。
    """
    if request.user.is_authenticated:
        # 获取当前用户的所有未读通知
        unread_notifications = Notification.objects.filter(recipient=request.user, unread=True)
        return {
            'unread_notifications': unread_notifications,
            'unread_notification_count': unread_notifications.count(),
        }
    return {}
