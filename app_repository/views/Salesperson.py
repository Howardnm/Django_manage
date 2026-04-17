from django.core.paginator import Paginator
from django.db.models import Count, Q, Max
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView
from django.contrib.auth import get_user_model

from app_project.models import ProjectNode
from app_repository.models import ProjectRepository
from app_repository.utils.filters import ProjectRepositoryFilter # 借用项目档案过滤器
from app_repository.mixins import RepositoryAccessMixin

User = get_user_model()

# ==========================================
# 6. 业务员/内部成员视图 (基于自定义 User)
# ==========================================
class SalespersonListView(RepositoryAccessMixin, ListView):
    """
    业务榜单/成员列表：
    - 展示所有内部员工及其负责的项目统计。
    - 仅限内部员工可见。
    """
    permission_required = 'app_user.view_user' # 使用 User 的查看权限
    model = User
    template_name = 'apps/app_repository/salesperson/salesperson_list.html'
    context_object_name = 'salespersons'
    paginate_by = 12
    
    # 榜单全局可见
    enforce_dept_isolation = False

    def get_queryset(self):
        # 仅筛选内部员工角色
        qs = User.objects.filter(
            user_type__in=[User.UserType.SALES, User.UserType.ENGINEER, User.UserType.ADMIN]
        ).annotate(
            completed_project_count=Count(
                'managed_project_repos',
                filter=Q(managed_project_repos__project__progress_percent=100, managed_project_repos__project__is_terminated=False)
            ),
            inprogress_project_count=Count(
                'managed_project_repos',
                filter=Q(managed_project_repos__project__progress_percent__lt=100, managed_project_repos__project__is_terminated=False)
            ),
            terminated_project_count=Count(
                'managed_project_repos',
                filter=Q(managed_project_repos__project__is_terminated=True)
            )
        ).order_by('-user_level', 'username')
        return qs


class SalespersonDetailView(RepositoryAccessMixin, DetailView):
    """
    业务员/成员详情：
    - 展示特定成员负责的所有项目档案。
    """
    permission_required = 'app_user.view_user'
    model = User
    template_name = 'apps/app_repository/salesperson/salesperson_detail.html'
    context_object_name = 'salesperson'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        member = self.object
        context['page_title'] = f'成员业绩详情: {member.get_full_name() or member.username}'

        # 获取该成员负责的所有项目档案 (作为 salesperson 关联的)
        related_projects_list = ProjectRepository.objects.filter(salesperson=member).select_related(
            'project', 'customer', 'oem'
        ).order_by('-project__created_at')

        paginator = Paginator(related_projects_list, 10)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        # 进度追踪
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
