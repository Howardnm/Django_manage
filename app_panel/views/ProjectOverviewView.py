from datetime import timedelta
from collections import defaultdict

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q, Max, Subquery, OuterRef, Prefetch
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from app_panel.utils.filters import PanelFilter
from app_project.mixins import ProjectPermissionMixin
from app_panel.mixins import CustomPermissionRequiredMixin
from app_project.models import Project, ProjectStage, ProjectNode


class ProjectOverviewView(LoginRequiredMixin, CustomPermissionRequiredMixin, ProjectPermissionMixin, View):
    permission_required = 'app_project.view_project'

    def get(self, request):
        base_qs = Project.objects.all()
        projects_qs = self.get_permitted_queryset(base_qs)

        filter_set = PanelFilter(request.GET, queryset=projects_qs)
        projects_qs = filter_set.qs

        start_date = request.GET.get('start_date', '')
        end_date = request.GET.get('end_date', '')

        now = timezone.now()
        day_14 = now - timedelta(days=14)
        day_30 = now - timedelta(days=30)

        total_all = projects_qs.count()
        terminated_count = projects_qs.filter(is_terminated=True).count()
        completed_count = projects_qs.filter(progress_percent=100, is_terminated=False).count()
        active_count = total_all - terminated_count - completed_count
        if active_count < 0: active_count = 0
        user_count = projects_qs.values('manager').distinct().count()

        active_qs = projects_qs.filter(is_terminated=False, progress_percent__lt=100)

        stage_data = active_qs.values('current_stage').annotate(count=Count('id'))
        stage_map = {item['current_stage']: item['count'] for item in stage_data}
        stage_counts = {label: stage_map.get(code, 0) for code, label in ProjectStage.choices if code != 'FEEDBACK'}

        # =========================================================
        # 4. 风险预警 (【N+1 修复】添加 prefetch_related)
        # =========================================================
        active_node_statuses = ['PENDING', 'DOING']

        current_node_update_subquery = Subquery(
            ProjectNode.objects.filter(
                project=OuterRef('pk'),
                status__in=active_node_statuses
            ).order_by('order').values('updated_at')[:1]
        )

        active_qs_with_current_node_time = active_qs.annotate(
            current_node_updated_at=current_node_update_subquery
        )

        # A. 滞后 30 天 (严重)
        stagnant_30d_qs = active_qs_with_current_node_time.filter(
            current_node_updated_at__lt=day_30
        ).select_related('manager').prefetch_related('nodes').distinct() # 【N+1 修复】

        stagnant_30d = []
        for p in stagnant_30d_qs:
            node = p.nodes.filter(status__in=active_node_statuses).order_by('order').first()
            if node:
                days = (now - node.updated_at).days
                stagnant_30d.append({'p': p, 'days': days, 'node': node})

        # B. 滞后 14 天 (中度)
        stagnant_14d_qs = active_qs_with_current_node_time.filter(
            current_node_updated_at__lt=day_14,
            current_node_updated_at__gte=day_30
        ).select_related('manager').prefetch_related('nodes').distinct() # 【N+1 修复】

        stagnant_14d = []
        for p in stagnant_14d_qs:
            node = p.nodes.filter(status__in=active_node_statuses).order_by('order').first()
            if node:
                days = (now - node.updated_at).days
                stagnant_14d.append({'p': p, 'days': days, 'node': node})

        # C. 多轮小试 (逻辑不变)
        multi_round_raw = active_qs.filter(
            nodes__stage='PILOT',
            nodes__round__gt=1
        ).select_related('manager').prefetch_related('nodes').distinct()[:10] # 【N+1 修复】

        multi_round_pilot = []
        for p in multi_round_raw:
            node = p.nodes.filter(stage='PILOT', round__gt=1).order_by('-round').first()
            if node:
                multi_round_pilot.append({'p': p, 'round': node.round})

        # =========================================================
        # 5. 成员负载 TOP 10 (已优化)
        # =========================================================
        top_managers_agg = active_qs.values('manager__id', 'manager__username') \
            .annotate(project_count=Count('id')) \
            .order_by('-project_count')[:10]

        top_manager_ids = [m['manager__id'] for m in top_managers_agg]

        all_projects_for_top_managers = active_qs.filter(manager__id__in=top_manager_ids) \
            .annotate(latest_node_update=Max('nodes__updated_at')) \
            .order_by('manager_id', '-latest_node_update') \
            .values('id', 'name', 'manager_id')

        projects_by_manager = defaultdict(list)
        for p in all_projects_for_top_managers:
            projects_by_manager[p['manager_id']].append({'id': p['id'], 'name': p['name']})

        member_stats_list = []
        for m in top_managers_agg:
            manager_id = m['manager__id']
            member_stats_list.append({
                'name': m['manager__username'],
                'avatar': m['manager__username'][0].upper() if m['manager__username'] else 'U',
                'project_count': m['project_count'],
                'projects': projects_by_manager.get(manager_id, [])
            })

        # =========================================================
        # 6. 组统计 (已优化)
        # =========================================================
        group_agg = projects_qs.values('manager__groups__name') \
            .annotate(
            total=Count('id'),
            active=Count('id', filter=Q(is_terminated=False, progress_percent__lt=100)),
            terminated=Count('id', filter=Q(is_terminated=True)),
            completed=Count('id', filter=Q(is_terminated=False, progress_percent=100))
        ).order_by('-total')

        group_stats = {
            g['manager__groups__name'] or '未分组': {
                'total': g['total'],
                'active': g['active'],
                'terminated': g['terminated'],
                'completed': g['completed']
            } for g in group_agg
        }

        stats = {
            'total_all': total_all,
            'total_active': active_count,
            'total_completed': completed_count,
            'total_terminated': terminated_count,
            'stage_counts': stage_counts,
            'stagnant_30d': stagnant_30d,
            'stagnant_14d': stagnant_14d,
            'total_stagnant_count': len(stagnant_30d) + len(stagnant_14d), # 【后端计算】
            'multi_round_pilot': multi_round_pilot,
            'group_stats': group_stats,
        }

        context = {
            'stats': stats,
            'user_count': user_count,
            'member_stats_list': member_stats_list,
            'start_date': start_date,
            'end_date': end_date,
            'filter': filter_set,
        }
        return render(request, 'apps/app_panel/project_overview.html', context)
