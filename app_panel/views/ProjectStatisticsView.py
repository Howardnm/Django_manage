from datetime import timedelta
from django.db.models import Count, Q, Subquery, OuterRef, F, Case, When, DecimalField
from django.shortcuts import render
from django.utils import timezone
from django.views import View
from app_panel.mixins import PanelAccessMixin
from app_panel.utils.filters import ProjectStatisticsFilter
from app_project.models import Project, ProjectStage, ProjectNode
from decimal import Decimal

class ProjectStatisticsView(PanelAccessMixin, View):
    """
    项目统计看板：
    - 准入：内部全员 (INTERNAL_STAFF)。
    - 隔离：关闭隔离，显示全公司榜单。
    - 筛选：按立项时间、成员组、成员筛选。
    """
    permission_required = 'app_project.view_project' # 依然需要查看项目权限

    def get(self, request):
        # 1. 获取基础查询集
        # PanelAccessMixin 已经处理了 is_superuser 和 identity_required
        # 对于统计看板，我们通常希望看到全局数据，所以直接从 Project.objects.all() 开始
        base_qs = Project.objects.all().select_related('manager', 'manager__department')

        # 2. 应用过滤器
        filter_set = ProjectStatisticsFilter(request.GET, queryset=base_qs)
        projects_qs = filter_set.qs

        total_projects = projects_qs.count()

        # 如果没有项目，直接返回空数据
        if total_projects == 0:
            context = {
                'filter': filter_set,
                'page_title': '项目统计看板',
                'stats': {},
                'analysis': {},
                'total_projects': 0
            }
            return render(request, 'apps/app_panel/project_statistics.html', context)

        # --- 辅助 Subquery 获取当前活跃节点信息 ---
        # 获取当前活跃节点的 stage, round, status
        current_active_node_info_subquery = ProjectNode.objects.filter(
            project=OuterRef('pk'),
            status__in=['DOING', 'PENDING', 'PAUSED']
        ).order_by('order').values('stage', 'round', 'status')[:1]

        projects_annotated_qs = projects_qs.annotate(
            active_node_stage=Subquery(current_active_node_info_subquery.values('stage')),
            active_node_round=Subquery(current_active_node_info_subquery.values('round')),
            active_node_status=Subquery(current_active_node_info_subquery.values('status')),
        )

        # --- 第一部分：项目数量统计 ---
        stats = {}
        
        # 开发中 (RND阶段，且不是再开发)
        stats['in_development'] = projects_annotated_qs.filter(
            active_node_stage=ProjectStage.RND,
            active_node_round=1,
            is_terminated=False,
            progress_percent__lt=100
        ).count()

        # 一次送样 (PILOT阶段，且是第一轮)
        stats['first_sample_delivery'] = projects_annotated_qs.filter(
            active_node_stage=ProjectStage.PILOT,
            active_node_round=1,
            is_terminated=False,
            progress_percent__lt=100
        ).count()

        # 不合格再开发 (RND阶段，且轮次大于1)
        stats['re_development'] = projects_annotated_qs.filter(
            active_node_stage=ProjectStage.RND,
            active_node_round__gt=1,
            is_terminated=False,
            progress_percent__lt=100
        ).count()

        # 多次送样 (PILOT阶段，且轮次大于1)
        stats['multiple_sample_deliveries'] = projects_annotated_qs.filter(
            active_node_stage=ProjectStage.PILOT,
            active_node_round__gt=1,
            is_terminated=False,
            progress_percent__lt=100
        ).count()

        # 合格待产 (MASS_PROD阶段，未终止，未完成)
        stats['qualified_awaiting_production'] = projects_annotated_qs.filter(
            current_stage=ProjectStage.MASS_PROD,
            is_terminated=False,
            progress_percent__lt=100
        ).count()

        # 已中试 (MID_TEST阶段已完成，当前阶段为ORDER，未终止，未完成)
        # 这里的定义是“中试已完成”，即当前阶段是ORDER，但项目未完全结束
        stats['mid_test_completed'] = projects_annotated_qs.filter(
            current_stage=ProjectStage.ORDER, # 假设进入ORDER阶段表示中试已完成
            is_terminated=False,
            progress_percent__lt=100
        ).count()

        # 已量产 (项目进度100%，未终止)
        stats['mass_production_completed'] = projects_annotated_qs.filter(
            progress_percent=100,
            is_terminated=False
        ).count()

        # 暂停 (当前活跃节点状态为PAUSED)
        stats['paused'] = projects_annotated_qs.filter(
            active_node_status='PAUSED'
        ).count()

        # 终止 (项目已终止)
        stats['terminated'] = projects_annotated_qs.filter(
            is_terminated=True
        ).count()

        # --- 第二部分：项目数据分析 ---
        analysis = {}
        
        # 项目合格率 = (已量产 + 已中试 + 合格待产) / (总项目数 - 终止项目数)
        # 避免除零错误
        total_for_pass_rate = total_projects - stats['terminated']
        if total_for_pass_rate > 0:
            analysis['pass_rate'] = (
                stats['mass_production_completed'] + 
                stats['mid_test_completed'] + 
                stats['qualified_awaiting_production']
            ) / total_for_pass_rate * 100
        else:
            analysis['pass_rate'] = Decimal('0.00')

        # 项目量产率 = 已量产 / (总项目数 - 终止项目数)
        if total_for_pass_rate > 0:
            analysis['mass_prod_rate'] = stats['mass_production_completed'] / total_for_pass_rate * 100
        else:
            analysis['mass_prod_rate'] = Decimal('0.00')

        # 项目反馈率 = 至少有一个FEEDBACK节点的项目数 / 总项目数
        projects_with_feedback = projects_qs.filter(nodes__stage=ProjectStage.FEEDBACK).distinct().count()
        if total_projects > 0:
            analysis['feedback_rate'] = projects_with_feedback / total_projects * 100
        else:
            analysis['feedback_rate'] = Decimal('0.00')

        # 项目暂停率 = 暂停项目数 / 总项目数
        if total_projects > 0:
            analysis['pause_rate'] = stats['paused'] / total_projects * 100
        else:
            analysis['pause_rate'] = Decimal('0.00')

        # 项目终止率 = 终止项目数 / 总项目数
        if total_projects > 0:
            analysis['termination_rate'] = stats['terminated'] / total_projects * 100
        else:
            analysis['termination_rate'] = Decimal('0.00')

        context = {
            'filter': filter_set,
            'page_title': '项目统计看板',
            'stats': stats,
            'analysis': analysis,
            'total_projects': total_projects
        }
        return render(request, 'apps/app_panel/project_statistics.html', context)
