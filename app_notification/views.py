from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import ListView
from django.views import View
from django.http import HttpResponseRedirect

from .models import Notification
from app_project.models import ProjectNode
from .mixins import NotificationAccessMixin

# 1. 标记已读
class MarkAsReadView(NotificationAccessMixin, View):
    """将单条通知标记为已读，然后智能重定向。Mixin 已确保 recipient 隔离。"""

    def get(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
        notification.mark_as_read()

        target = notification.target
        if isinstance(target, ProjectNode):
            project_url = reverse('project_detail', kwargs={'pk': target.project.pk})
            next_url = f"{project_url}#node-{target.pk}"
        else:
            next_url = reverse('panel_home')

        return redirect(next_url)


# 2. 全部标记已读
class MarkAllAsReadView(NotificationAccessMixin, View):
    """需具备 view_notification 权限（或维持现状，仅限本人）"""
    def get(self, request, *args, **kwargs):
        # 这里的 get_queryset 已经由 Mixin 自动实现了 recipient 隔离
        Notification.objects.filter(recipient=request.user, unread=True).update(unread=False)
        referer_url = request.META.get('HTTP_REFERER', reverse('notification_list'))
        return HttpResponseRedirect(referer_url)


# 3. 通知列表
class NotificationListView(NotificationAccessMixin, ListView):
    """通知中心列表页"""
    model = Notification
    template_name = 'apps/app_notification/list.html'
    context_object_name = 'notifications'
    paginate_by = 20

    def get_queryset(self):
        # 1. 调用 Mixin 的本人隔离过滤
        qs = super().get_queryset().select_related('actor').prefetch_related('target', 'action_object')
        return qs
