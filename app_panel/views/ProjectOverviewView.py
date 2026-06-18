from datetime import timedelta
from collections import defaultdict
from django.db.models import Count, Q, Max, Subquery, OuterRef
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from app_panel.utils.filters import PanelFilter
from app_project.mixins import ProjectAccessMixin
from app_project.models import Project, ProjectStage, ProjectNode


class ProjectOverviewView(ProjectAccessMixin, View):
    """
    项目全局概览看板：
    - 准入：需有 app_project.view_project 权限。
    - 隔离：继承项目模块的部门隔离逻辑。
    """
    permission_required = 'app_project.view_project'

    def get(self, request):
        # 1. 获取经过权限过滤的基础查询集 (由 ProjectAccessMixin.get_queryset 提供)
        base_qs = Project.objects.all()
        # get_permitted_queryset() 继承 ProjectAccessMixin 的部门+成员隔离
        projects_qs = self.get_permitted_queryset(base_qs)

        # 2. 应用面板过滤器
        filter_set = PanelFilter(request.GET, queryset=projects_qs)
        projects_qs = filter_set.qs

        start_date = request.GET.get('start_date', '')
        end_date = request.GET.get('end_date', '')

        now = timezone.now()
        day_14 = now - timedelta(days=14)
        day_30 = now - timedelta(days=30)

        # --- 数据统计 ---
        total_all = projects_qs.count()
        terminated_count = projects_qs.filter(is_terminated=True).count()
        completed_count = projects_qs.filter(progress_percent=100, is_terminated=False).count()
        active_count = max(0, total_all - terminated_count - completed_count)
        user_count = projects_qs.values('manager').distinct().count()

        active_qs = projects_qs.filter(is_terminated=False, progress_percent__lt=100)

        # 阶段分布
        stage_data = active_qs.values('current_stage').annotate(count=Count('id'))
        stage_map = {item['current_stage']: item['count'] for item in stage_data}
        stage_counts = {label: stage_map.get(code, 0) for code, label in ProjectStage.choices if code != 'FEEDBACK'}

        # --- 风险预警逻辑 ---
        active_node_statuses = ['PENDING', 'DOING']
        current_node_update_subquery = Subquery(
            ProjectNode.objects.filter(
                project=OuterRef('pk'),
                status__in=active_node_statuses
            ).order_by('order').values('updated_at')[:1]
        )
        active_qs_with_time = active_qs.annotate(current_node_updated_at=current_node_update_subquery)

        # 滞后预警
        stagnant_30d_qs = active_qs_with_time.filter(current_node_updated_at__lt=day_30).select_related('manager').prefetch_related('nodes')
        stagnant_30d = [{'p': p, 'days': (now - p.current_node_updated_at).days} for p in stagnant_30d_qs if p.current_node_updated_at]

        stagnant_14d_qs = active_qs_with_time.filter(
            current_node_updated_at__lt=day_14, current_node_updated_at__gte=day_30
        ).select_related('manager').prefetch_related('nodes')
        stagnant_14d = [{'p': p, 'days': (now - p.current_node_updated_at).days} for p in stagnant_14d_qs if p.current_node_updated_at]

        # --- 成员负载 TOP 10 ---
        top_managers_agg = active_qs.values('manager__id', 'manager__username') \
            .annotate(project_count=Count('id')).order_by('-project_count')[:10]

        member_stats_list = []
        for m in top_managers_agg:
            member_stats_list.append({
                'name': m['manager__username'],
                'avatar': m['manager__username'][0].upper() if m['manager__username'] else 'U',
                'project_count': m['project_count']
            })

        # --- 部门统计 ---
        dept_agg = projects_qs.values('manager__department__name') \
            .annotate(
            total=Count('id'),
            active=Count('id', filter=Q(is_terminated=False, progress_percent__lt=100)),
            completed=Count('id', filter=Q(is_terminated=False, progress_percent=100))
        ).order_by('-total')

        context = {
            'stats': {
                'total_all': total_all,
                'total_active': active_count,
                'total_completed': completed_count,
                'total_terminated': terminated_count,
                'stage_counts': stage_counts,
                'stagnant_30d': stagnant_30d,
                'stagnant_14d': stagnant_14d,
                'total_stagnant_count': len(stagnant_30d) + len(stagnant_14d),
            },
            'dept_stats': dept_agg,
            'user_count': user_count,
            'member_stats_list': member_stats_list,
            'start_date': start_date,
            'end_date': end_date,
            'filter': filter_set,
        }
        return render(request, 'apps/app_panel/project_overview.html', context)

    def get_permitted_queryset(self, qs):
        """兼容 View 模式下的过滤调用"""
        self.queryset = qs
        return self.get_queryset()
