from django.http import JsonResponse
from django.db.models import Count, Q, Subquery, OuterRef, Exists
from django.shortcuts import render
from django.views import View
from app_panel.mixins import PanelAccessMixin
from app_panel.utils.filters import ProjectStatisticsFilter
from app_project.models import Project, ProjectStage, ProjectNode
from decimal import Decimal

class ProjectStatisticsView(PanelAccessMixin, View):
    """
    项目统计看板：
    - 逻辑：基于节点状态、轮次及异常历史进行 10 维度分类统计。
    """
    permission_required = 'app_project.view_project'

    def get(self, request):
        base_qs = Project.objects.all().select_related('manager', 'manager__department')
        filter_set = ProjectStatisticsFilter(request.GET, queryset=base_qs)
        projects_qs = filter_set.qs

        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
            return self._get_json_stats(projects_qs)

        context = {
            'filter': filter_set,
            'page_title': '项目数据统计中心',
        }
        return render(request, 'apps/app_panel/project_statistics.html', context)

    def _get_json_stats(self, projects_qs):
        total_projects = projects_qs.count()
        
        if total_projects == 0:
            return JsonResponse({'total_projects': 0, 'stats': {}, 'analysis': {}})

        # --- 核心标注逻辑 ---
        def get_last_status_subquery(stage):
            return Subquery(
                ProjectNode.objects.filter(project=OuterRef('pk'), stage=stage)
                .order_by('-order').values('status')[:1]
            )

        annotated_qs = projects_qs.annotate(
            # 异常历史标识：是否存在任何失败的客户小试节点
            has_failed_pilot=Exists(
                ProjectNode.objects.filter(project=OuterRef('pk'), stage=ProjectStage.PILOT, status='FAILED')
            ),
            # 暂停标识：是否存在任何暂停中的节点
            has_paused_node=Exists(
                ProjectNode.objects.filter(project=OuterRef('pk'), status='PAUSED')
            ),
            # 各阶段最后一轮节点的最新状态
            last_rnd_status=get_last_status_subquery(ProjectStage.RND),
            last_pilot_status=get_last_status_subquery(ProjectStage.PILOT),
            last_mid_test_status=get_last_status_subquery(ProjectStage.MID_TEST),
            last_mass_prod_status=get_last_status_subquery(ProjectStage.MASS_PROD),
        )

        active_states = ['PENDING', 'DOING']
        q_rnd_active = Q(last_rnd_status__in=active_states)
        q_rnd_done = Q(last_rnd_status='DONE')
        
        stats = {
            # 1. 终止：出现终止状态的项目 (项目级标志位)
            'terminated': annotated_qs.filter(is_terminated=True).count(),
            
            # 2. 暂停：项目中出现任何处于 PAUSED 状态的节点
            'paused': annotated_qs.filter(is_terminated=False, has_paused_node=True).count(),
            
            # 3. 开发中：最后一轮研发节点未开始/进行中，且从未有过小试失败历史
            'in_development': annotated_qs.filter(
                is_terminated=False, has_paused_node=False, has_failed_pilot=False
            ).filter(q_rnd_active).count(),

            # 4. 一次送样：最后一轮研发节点已完成，且最后一轮小试节点正在进行中，且从未有过小试失败历史
            'first_sample_delivery': annotated_qs.filter(
                is_terminated=False, has_paused_node=False, has_failed_pilot=False
            ).filter(q_rnd_done, last_pilot_status='DOING').count(),

            # 5. 不合格再开发：至少有一个客户小试节点异常，且最后一轮研发节点处于未开始/进行中
            're_development': annotated_qs.filter(
                is_terminated=False, has_paused_node=False, has_failed_pilot=True
            ).filter(q_rnd_active).count(),

            # 6. 已开发未送样：最后一轮研发节点已完成，且最后一轮客户小试节点处于未开始状态 (Pending)
            'developed_not_sampled': annotated_qs.filter(
                is_terminated=False, has_paused_node=False
            ).filter(q_rnd_done, last_pilot_status='PENDING').count(),

            # 7. 多次送样：至少有一个客户小试节点异常，且最后一轮研发节点已完成，且最后一轮小试节点正在进行中
            'multiple_sample_deliveries': annotated_qs.filter(
                is_terminated=False, has_paused_node=False, has_failed_pilot=True
            ).filter(q_rnd_done, last_pilot_status='DOING').count(),

            # 8. 合格待产：最后一轮小试节点已完成，且中试节点尚未开始或正在进行中
            'qualified_awaiting_production': annotated_qs.filter(
                is_terminated=False, has_paused_node=False
            ).filter(last_pilot_status='DONE', last_mid_test_status__in=active_states).count(),

            # 9. 已中试：最后一轮中试节点已完成，且量产意向节点尚未开始或正在进行中
            'mid_test_completed': annotated_qs.filter(
                is_terminated=False, has_paused_node=False
            ).filter(last_mid_test_status='DONE', last_mass_prod_status__in=active_states).count(),

            # 10. 已量产：最后一轮 MASS_PROD (客户量产意向) 节点已完成
            'mass_production_completed': annotated_qs.filter(
                is_terminated=False, has_paused_node=False, last_mass_prod_status='DONE'
            ).count(),
        }

        # --- 分析指标计算 ---
        total_for_rates = total_projects - stats['terminated']
        analysis = {
            # 项目合格率 = (已量产 + 已中试 + 合格待产) / (总项目数 - 终止项目数)
            'pass_rate': float((stats['mass_production_completed'] + stats['mid_test_completed'] + stats['qualified_awaiting_production']) / total_for_rates * 100) if total_for_rates > 0 else 0,
            # 项目量产率 = 已量产 / (总项目数 - 终止项目数)
            'mass_prod_rate': float(stats['mass_production_completed'] / total_for_rates * 100) if total_for_rates > 0 else 0,
            # 项目反馈率 = 至少拥有一个 FEEDBACK (意见) 阶段节点的项目占比
            'feedback_rate': float(projects_qs.filter(nodes__stage=ProjectStage.FEEDBACK).distinct().count() / total_projects * 100) if total_projects > 0 else 0,
            # 项目暂停率 = 处于暂停状态的项目占比
            'pause_rate': float(stats['paused'] / total_projects * 100) if total_projects > 0 else 0,
            # 项目终止率 = 已终止项目占总立项数的比例
            'termination_rate': float(stats['terminated'] / total_projects * 100) if total_projects > 0 else 0,
        }

        return JsonResponse({'total_projects': total_projects, 'stats': stats, 'analysis': analysis})
