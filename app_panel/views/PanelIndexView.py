from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from app_panel.utils.filters import PanelFilter
from app_project.mixins import ProjectPermissionMixin
from app_project.models import Project, ProjectStage


class PanelIndexView(LoginRequiredMixin, ProjectPermissionMixin, View):
    def get(self, request):
        # 1. 获取基础 QuerySet (权限过滤)
        base_qs = Project.objects.all()
        projects_qs = self.get_permitted_queryset(base_qs)

        # 使用 FilterSet 处理筛选 (日期 + 用户组)
        filter_set = PanelFilter(request.GET, queryset=projects_qs)
        projects_qs = filter_set.qs

        # 获取筛选参数回填
        start_date = request.GET.get('start_date', '')
        end_date = request.GET.get('end_date', '')

        now = timezone.now()
        day_14 = now - timedelta(days=14)
        day_30 = now - timedelta(days=30)

        # =========================================================
        # 2. 全局数字统计 (【优化】直接使用 Project 冗余字段)
        # =========================================================
        # 总数
        total_all = projects_qs.count()

        # 统计已终止项目
        terminated_count = projects_qs.filter(is_terminated=True).count()

        # 统计已完成项目 (进度100%且未终止)
        completed_count = projects_qs.filter(progress_percent=100, is_terminated=False).count()

        # 统计活跃项目 (未终止且未完成)
        active_count = total_all - terminated_count - completed_count
        if active_count < 0: active_count = 0

        # 用户总数
        user_count = projects_qs.values('manager').distinct().count()

        # =========================================================
        # 3. 阶段分布统计 (【优化】直接聚合 current_stage)
        # =========================================================
        # 只统计活跃项目 (未终止且未完成)
        active_qs = projects_qs.filter(is_terminated=False, progress_percent__lt=100)

        stage_data = active_qs.values('current_stage').annotate(count=Count('id'))
        stage_map = {item['current_stage']: item['count'] for item in stage_data}

        stage_counts = {}
        for code, label in ProjectStage.choices:
            if code != 'FEEDBACK':
                stage_counts[label] = stage_map.get(code, 0)

        # =========================================================
        # 4. 风险预警 (依然需要查 Nodes，但先通过 Project 缩小范围)
        # =========================================================

        # A. 滞后 30 天 (严重)
        # 逻辑：项目未结束，且当前活跃节点的更新时间早于30天前
        stagnant_30d_raw = active_qs.filter(
            nodes__status='DOING',
            nodes__updated_at__lt=day_30
        ).select_related('manager').distinct()[:10]

        stagnant_30d = []
        for p in stagnant_30d_raw:
            # 获取该项目当前卡住的节点
            node = p.nodes.filter(status='DOING').first()
            if node:
                days = (now - node.updated_at).days
                stagnant_30d.append({'p': p, 'days': days, 'node': node})

        # B. 滞后 14 天 (中度)
        stagnant_14d_raw = active_qs.filter(
            nodes__status='DOING',
            nodes__updated_at__lt=day_14,
            nodes__updated_at__gte=day_30
        ).select_related('manager').distinct()[:10]

        stagnant_14d = []
        for p in stagnant_14d_raw:
            node = p.nodes.filter(status='DOING').first()
            if node:
                days = (now - node.updated_at).days
                stagnant_14d.append({'p': p, 'days': days, 'node': node})

        # C. 多轮小试 (修改逻辑)
        # 筛选条件：
        # 1. 项目必须是活跃的 (active_qs 已经保证了 is_terminated=False, progress_percent<100)
        # 2. 存在 round > 1 的 PILOT 节点 (无论该节点状态如何)
        multi_round_raw = active_qs.filter(
            nodes__stage='PILOT',
            nodes__round__gt=1
        ).select_related('manager').distinct()[:10]

        multi_round_pilot = []
        for p in multi_round_raw:
            # 找到那个轮次最大的 PILOT 节点，用于展示
            # 注意：这里不再限制 status='DOING'，而是找 round > 1 的
            node = p.nodes.filter(stage='PILOT', round__gt=1).order_by('-round').first()
            if node:
                multi_round_pilot.append({'p': p, 'round': node.round})

        # =========================================================
        # 5. 成员负载 TOP 10 (【优化】直接聚合 Project)
        # =========================================================
        # 统计每个经理手头有多少个活跃项目
        member_agg = active_qs.values('manager__id', 'manager__username') \
            .annotate(project_count=Count('id')) \
            .order_by('-project_count')[:10]

        member_stats_list = []
        for m in member_agg:
            member_stats_list.append({
                'name': m['manager__username'],
                'avatar': m['manager__username'][0].upper() if m['manager__username'] else 'U',
                'project_count': m['project_count'],
                'projects': []
            })

        # =========================================================
        # 6. 组统计 (【优化】直接聚合 Project)
        # =========================================================
        group_agg = projects_qs.values('manager__groups__name') \
            .annotate(
            total=Count('id'),
            active=Count('id', filter=Q(is_terminated=False, progress_percent__lt=100)),
            terminated=Count('id', filter=Q(is_terminated=True)),
            completed=Count('id', filter=Q(is_terminated=False, progress_percent=100))
        ).order_by('-total')

        group_stats = {}
        for g in group_agg:
            group_name = g['manager__groups__name'] or '未分组'
            group_stats[group_name] = {
                'total': g['total'],
                'active': g['active'],
                'terminated': g['terminated'],
                'completed': g['completed']
            }

        stats = {
            'total_all': total_all,
            'total_active': active_count,
            'total_completed': completed_count,
            'total_terminated': terminated_count,
            'stage_counts': stage_counts,
            'stagnant_30d': stagnant_30d,
            'stagnant_14d': stagnant_14d,
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
        return render(request, 'apps/app_panel/index.html', context)
