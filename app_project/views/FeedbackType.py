from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.db.models import Count
from django.shortcuts import redirect

from app_project.models import FeedbackType
from app_project.forms import FeedbackTypeForm
from app_project.mixins import SharedConfigMixin


class FeedbackTypeListView(SharedConfigMixin, ListView):
    """客户意见类型列表"""
    permission_required = 'app_project.change_project'
    model = FeedbackType
    template_name = 'apps/app_project/feedback_type_list.html'
    context_object_name = 'types'
    ordering = ['order', 'name']

    def get_queryset(self):
        return super().get_queryset().annotate(node_count=Count('projectnode')).order_by('order', 'name')


class FeedbackTypeCreateView(SharedConfigMixin, CreateView):
    """创建客户意见类型"""
    permission_required = 'app_project.change_project'
    model = FeedbackType
    form_class = FeedbackTypeForm
    template_name = 'apps/app_project/feedback_type_form.html'
    success_url = reverse_lazy('feedback_type_list')

    def form_valid(self, form):
        messages.success(self.request, "客户意见类型已添加")
        return super().form_valid(form)


class FeedbackTypeUpdateView(SharedConfigMixin, UpdateView):
    """编辑客户意见类型"""
    permission_required = 'app_project.change_project'
    model = FeedbackType
    form_class = FeedbackTypeForm
    template_name = 'apps/app_project/feedback_type_form.html'
    success_url = reverse_lazy('feedback_type_list')

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def form_valid(self, form):
        messages.success(self.request, "客户意见类型已更新")
        return super().form_valid(form)


class FeedbackTypeDeleteView(SharedConfigMixin, DeleteView):
    """删除客户意见类型"""
    permission_required = 'app_project.change_project'
    model = FeedbackType
    success_url = reverse_lazy('feedback_type_list')

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def form_valid(self, form):
        if self.object.projectnode_set.exists():
            messages.error(self.request, f'无法删除"{self.object.name}"：已有 {self.object.projectnode_set.count()} 个项目节点关联了该意见类型。')
            return redirect(self.success_url)
        messages.success(self.request, "客户意见类型已成功移除")
        return super().form_valid(form)
