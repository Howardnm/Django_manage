from django.shortcuts import render, get_object_or_404
from django.views import View
from django.contrib.auth import get_user_model
from django.db.models import Sum, F, DecimalField, ExpressionWrapper, Q, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from app_panel.mixins import PanelAccessMixin
from decimal import Decimal
from app_project.models import ProjectMember, ProjectNode, ProjectStage

User = get_user_model()

class UserPerformanceListView(PanelAccessMixin, View):
    """
    【增量增强版】全局成员绩效看板视图：
    1. 立项日期筛选：过滤特定时间内立项的项目。
    2. 增量统计区间：计算特定时间内得分的增长情况（快照对比法）。
    """
    def get(self, request):
        # 参数获取
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        inc_start = request.GET.get('inc_start')
        inc_end = request.GET.get('inc_end')
        sort = request.GET.get('sort', '-effective')

        # --- A. 处理立项日期过滤条件 ---
        project_ids_in_period = None
        if start_date or end_date:
            node_qs = ProjectNode.objects.filter(stage=ProjectStage.INIT, order=1)
            if start_date: node_qs = node_qs.filter(updated_at__date__gte=start_date)
            if end_date: node_qs = node_qs.filter(updated_at__date__lte=end_date)
            project_ids_in_period = node_qs.values_list('project_id', flat=True)

        cumulative_filter = Q()
        if project_ids_in_period is not None:
            cumulative_filter = Q(projectmember__project_id__in=project_ids_in_period)

        # --- B. 基础聚合查询 ---
        user_stats = User.objects.filter(is_active=True).annotate(
            effective_score=Coalesce(Sum(
                ExpressionWrapper(
                    (F('projectmember__project__quality_score') * F('projectmember__workload_share') / 100.0) * 
                    Coalesce(F('projectmember__project__grade__factor'), 1.0, output_field=DecimalField()),
                    output_field=DecimalField()
                ), filter=cumulative_filter), 0.00, output_field=DecimalField()),
            workload_score=Coalesce(Sum(
                ExpressionWrapper(
                    F('projectmember__project__quality_score') * F('projectmember__workload_share') / 100.0,
                    output_field=DecimalField()
                ), filter=cumulative_filter), 0.00, output_field=DecimalField())
        )

        # --- C. 处理得分增量逻辑 ---
        inc_data_map = {}
        if inc_start and inc_end:
            def get_snapshot_subquery(date_val):
                return Subquery(
                    ProjectNode.objects.filter(
                        project=OuterRef('project_id'),
                        updated_at__date__lte=date_val,
                        status__in=['DONE', 'FAILED', 'TERMINATED']
                    ).order_by('-order').values('final_score')[:1]
                )

            member_incs = ProjectMember.objects.annotate(
                s_start=Coalesce(get_snapshot_subquery(inc_start), 0.00, output_field=DecimalField()),
                s_end=Coalesce(get_snapshot_subquery(inc_end), 0.00, output_field=DecimalField()),
                factor=Coalesce(F('project__grade__factor'), 1.0, output_field=DecimalField())
            ).annotate(
                diff_eff=ExpressionWrapper((F('s_end') - F('s_start')) * F('workload_share') / 100.0 * F('factor'), output_field=DecimalField()),
                diff_work=ExpressionWrapper((F('s_end') - F('s_start')) * F('workload_share') / 100.0, output_field=DecimalField())
            ).values('user_id').annotate(
                total_inc_eff=Sum('diff_eff'),
                total_inc_work=Sum('diff_work')
            )
            inc_data_map = {item['user_id']: item for item in member_incs}

        # --- D. 组装数据 ---
        performance_data = []
        for user in user_stats:
            inc_info = inc_data_map.get(user.id, {})
            eff_inc = inc_info.get('total_inc_eff', Decimal('0.00')) or Decimal('0.00')
            work_inc = inc_info.get('total_inc_work', Decimal('0.00')) or Decimal('0.00')

            if user.effective_score > 0 or user.workload_score > 0 or eff_inc != 0:
                m_count = user.projectmember_set.all()
                if project_ids_in_period is not None:
                    m_count = m_count.filter(project_id__in=project_ids_in_period)

                performance_data.append({
                    'user': user,
                    'effective_score': user.effective_score,
                    'workload_score': user.workload_score,
                    'eff_inc': eff_inc,
                    'work_inc': work_inc, # 这里的键名是 work_inc
                    'project_count': m_count.count(),
                })

        # --- E. 修正排序逻辑 ---
        reverse = sort.startswith('-')
        sort_key = sort.lstrip('-')
        mapping = {
            'effective': 'effective_score',
            'workload': 'workload_score',
            'inc_eff': 'eff_inc',
            'inc_work': 'work_inc' # 核心修复：确保此处指向正确的字典键名
        }
        actual_key = mapping.get(sort_key, 'effective_score')
        performance_data.sort(key=lambda x: x.get(actual_key, 0), reverse=reverse)

        context = {
            'performance_data': performance_data,
            'page_title': '成员协同绩效看板',
            'current_sort': sort,
            'start_date': start_date, 'end_date': end_date,
            'inc_start': inc_start, 'inc_end': inc_end,
        }
        return render(request, 'apps/app_project/performance/list.html', context)


