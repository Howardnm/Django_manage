from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import ListView
from django.views import View
from django.http import HttpResponseRedirect

from .models import Notification
from .mixins import NotificationAccessMixin

# 1. 标记已读
class MarkAsReadView(NotificationAccessMixin, View):
    """将单条通知标记为已读，然后跳转到通知的落地页。Mixin 已确保 recipient 隔离。"""
    permission_required = []  # 仅依赖 L1 角色 + L2 等级准入，不做 L3 权限码校验

    def get(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
        notification.mark_as_read()

        # 跳转到创建时快照的落地页；无落地页则回首页
        return redirect(notification.url or reverse('panel_home'))


# 2. 全部标记已读
class MarkAllAsReadView(NotificationAccessMixin, View):
    """需具备 view_notification 权限（或维持现状，仅限本人）"""
    permission_required = []  # 仅依赖 L1 角色 + L2 等级准入，不做 L3 权限码校验

    def get(self, request, *args, **kwargs):
        # 这里的 get_queryset 已经由 Mixin 自动实现了 recipient 隔离
        Notification.objects.filter(recipient=request.user, unread=True).update(unread=False)
        referer_url = request.META.get('HTTP_REFERER', reverse('notification_list'))
        return HttpResponseRedirect(referer_url)


# 3. 通知列表
class NotificationListView(NotificationAccessMixin, ListView):
    """通知中心列表页"""
    permission_required = []  # 仅依赖 L1 角色 + L2 等级准入，不做 L3 权限码校验
    model = Notification
    template_name = 'apps/app_notification/list.html'
    context_object_name = 'notifications'
    paginate_by = 20

    def get_queryset(self):
        # 1. 调用 Mixin 的本人隔离过滤
        qs = super().get_queryset()
        # 2. actor 是普通外键可 select_related；target/action_object 是 GFK，
        #    但模板只读快照字段（url/title/verb/type/icon），从未访问 target/action_object，
        #    故无需 prefetch。
        return qs.select_related('actor')