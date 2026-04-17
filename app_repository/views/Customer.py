from django.core.paginator import Paginator
from django.db.models import Max, Count, Q
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DetailView

from app_repository.forms import CustomerForm
from app_repository.models import Customer, ProjectRepository
from app_project.models import ProjectNode
from app_repository.utils.filters import CustomerFilter
from app_repository.mixins import RepositoryAccessMixin


class CustomerListView(RepositoryAccessMixin, ListView):
    """
    客户列表：需有 view_customer 权限。
    由于客户数据量级较大且通常为共享资源，此处默认不执行严格部门隔离。
    """
    permission_required = 'app_repository.view_customer'
    model = Customer
    template_name = 'apps/app_repository/customer/customer_list.html'
    context_object_name = 'customers'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset().annotate(
            completed_project_count=Count(
                'projectrepository',
                filter=Q(projectrepository__project__progress_percent=100, projectrepository__project__is_terminated=False)
            ),
            inprogress_project_count=Count(
                'projectrepository',
                filter=Q(projectrepository__project__progress_percent__lt=100, projectrepository__project__is_terminated=False)
            ),
            terminated_project_count=Count(
                'projectrepository',
                filter=Q(projectrepository__project__is_terminated=True)
            )
        ).order_by('-id')
        self.filterset = CustomerFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        context['current_sort'] = self.request.GET.get('sort', '')
        return context


class CustomerCreateView(RepositoryAccessMixin, CreateView):
    """新增客户：需有 add_customer 权限"""
    permission_required = 'app_repository.add_customer'
    model = Customer
    form_class = CustomerForm
    template_name = 'apps/app_repository/form_generic.html'
    success_url = reverse_lazy('repo_customer_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增客户'
        return context


class CustomerUpdateView(RepositoryAccessMixin, UpdateView):
    """编辑客户：需有 change_customer 权限"""
    permission_required = 'app_repository.change_customer'
    model = Customer
    form_class = CustomerForm
    template_name = 'apps/app_repository/form_generic.html'
    success_url = reverse_lazy('repo_customer_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑客户: {self.object.company_name}'
        return context


class CustomerDetailView(RepositoryAccessMixin, DetailView):
    """客户详情：需有 view_customer 权限"""
    permission_required = 'app_repository.view_customer'
    model = Customer
    template_name = 'apps/app_repository/customer/customer_detail.html'
    context_object_name = 'customer'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'客户详情: {self.object.company_name}'

        # 获取所有关联的项目档案
        related_projects_list = ProjectRepository.objects.filter(customer=self.object).select_related('project', 'oem', 'salesperson').order_by('-project__created_at')

        # 分页逻辑保持不变
        paginator = Paginator(related_projects_list, 10)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        # 附加进度信息
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
