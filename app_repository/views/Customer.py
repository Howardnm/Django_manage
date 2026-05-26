from django.core.paginator import Paginator
from django.db.models import Max, Count, Q, Sum, F, ExpressionWrapper, DecimalField
from django.db.models.functions import Coalesce
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
    
    # 客户库通常对内部全员公开，关闭自动隔离
    enforce_dept_isolation = False

    def get_queryset(self):
        # 优化：通过 prefetch_related 带出公司的联系人(User)
        qs = super().get_queryset().prefetch_related('members').annotate(
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
    """新增客户公司"""
    permission_required = 'app_repository.add_customer'
    model = Customer
    form_class = CustomerForm
    template_name = 'apps/app_repository/form_generic.html'
    success_url = reverse_lazy('repo_customer_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增客户公司'
        return context


class CustomerUpdateView(RepositoryAccessMixin, UpdateView):
    """编辑客户公司"""
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
    """客户详情：增加了"联系人列表"和"关联项目"的联动展示"""
    permission_required = 'app_repository.view_customer'
    model = Customer
    template_name = 'apps/app_repository/customer/customer_detail.html'
    context_object_name = 'customer'

    def get_queryset(self):
        # 预加载成员信息
        return super().get_queryset().prefetch_related('members')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'客户详情: {self.object.company_name}'

        # 1. 提取关联的系统账号 (联系人)
        context['contacts'] = self.object.members.all().order_by('username')

        # 2. 获取所有关联的项目档案
        related_projects_list = ProjectRepository.objects.filter(
            customer=self.object
        ).select_related('project', 'oem', 'salesperson', 'project__grade').order_by('-project__created_at')

        # 3. 分页逻辑
        paginator = Paginator(related_projects_list, 10)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        # 4. 进度追踪
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


# ==========================================
# 5. 客户公司评分排行视图 (新增)
# ==========================================
class CustomerRankingView(RepositoryAccessMixin, ListView):
    """
    客户评分排行榜：
    评分逻辑 = SUM(项目等级因子 * (项目质量分 / 100)) / SUM(项目等级因子)
    """
    permission_required = 'app_repository.view_customer'
    model = Customer
    template_name = 'apps/app_repository/customer/customer_ranking.html'
    context_object_name = 'rankings'

    def get_queryset(self):
        """
        核心加权平均评分逻辑：
        1. 关联 ProjectRepository -> Project -> GradeFactor
        2. 计算加权得分和：SUM(Coalesce(Factor, 1.0) * (Quality Score / 100.0))
        3. 计算权重因子和：SUM(Coalesce(Factor, 1.0))
        4. 结果 = 分子 / 分母
        """
        return Customer.objects.annotate(
            # 分子：加权得分总和 (处理 null 等级默认为 1.0 因子)
            weighted_points_sum=Coalesce(
                Sum(
                    ExpressionWrapper(
                        Coalesce(F('projectrepository__project__grade__factor'), 1.0, output_field=DecimalField()) * 
                        F('projectrepository__project__quality_score') / 100.0,
                        output_field=DecimalField()
                    )
                ),
                0.00,
                output_field=DecimalField()
            ),
            # 分母：因子权重总和
            weight_factors_sum=Coalesce(
                Sum(
                    Coalesce(F('projectrepository__project__grade__factor'), 1.0, output_field=DecimalField())
                ),
                1.00,
                output_field=DecimalField()
            ),
            project_count=Count('projectrepository')
        ).annotate(
            # 最终得分 = 加权平均
            total_weighted_score=ExpressionWrapper(
                F('weighted_points_sum') / F('weight_factors_sum'),
                output_field=DecimalField()
            )
        ).filter(project_count__gt=0).order_by('-total_weighted_score')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '客户合作质量排行榜'
        return context
