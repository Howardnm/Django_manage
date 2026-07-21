from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.db.models import Count
from django.shortcuts import redirect

from app_project.models import FailureReason
from app_project.forms import FailureReasonForm
from app_project.mixins import ProjectAccessMixin


class FailureReasonListView(ProjectAccessMixin, ListView):
    """不合格原因列表"""
    permission_required = 'app_project.change_project'
    model = FailureReason
    template_name = 'apps/app_project/failure_reason_list.html'
    context_object_name = 'reasons'
    ordering = ['order', 'name']

    def get_queryset(self):
        return super().get_queryset().annotate(node_count=Count('projectnode')).order_by('order', 'name')


class FailureReasonCreateView(ProjectAccessMixin, CreateView):
    """创建不合格原因"""
    permission_required = 'app_project.change_project'
    model = FailureReason
    form_class = FailureReasonForm
    template_name = 'apps/app_project/failure_reason_form.html'
    success_url = reverse_lazy('failure_reason_list')

    def form_valid(self, form):
        messages.success(self.request, "不合格原因已添加")
        return super().form_valid(form)


class FailureReasonUpdateView(ProjectAccessMixin, UpdateView):
    """编辑不合格原因"""
    permission_required = 'app_project.change_project'
    model = FailureReason
    form_class = FailureReasonForm
    template_name = 'apps/app_project/failure_reason_form.html'
    success_url = reverse_lazy('failure_reason_list')

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def form_valid(self, form):
        messages.success(self.request, "不合格原因已更新")
        return super().form_valid(form)


class FailureReasonDeleteView(ProjectAccessMixin, DeleteView):
    """删除不合格原因"""
    permission_required = 'app_project.change_project'
    model = FailureReason
    success_url = reverse_lazy('failure_reason_list')

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def form_valid(self, form):
        if self.object.projectnode_set.exists():
            messages.error(self.request, f'无法删除"{self.object.name}"：已有 {self.object.projectnode_set.count()} 个项目节点关联了该不合格原因。')
            return redirect(self.success_url)
        messages.success(self.request, "不合格原因已成功移除")
        return super().form_valid(form)
