from django.core.paginator import Paginator
from django.db.models import Max, Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import ListView, CreateView, UpdateView, DetailView, View

from app_project.models import ProjectNode
from app_repository.forms import OEMForm
from app_repository.models import OEM, ProjectRepository
from app_repository.utils.filters import OEMFilter
from app_repository.mixins import RepositoryAccessMixin


class OEMListView(RepositoryAccessMixin, ListView):
    """主机厂列表：内部人员可见"""
    permission_required = 'app_repository.view_oem'
    model = OEM
    template_name = 'apps/app_repository/oem/oem_list.html'
    context_object_name = 'oems'
    paginate_by = 10
    
    enforce_dept_isolation = False

    def get_queryset(self):
        # 预加载联系人账号
        qs = super().get_queryset().prefetch_related('members').annotate(
            completed_project_count=Count(
                'repo_records',
                filter=Q(repo_records__project__progress_percent=100, repo_records__project__is_terminated=False)
            ),
            inprogress_project_count=Count(
                'repo_records',
                filter=Q(repo_records__project__progress_percent__lt=100, repo_records__project__is_terminated=False)
            ),
            terminated_project_count=Count(
                'repo_records',
                filter=Q(repo_records__project__is_terminated=True)
            )
        ).order_by('name')
        self.filterset = OEMFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        context['current_sort'] = self.request.GET.get('sort', '')
        return context


class OEMDetailView(RepositoryAccessMixin, DetailView):
    """主机厂详情：增加关联联系人列表"""
    permission_required = 'app_repository.view_oem'
    model = OEM
    template_name = 'apps/app_repository/oem/oem_detail.html'
    context_object_name = 'oem'

    def get_queryset(self):
        return super().get_queryset().prefetch_related('members')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        oem = self.object
        context['page_title'] = f'主机厂详情: {oem.name}'
        
        # 1. 获取关联的联系人账号
        context['contacts'] = oem.members.all().order_by('username')

        # 2. 获取关联项目列表
        related_projects_list = ProjectRepository.objects.filter(oem=oem).select_related(
            'project', 'customer', 'salesperson'
        ).order_by('-project__created_at')

        paginator = Paginator(related_projects_list, 10)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        project_ids = [repo.project.id for repo in page_obj]
        latest_updates = ProjectNode.objects.filter(
            project_id__in=project_ids
        ).values('project_id').annotate(max_updated_at=Max('updated_at'))
        latest_node_map = {item['project_id']: item['max_updated_at'] for item in latest_updates}

        for repo in page_obj:
            repo.project.latest_node_update = latest_node_map.get(repo.project.id)

        context.update({
            'page_obj': page_obj,
            'paginator': paginator,
            'is_paginated': page_obj.has_other_pages()
        })
        return context


class OEMCreateView(RepositoryAccessMixin, CreateView):
    """新增主机厂公司"""
    permission_required = 'app_repository.add_oem'
    model = OEM
    form_class = OEMForm
    template_name = 'apps/app_repository/form_generic.html'

    def get_success_url(self):
        return reverse('repo_oem_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增主机厂公司 (OEM)'
        return context


class OEMUpdateView(RepositoryAccessMixin, UpdateView):
    """编辑主机厂公司信息"""
    permission_required = 'app_repository.change_oem'
    model = OEM
    form_class = OEMForm
    template_name = 'apps/app_repository/form_generic.html'

    def get_success_url(self):
        return reverse('repo_oem_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑主机厂: {self.object.name}'
        return context
