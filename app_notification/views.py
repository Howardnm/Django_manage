from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.views.generic import ListView
from django.views import View
from django.http import HttpResponseRedirect

from .models import Notification
# 关键修改：只导入 ProjectNode，因为我们只处理这一种目标
from app_project.models import ProjectNode

@login_required
def mark_as_read(request, pk):
    """
    将单条通知标记为已读，并智能重定向到目标页面。
    """
    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    notification.mark_as_read()
    
    target = notification.target
    
    # 关键修改：简化逻辑，只处理 ProjectNode 类型的 target
    if isinstance(target, ProjectNode):
        # 如果目标是节点，构建带锚点的URL
        project_url = reverse('project_detail', kwargs={'pk': target.project.pk})
        next_url = f"{project_url}#node-{target.pk}"
    else:
        # 对于所有其他情况（包括目标为空），都安全地回退到首页
        next_url = reverse('panel_home')

    return redirect(next_url)


class MarkAllAsReadView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        Notification.objects.filter(recipient=request.user, unread=True).update(unread=False)
        referer_url = request.META.get('HTTP_REFERER', reverse('notification_list'))
        return HttpResponseRedirect(referer_url)


class NotificationListView(LoginRequiredMixin, ListView):
    model = Notification
    template_name = 'apps/app_notification/list.html'
    context_object_name = 'notifications'
    paginate_by = 20

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user).select_related(
            'actor'
        ).prefetch_related(
            'target', 'action_object'
        )
