from .models import Notification

def notifications(request):
    """
    一个上下文处理器，用于向所有模板添加未读通知。
    """
    if request.user.is_authenticated:
        # 关键修改：查询所有未读通知的总数（角标用 count，语义不同于列表 slice）
        unread_count = Notification.objects.filter(recipient=request.user, unread=True).count()

        # 只获取最新的10条未读通知用于显示。
        # select_related('actor') 避免模板访问 actor.username 产生 N+1；
        # only() 只取模板用到的列减负。
        unread_list = (
            Notification.objects.filter(recipient=request.user, unread=True)
            .select_related('actor')
            .only('type', 'icon', 'title', 'verb', 'url', 'actor', 'unread', 'timestamp')[:10]
        )

        return {
            'unread_notifications': unread_list,
            'unread_notification_count': unread_count,
        }
    return {}
