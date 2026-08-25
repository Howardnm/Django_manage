from django.shortcuts import render, get_object_or_404
from django.views import View
from django.contrib.auth import get_user_model
from django.db.models import Sum, Count, Max
from app_panel.mixins import PanelAccessMixin
from decimal import Decimal
from app_project.models import (
    ProjectMember,
    ProjectSalesMember,
    ProjectNode,
    ProjectStage,
    MemberScoreSnapshot,
)

User = get_user_model()


def _latest_snapshot_ids(track, project_ids=None, date_before=None):
    """返回「每个 (project, user) 在该轨的最新一条快照」的 id 列表。

    取每组 Max(id)：id 严格递增（Django 自增主键）且快照仅在得分变更时写入、
    幂等去重保证相邻值不同，因此 id 最大者即「最新（当前或截止 date_before）」快照。

    date_before: 给定则只考虑 snapshot_at__date__lte=date_before 之前的快照（用于增量切片）。
    project_ids: 限定的项目集合（可迭代），None 表示不限制。
    """
    qs = MemberScoreSnapshot.objects.filter(track=track)
    if date_before:
        qs = qs.filter(snapshot_at__date__lte=date_before)
    if project_ids is not None:
        qs = qs.filter(project_id__in=project_ids)
    return list(
        qs.values('project_id', 'user_id').annotate(latest=Max('id'))
        .values_list('latest', flat=True)
    )


def _latest_snapshots_qs(track, project_ids=None, date_before=None):
    """返回「每个 (project, user) 在该轨的最新一条快照」的查询集。"""
    ids = _latest_snapshot_ids(track, project_ids, date_before)
    if not ids:
        return MemberScoreSnapshot.objects.none()
    return MemberScoreSnapshot.objects.filter(id__in=ids)


def _aggregate_by_user(qs):
    """把最新快照查询集按 user 聚合出累计分与项目数。"""
    rows = qs.values('user_id').annotate(
        effective_score=Sum('effective_score'),
        workload_score=Sum('workload_score'),
        project_count=Count('project_id', distinct=True),
    )
    result = {}
    for row in rows:
        result[row['user_id']] = {
            'effective_score': row['effective_score'] or Decimal('0.00'),
            'workload_score': row['workload_score'] or Decimal('0.00'),
            'project_count': row['project_count'] or 0,
        }
    return result


def _increment_by_user(qs_start, qs_end):
    """由两个切片（inc_start / inc_end）的最新快照，算出每个 user 的增量。"""
    start_agg = {}
    for row in qs_start.values('user_id').annotate(
        eff=Sum('effective_score'), work=Sum('workload_score'),
    ):
        start_agg[row['user_id']] = (row['eff'] or Decimal('0.00'), row['work'] or Decimal('0.00'))

    result = {}
    for row in qs_end.values('user_id').annotate(
        eff=Sum('effective_score'), work=Sum('workload_score'),
    ):
        uid = row['user_id']
        s_eff, s_work = start_agg.get(uid, (Decimal('0.00'), Decimal('0.00')))
        e_eff = row['eff'] or Decimal('0.00')
        e_work = row['work'] or Decimal('0.00')
        result[uid] = {
            'eff_inc': e_eff - s_eff,
            'work_inc': e_work - s_work,
        }
    return result


class UserPerformanceListView(PanelAccessMixin, View):
    permission_required = 'app_project.view_project'

    def get(self, request):
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        inc_start = request.GET.get('inc_start')
        inc_end = request.GET.get('inc_end')
        sort = request.GET.get('sort', '-effective')
        tab = request.GET.get('tab', 'rd')

        # --- A. 立项日期过滤：限定「立项时间」在区间内的项目集合 ---
        project_ids_in_period = None
        if start_date or end_date:
            node_qs = ProjectNode.objects.filter(stage=ProjectStage.INIT, order=1)
            if start_date:
                node_qs = node_qs.filter(updated_at__date__gte=start_date)
            if end_date:
                node_qs = node_qs.filter(updated_at__date__lte=end_date)
            project_ids_in_period = list(node_qs.values_list('project_id', flat=True))

        reverse = sort.startswith('-')
        sort_key = sort.lstrip('-')
        mapping = {
            'effective': 'effective_score',
            'workload': 'workload_score',
            'inc_eff': 'eff_inc',
            'inc_work': 'work_inc',
        }
        actual_key = mapping.get(sort_key, 'effective_score')

        def build_data(track):
            # 项目过滤为空集时，直接返回空
            if project_ids_in_period is not None and not project_ids_in_period:
                return []

            cumulative = _aggregate_by_user(
                _latest_snapshots_qs(track, project_ids_in_period)
            )

            inc_map = {}
            if inc_start and inc_end:
                inc_map = _increment_by_user(
                    _latest_snapshots_qs(track, project_ids_in_period, inc_start),
                    _latest_snapshots_qs(track, project_ids_in_period, inc_end),
                )

            user_ids = set(cumulative.keys()) | set(inc_map.keys())
            users = {
                u.id: u for u in User.objects.filter(id__in=user_ids).select_related('department')
            }

            data = []
            for uid in user_ids:
                stats = cumulative.get(uid, {
                    'effective_score': Decimal('0.00'),
                    'workload_score': Decimal('0.00'),
                    'project_count': 0,
                })
                inc = inc_map.get(uid, {'eff_inc': Decimal('0.00'), 'work_inc': Decimal('0.00')})
                data.append({
                    'user': users.get(uid),
                    'effective_score': stats['effective_score'],
                    'workload_score': stats['workload_score'],
                    'eff_inc': inc['eff_inc'],
                    'work_inc': inc['work_inc'],
                    'project_count': stats['project_count'],
                })

            data.sort(key=lambda x: x.get(actual_key, 0) or 0, reverse=reverse)
            return data

        rd_data = build_data('RD')
        sales_data = build_data('SALES')

        context = {
            'rd_data': rd_data,
            'sales_data': sales_data,
            'current_tab': tab,
            'page_title': '成员协同绩效看板',
            'current_sort': sort,
            'start_date': start_date, 'end_date': end_date,
            'inc_start': inc_start, 'inc_end': inc_end,
        }
        return render(request, 'apps/app_project/performance/list.html', context)


