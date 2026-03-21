from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Count, Q, Max
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DetailView

from app_project.models import ProjectNode
from app_repository.forms import SalespersonForm
from app_repository.models import Salesperson, ProjectRepository
from app_repository.utils.filters import SalespersonFilter

# ==========================================
# 6. 业务员管理 (Salesperson)
# ==========================================
class SalespersonListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'app_repository.view_salesperson'
    model = Salesperson
    template_name = 'apps/app_repository/salesperson/salesperson_list.html'
    context_object_name = 'salespersons'
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
        ).order_by('name')
        self.filterset = SalespersonFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        return context


class SalespersonDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = 'app_repository.view_salesperson'
    model = Salesperson
    template_name = 'apps/app_repository/salesperson/salesperson_detail.html'
    context_object_name = 'salesperson'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'业务员详情: {self.object.name}'

        related_projects_list = ProjectRepository.objects.filter(salesperson=self.object).select_related(
            'project', 'customer', 'oem'
        ).order_by('-project__created_at')

        paginator = Paginator(related_projects_list, 10)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        project_ids = [repo.project.id for repo in page_obj]
        latest_updates = ProjectNode.objects.filter(
            project_id__in=project_ids
        ).values('project_id').annotate(
            max_updated_at=Max('updated_at')
        )
        latest_node_map = {item['project_id']: item['max_updated_at'] for item in latest_updates}

        for repo in page_obj:
            repo.project.latest_node_update = latest_node_map.get(repo.project.id)

        context['page_obj'] = page_obj
        context['paginator'] = paginator
        context['is_paginated'] = page_obj.has_other_pages()

        return context


class SalespersonCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'app_repository.add_salesperson'
    raise_exception = True
    model = Salesperson
    form_class = SalespersonForm
    template_name = 'apps/app_repository/form_generic.html'
    success_url = reverse_lazy('repo_sales_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增业务员'
        return context


class SalespersonUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'app_repository.change_salesperson'
    raise_exception = True
    model = Salesperson
    form_class = SalespersonForm
    template_name = 'apps/app_repository/form_generic.html'
    success_url = reverse_lazy('repo_sales_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑业务员: {self.object.name}'
        return context
