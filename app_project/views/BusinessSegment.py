from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.db.models import Count
from django.shortcuts import redirect

from app_project.models import BusinessSegment, Project
from app_project.forms import BusinessSegmentForm
from app_project.mixins import SharedConfigMixin


class BusinessSegmentListView(SharedConfigMixin, ListView):
    """业务板块列表"""
    permission_required = 'app_project.change_project'
    model = BusinessSegment
    template_name = 'apps/app_project/business_segment_list.html'
    context_object_name = 'segments'
    ordering = ['order', 'name']

    def get_queryset(self):
        return super().get_queryset().annotate(project_count=Count('project')).order_by('order', 'name')


class BusinessSegmentCreateView(SharedConfigMixin, CreateView):
    """创建业务板块"""
    permission_required = 'app_project.change_project'
    model = BusinessSegment
    form_class = BusinessSegmentForm
    template_name = 'apps/app_project/business_segment_form.html'
    success_url = reverse_lazy('business_segment_list')

    def form_valid(self, form):
        messages.success(self.request, "业务板块已添加")
        return super().form_valid(form)


class BusinessSegmentUpdateView(SharedConfigMixin, UpdateView):
    """编辑业务板块"""
    permission_required = 'app_project.change_project'
    model = BusinessSegment
    form_class = BusinessSegmentForm
    template_name = 'apps/app_project/business_segment_form.html'
    success_url = reverse_lazy('business_segment_list')

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def form_valid(self, form):
        messages.success(self.request, "业务板块已更新")
        return super().form_valid(form)


class BusinessSegmentDeleteView(SharedConfigMixin, DeleteView):
    """删除业务板块"""
    permission_required = 'app_project.change_project'
    model = BusinessSegment
    success_url = reverse_lazy('business_segment_list')

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def form_valid(self, form):
        count = Project.objects.filter(business_segment=self.object).count()
        if count:
            messages.error(self.request, f'无法删除"{self.object.name}"：已有 {count} 个项目关联了该业务板块。')
            return redirect(self.success_url)
        messages.success(self.request, "业务板块已成功移除")
        return super().form_valid(form)
