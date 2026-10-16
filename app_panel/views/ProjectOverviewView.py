from datetime import timedelta
from collections import defaultdict
from django.db.models import Count, Exists, OuterRef, Q, Subquery
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from app_panel.utils.filters import PanelFilter
from app_project.mixins import ProjectAccessMixin
from app_project.models import Project, ProjectStage, ProjectNode
from app_user.models import WorkGroup

# 与 signals._update_project_current_stage 一致：这些状态不算当前节点
_CLOSED_NODE_STATUSES = ('DONE', 'FAILED', 'FEEDBACK')
# 与 Project.current_active_node 一致：当前节点只从这些状态里按 order 取第一个
_ACTIVE_NODE_STATUSES = ('DOING', 'PENDING', 'PAUSED', 'AWAITING_APPROVAL')


def _current_open_node(project):
    """按 order 取第一个未关闭节点。后面尚未开始的 PENDING 不算当前节点。"""
    for node in sorted(project.nodes.all(), key=lambda n: n.order):
        if node.status not in _CLOSED_NODE_STATUSES:
            return node
    return None


class ProjectOverviewView(ProjectAccessMixin, View):
    """
    项目全景看板：
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
        # 暂停跟项目详情的 status_label 同一口径：未终止、未完成，且当前节点是 PAUSED。
        # 已完成优先于暂停，量产跟踪被暂停的项目仍算已完成，不重复计入。
        current_status = Subquery(
            ProjectNode.objects.filter(
                project=OuterRef('pk'),
                status__in=_ACTIVE_NODE_STATUSES,
            ).order_by('order').values('status')[:1]
        )
        paused_count = (
            projects_qs.filter(is_terminated=False, progress_percent__lt=100)
            .annotate(_current_status=current_status)
            .filter(_current_status='PAUSED')
            .order_by()
            .values('id')
            .distinct()
            .count()
        )
        active_count = max(0, total_all - terminated_count - completed_count - paused_count)
        # 权限查询带了 distinct 和成员关联，模型又默认按 created_at 排序。
        # 聚合前必须清掉排序，否则 GROUP BY 会带上 created_at，同一阶段被拆成多行，
        # 后面用字典按阶段收口时只留下最后一行，数量就会偏少。
        user_count = projects_qs.order_by().values('manager').distinct().count()

        active_qs = projects_qs.filter(is_terminated=False, progress_percent__lt=100)

        # 阶段分布按当前阶段统计全部未终止项目。
        # 进度到 100 后当前阶段是「量产过程跟踪」，不能再用 progress<100
        # 把它们滤掉，也不能把这个阶段排除出分类，否则这些项目不会出现在任何一根柱子上。
        # 客户意见是按需插入的，没有项目落在上面时不占一根空柱。
        stage_data = (
            projects_qs.filter(is_terminated=False)
            .order_by()
            .values('current_stage')
            .annotate(count=Count('id', distinct=True))
        )
        stage_map = {item['current_stage']: item['count'] for item in stage_data}
        stage_counts = {
            label: stage_map.get(code, 0)
            for code, label in ProjectStage.choices
            if code != ProjectStage.FEEDBACK or stage_map.get(code, 0)
        }
        known_codes = {code for code, _ in ProjectStage.choices}
        other_count = sum(count for code, count in stage_map.items() if code not in known_codes)
        if other_count:
            stage_counts['未归类'] = other_count

        # 当前节点：第一个非 DONE/FAILED/FEEDBACK，含 PAUSED、AWAITING_APPROVAL
        current_node_update_subquery = Subquery(
            ProjectNode.objects.filter(project=OuterRef('pk'))
            .exclude(status__in=_CLOSED_NODE_STATUSES)
            .order_by('order')
            .values('updated_at')[:1]
        )
        active_qs_with_time = active_qs.annotate(current_node_updated_at=current_node_update_subquery)

        def _stagnant_items(qs):
            items = []
            for project in qs:
                node = _current_open_node(project)
                if node is None or node.updated_at is None:
                    continue
                items.append({
                    'p': project,
                    'node': node,
                    'days': (now - node.updated_at).days,
                })
            return items

        stagnant_30d = _stagnant_items(
            active_qs_with_time.filter(current_node_updated_at__lt=day_30)
            .select_related('manager').prefetch_related('nodes')
        )
        stagnant_14d = _stagnant_items(
            active_qs_with_time.filter(
                current_node_updated_at__lt=day_14,
                current_node_updated_at__gte=day_30,
            ).select_related('manager').prefetch_related('nodes')
        )

        # 多轮小试：进行中项目里，客户小试最大轮次 >= 2
        pilot_round_subquery = Subquery(
            ProjectNode.objects.filter(project=OuterRef('pk'), stage=ProjectStage.PILOT)
            .order_by('-round')
            .values('round')[:1]
        )
        multi_round_pilot = [
            {'p': project, 'round': project.pilot_round}
            for project in active_qs.annotate(pilot_round=pilot_round_subquery)
            .filter(pilot_round__gte=2)
            .select_related('manager')
        ]

        # --- 成员负载 TOP 10 ---
        top_managers_agg = list(
            active_qs.order_by()
            .values('manager__id', 'manager__username')
            .annotate(project_count=Count('id', distinct=True))
            .order_by('-project_count')[:10]
        )
        manager_ids = [row['manager__id'] for row in top_managers_agg if row['manager__id']]
        projects_by_manager = defaultdict(list)
        if manager_ids:
            for project in (
                active_qs.filter(manager_id__in=manager_ids)
                .only('id', 'name', 'manager_id')
                .order_by('-created_at')
            ):
                bucket = projects_by_manager[project.manager_id]
                if len(bucket) < 3:
                    bucket.append(project)

        member_stats_list = []
        for row in top_managers_agg:
            username = row['manager__username'] or ''
            member_stats_list.append({
                'name': username,
                'avatar': username[0].upper() if username else 'U',
                'project_count': row['project_count'],
                'projects': projects_by_manager.get(row['manager__id'], []),
            })

        # 团队效能按负责人所在的启用工作组汇总。一个人可以在多个组，
        # 他负责的项目会分别计入每个组，不是按部门切一刀。
        def _status_counts():
            return dict(
                total=Count('id', distinct=True),
                active=Count('id', distinct=True, filter=Q(is_terminated=False, progress_percent__lt=100)),
                completed=Count('id', distinct=True, filter=Q(is_terminated=False, progress_percent=100)),
                terminated=Count('id', distinct=True, filter=Q(is_terminated=True)),
            )

        grouped_rows = (
            projects_qs.filter(manager__work_groups__is_active=True)
            .order_by()
            .values('manager__work_groups__name', 'manager__work_groups__department__name')
            .annotate(**_status_counts())
            .order_by('-total')
        )
        group_entries = []
        for row in grouped_rows:
            label = f"[{row['manager__work_groups__department__name']}] {row['manager__work_groups__name']}"
            group_entries.append((label, {
                'total': row['total'],
                'active': row['active'],
                'completed': row['completed'],
                'terminated': row['terminated'],
            }))
        has_active_group = Exists(
            WorkGroup.objects.filter(is_active=True, members=OuterRef('manager_id'))
        )
        ungrouped = projects_qs.annotate(_has_group=has_active_group).filter(_has_group=False).aggregate(**_status_counts())
        if ungrouped['total']:
            group_entries.append(('未分组', ungrouped))
        group_entries.sort(key=lambda item: item[1]['total'], reverse=True)
        group_stats = dict(group_entries)

        warning_rows = []
        for item in multi_round_pilot:
            warning_rows.append({**item, 'kind': 'pilot'})
        for item in stagnant_30d:
            warning_rows.append({**item, 'kind': 'stagnant_30'})
        for item in stagnant_14d:
            warning_rows.append({**item, 'kind': 'stagnant_14'})

        context = {
            'stats': {
                'total_all': total_all,
                'total_active': active_count,
                'total_paused': paused_count,
                # 停滞、多轮小试的分母仍是未完成且未终止，暂停项目也在这个范围内
                'total_unfinished': active_count + paused_count,
                'total_completed': completed_count,
                'total_terminated': terminated_count,
                'stage_counts': stage_counts,
                'stagnant_30d': stagnant_30d,
                'stagnant_14d': stagnant_14d,
                'total_stagnant_count': len(stagnant_30d) + len(stagnant_14d),
                'multi_round_pilot': multi_round_pilot,
                'group_stats': group_stats,
            },
            'user_count': user_count,
            'member_stats_list': member_stats_list,
            'warning_rows': warning_rows,
            'start_date': start_date,
            'end_date': end_date,
            'filter': filter_set,
        }
        return render(request, 'apps/app_panel/project_overview.html', context)

    def get_permitted_queryset(self, qs):
        """兼容 View 模式下的过滤调用"""
        self.queryset = qs
        return self.get_queryset()
