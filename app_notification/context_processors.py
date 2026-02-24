from .models import Notification

def notifications(request):
    """
    一个上下文处理器，用于向所有模板添加未读通知。
    """
    if request.user.is_authenticated:
        # 关键修改：查询所有未读通知的总数
        unread_count = Notification.objects.filter(recipient=request.user, unread=True).count()
        
        # 关键修改：只获取最新的10条未读通知用于显示
        unread_list = Notification.objects.filter(recipient=request.user, unread=True)[:10]
        
        return {
            'unread_notifications': unread_list,
            'unread_notification_count': unread_count,
        }
    return {}