class UserPerformanceDetailView(PanelAccessMixin, View):
    permission_required = 'app_project.view_project'

    def get(self, request, user_id):
        target_user = get_object_or_404(User, pk=user_id)
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        inc_start = request.GET.get('inc_start')
        inc_end = request.GET.get('inc_end')

        def _filter_projects(queryset):
            if start_date or end_date:
                node_qs = ProjectNode.objects.filter(stage=ProjectStage.INIT, order=1)
                if start_date:
                    node_qs = node_qs.filter(updated_at__date__gte=start_date)
                if end_date:
                    node_qs = node_qs.filter(updated_at__date__lte=end_date)
                queryset = queryset.filter(project_id__in=node_qs.values_list('project_id', flat=True))
            return queryset

        def build_memberships(track, member_model):
            """返回该成员在该轨的明细列表（成员对象 + 快照累计/增量）。"""
            qs = member_model.objects.filter(user=target_user).select_related(
                'project', 'project__grade', 'project__repository__customer'
            )
            qs = _filter_projects(qs).order_by('-project__created_at')
            return qs

        rd_memberships = build_memberships('RD', ProjectMember)
        sales_memberships = build_memberships('SALES', ProjectSalesMember)

        def attach_snapshot_metrics(memberships, track):
            for m in memberships:
                latest = (
                    MemberScoreSnapshot.objects.filter(
                        project=m.project, user=target_user, track=track,
                    ).order_by('-snapshot_at', '-pk').first()
                )
                m.cumulative_eff = latest.effective_score if latest else Decimal('0.00')
                m.cumulative_work = latest.workload_score if latest else Decimal('0.00')

                m.inc_eff = Decimal('0.00')
                m.inc_work = Decimal('0.00')
                if inc_start and inc_end:
                    def _score_at(date_val, col):
                        return (
                            MemberScoreSnapshot.objects.filter(
                                project=m.project, user=target_user, track=track,
                                snapshot_at__date__lte=date_val,
                            ).order_by('-snapshot_at', '-pk').values_list(col, flat=True).first()
                            or Decimal('0.00')
                        )
                    s_eff = _score_at(inc_start, 'effective_score')
                    e_eff = _score_at(inc_end, 'effective_score')
                    s_work = _score_at(inc_start, 'workload_score')
                    e_work = _score_at(inc_end, 'workload_score')
                    m.inc_eff = e_eff - s_eff
                    m.inc_work = e_work - s_work

        attach_snapshot_metrics(rd_memberships, 'RD')
        attach_snapshot_metrics(sales_memberships, 'SALES')

        rd_total_eff = sum((m.cumulative_eff for m in rd_memberships), Decimal('0.00'))
        rd_total_work = sum((m.cumulative_work for m in rd_memberships), Decimal('0.00'))
        sales_total_eff = sum((m.cumulative_eff for m in sales_memberships), Decimal('0.00'))
        sales_total_work = sum((m.cumulative_work for m in sales_memberships), Decimal('0.00'))

        rd_inc_eff = sum((m.inc_eff for m in rd_memberships), Decimal('0.00'))
        rd_inc_work = sum((m.inc_work for m in rd_memberships), Decimal('0.00'))
        sales_inc_eff = sum((m.inc_eff for m in sales_memberships), Decimal('0.00'))
        sales_inc_work = sum((m.inc_work for m in sales_memberships), Decimal('0.00'))

        total_eff = rd_total_eff + sales_total_eff
        total_work = rd_total_work + sales_total_work
        total_inc_eff = rd_inc_eff + sales_inc_eff
        total_inc_work = rd_inc_work + sales_inc_work

        context = {
            'target_user': target_user,
            'rd_memberships': rd_memberships,
            'sales_memberships': sales_memberships,
            'rd_total_eff': rd_total_eff,
            'rd_total_work': rd_total_work,
            'sales_total_eff': sales_total_eff,
            'sales_total_work': sales_total_work,
            'rd_inc_eff': rd_inc_eff,
            'rd_inc_work': rd_inc_work,
            'sales_inc_eff': sales_inc_eff,
            'sales_inc_work': sales_inc_work,
            'total_eff': total_eff,
            'total_work': total_work,
            'total_inc_eff': total_inc_eff,
            'total_inc_work': total_inc_work,
            'project_count': len(rd_memberships) + len(sales_memberships),
            'page_title': f'绩效明细: {target_user.username}',
            'start_date': start_date, 'end_date': end_date,
            'inc_start': inc_start, 'inc_end': inc_end,
        }
        return render(request, 'apps/app_project/performance/detail.html', context)