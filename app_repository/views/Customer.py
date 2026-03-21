from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Max, Count, Q
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DetailView

from app_repository.forms import CustomerForm
from app_repository.models import Customer, ProjectRepository
from app_project.models import ProjectNode
from app_repository.utils.filters import CustomerFilter

# ==========================================
# 1. 客户库视图 (Customer)
# ==========================================
class CustomerListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'app_repository.view_customer'
    model = Customer
    template_name = 'apps/app_repository/customer/customer_list.html'
    context_object_name = 'customers'
    paginate_by = 10

    def get_queryset(self):
        # 使用条件聚合来分别计算不同状态下的项目数量
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


class CustomerCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'app_repository.add_customer'
    raise_exception = True
    model = Customer
    form_class = CustomerForm
    template_name = 'apps/app_repository/form_generic.html'
    success_url = reverse_lazy('repo_customer_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增客户'
        return context


class CustomerUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'app_repository.change_customer'
    raise_exception = True
    model = Customer
    form_class = CustomerForm
    template_name = 'apps/app_repository/form_generic.html'
    success_url = reverse_lazy('repo_customer_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑客户: {self.object.company_name}'
        return context


class CustomerDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = 'app_repository.view_customer'
    model = Customer
    template_name = 'apps/app_repository/customer/customer_detail.html'
    context_object_name = 'customer'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'客户详情: {self.object.company_name}'

        # 获取所有关联的项目档案
        related_projects_list = ProjectRepository.objects.filter(customer=self.object).select_related('project', 'oem', 'salesperson').order_by('-project__created_at')

        # --- 手动分页 ---
        paginator = Paginator(related_projects_list, 10)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        # --- 为当前页的项目附加最新的节点更新时间 (跨数据库兼容方案) ---
        project_ids = [repo.project.id for repo in page_obj]
        
        # 使用 annotate 和 Max 来分组获取每个 project_id 的最大 updated_at
        latest_updates = ProjectNode.objects.filter(
            project_id__in=project_ids
        ).values('project_id').annotate(
            max_updated_at=Max('updated_at')
        )
        
        # 创建一个 project_id -> max_updated_at 的映射字典
        latest_node_map = {item['project_id']: item['max_updated_at'] for item in latest_updates}

        # 将最新的更新时间附加到项目对象上
        for repo in page_obj:
            repo.project.latest_node_update = latest_node_map.get(repo.project.id)

        # 保持和 ListView 一致的上下文变量
        context['page_obj'] = page_obj
        context['paginator'] = paginator
        context['is_paginated'] = page_obj.has_other_pages()

        return context
