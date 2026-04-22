from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from app_repository.models import GradeFactor
from app_repository.forms import GradeFactorForm
from app_project.views.PerformanceRule import PerformanceManagementMixin

class GradeFactorListView(PerformanceManagementMixin, ListView):
    """等级因子规则列表"""
    permission_required = 'app_repository.view_gradefactor'
    model = GradeFactor
    template_name = 'apps/app_repository/performance/grade_factor_list.html'
    context_object_name = 'factors'
    ordering = ['factor']

class GradeFactorCreateView(PerformanceManagementMixin, CreateView):
    """创建等级因子"""
    permission_required = 'app_repository.add_gradefactor'
    model = GradeFactor
    form_class = GradeFactorForm
    template_name = 'apps/app_repository/performance/grade_factor_form.html'
    success_url = reverse_lazy('repo_grade_factor_list')

    def form_valid(self, form):
        messages.success(self.request, "等级因子已添加")
        return super().form_valid(form)

class GradeFactorUpdateView(PerformanceManagementMixin, UpdateView):
    """编辑等级因子"""
    permission_required = 'app_repository.change_gradefactor'
    model = GradeFactor
    form_class = GradeFactorForm
    template_name = 'apps/app_repository/performance/grade_factor_form.html'
    success_url = reverse_lazy('repo_grade_factor_list')

    def form_valid(self, form):
        messages.success(self.request, "等级因子已更新")
        return super().form_valid(form)

class GradeFactorDeleteView(PerformanceManagementMixin, DeleteView):
    """删除等级因子"""
    permission_required = 'app_repository.delete_gradefactor'
    model = GradeFactor
    success_url = reverse_lazy('repo_grade_factor_list')

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "等级因子已删除")
        return super().delete(request, *args, **kwargs)
