from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from app_project.models import NodeScoreRule
from app_project.forms import NodeScoreRuleForm
from app_project.mixins import ProjectAccessMixin


class PerformanceManagementMixin(ProjectAccessMixin):
    """
    绩效管理专用权限：
    仅限拥有管理权限 (change_project) 且 职级达到 15 级（预设的高级经理级别）的人员。
    或者通过 identity_required 锁定到特定的高级管理角色。
    """
    # 强制要求高职级
    min_level_required = 15 
    
    # 即使是同一部门，普通员工也看不到规则
    enforce_dept_isolation = False # 规则本身不分部门，但准入门槛极高

class NodeScoreRuleListView(PerformanceManagementMixin, ListView):
    """评分规则列表"""
    permission_required = 'app_project.change_project'
    model = NodeScoreRule
    template_name = 'apps/app_project/performance/rule_list.html'
    context_object_name = 'rules'
    ordering = ['trigger_stage', 'trigger_status']


class NodeScoreRuleCreateView(PerformanceManagementMixin, CreateView):
    """创建评分规则"""
    permission_required = 'app_project.change_project'
    model = NodeScoreRule
    form_class = NodeScoreRuleForm
    template_name = 'apps/app_project/performance/rule_form.html'
    success_url = reverse_lazy('project_score_rule_list')

    def form_valid(self, form):
        messages.success(self.request, "评分规则已添加")
        return super().form_valid(form)


class NodeScoreRuleUpdateView(PerformanceManagementMixin, UpdateView):
    """编辑评分规则"""
    permission_required = 'app_project.change_project'
    model = NodeScoreRule
    form_class = NodeScoreRuleForm
    template_name = 'apps/app_project/performance/rule_form.html'
    success_url = reverse_lazy('project_score_rule_list')

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def form_valid(self, form):
        messages.success(self.request, "评分规则已更新")
        return super().form_valid(form)


class NodeScoreRuleDeleteView(PerformanceManagementMixin, DeleteView):
    """删除评分规则"""
    permission_required = 'app_project.change_project'
    model = NodeScoreRule
    success_url = reverse_lazy('project_score_rule_list')

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "评分规则已成功移除")
        return super().delete(request, *args, **kwargs)
