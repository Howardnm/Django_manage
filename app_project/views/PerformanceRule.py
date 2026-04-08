from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from app_project.models import NodeScoreRule
from app_project.forms import NodeScoreRuleForm


class NodeScoreRuleListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """评分规则列表"""
    permission_required = 'app_project.change_project' # 通常只有管理权的人能看
    model = NodeScoreRule
    template_name = 'apps/app_project/performance/rule_list.html'
    context_object_name = 'rules'
    ordering = ['trigger_stage', 'trigger_status']


class NodeScoreRuleCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """创建评分规则"""
    permission_required = 'app_project.change_project'
    model = NodeScoreRule
    form_class = NodeScoreRuleForm
    template_name = 'apps/app_project/performance/rule_form.html'
    success_url = reverse_lazy('project_score_rule_list')

    def form_valid(self, form):
        messages.success(self.request, "评分规则已添加")
        return super().form_valid(form)


class NodeScoreRuleUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """编辑评分规则"""
    permission_required = 'app_project.change_project'
    model = NodeScoreRule
    form_class = NodeScoreRuleForm
    template_name = 'apps/app_project/performance/rule_form.html'
    success_url = reverse_lazy('project_score_rule_list')

    def form_valid(self, form):
        messages.success(self.request, "评分规则已更新")
        return super().form_valid(form)


class NodeScoreRuleDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """删除评分规则"""
    permission_required = 'app_project.change_project'
    model = NodeScoreRule
    success_url = reverse_lazy('project_score_rule_list')

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "评分规则已成功移除")
        return super().delete(request, *args, **kwargs)