class UserPerformanceDetailView(PanelAccessMixin, View):
    """成员绩效明细页面"""
    def get(self, request, user_id):
        target_user = get_object_or_404(User, pk=user_id)
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        inc_start = request.GET.get('inc_start')
        inc_end = request.GET.get('inc_end')
        
        memberships = ProjectMember.objects.filter(user=target_user).select_related(
            'project', 'project__grade', 'project__repository__customer'
        )

        if start_date or end_date:
            node_qs = ProjectNode.objects.filter(stage=ProjectStage.INIT, order=1)
            if start_date: node_qs = node_qs.filter(updated_at__date__gte=start_date)
            if end_date: node_qs = node_qs.filter(updated_at__date__lte=end_date)
            memberships = memberships.filter(project_id__in=node_qs.values_list('project_id', flat=True))

        memberships = memberships.annotate(
            cumulative_eff=ExpressionWrapper((F('project__quality_score') * F('workload_share') / 100.0) * Coalesce(F('project__grade__factor'), 1.0, output_field=DecimalField()), output_field=DecimalField()),
            cumulative_work=ExpressionWrapper(F('project__quality_score') * F('workload_share') / 100.0, output_field=DecimalField()),
        )

        if inc_start and inc_end:
            def get_snapshot_subquery(date_val):
                return Subquery(
                    ProjectNode.objects.filter(project=OuterRef('project_id'), updated_at__date__lte=date_val, status__in=['DONE', 'FAILED', 'TERMINATED'])
                    .order_by('-order').values('final_score')[:1]
                )

            memberships = memberships.annotate(
                s_start=Coalesce(get_snapshot_subquery(inc_start), 0.00, output_field=DecimalField()),
                s_end=Coalesce(get_snapshot_subquery(inc_end), 0.00, output_field=DecimalField()),
                factor=Coalesce(F('project__grade__factor'), 1.0, output_field=DecimalField())
            ).annotate(
                inc_eff=ExpressionWrapper((F('s_end') - F('s_start')) * F('workload_share') / 100.0 * F('factor'), output_field=DecimalField()),
                inc_work=ExpressionWrapper((F('s_end') - F('s_start')) * F('workload_share') / 100.0, output_field=DecimalField())
            )
        else:
            memberships = memberships.annotate(
                inc_eff=Value(0.00, output_field=DecimalField()),
                inc_work=Value(0.00, output_field=DecimalField())
            )

        memberships = memberships.order_by('-project__created_at')

        context = {
            'target_user': target_user,
            'memberships': memberships,
            'total_effective': sum(m.cumulative_eff for m in memberships),
            'total_workload': sum(m.cumulative_work for m in memberships),
            'total_inc_eff': sum(m.inc_eff for m in memberships) if inc_start and inc_end else 0,
            'total_inc_work': sum(m.inc_work for m in memberships) if inc_start and inc_end else 0,
            'page_title': f'绩效明细: {target_user.username}',
            'start_date': start_date, 'end_date': end_date,
            'inc_start': inc_start, 'inc_end': inc_end,
        }
        return render(request, 'apps/app_project/performance/detail.html', context)
