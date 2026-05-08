from django.shortcuts import render, get_object_or_404
from django.views import View
from django.contrib.auth import get_user_model
from django.db.models import Sum, F, DecimalField, ExpressionWrapper, Q, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from app_panel.mixins import PanelAccessMixin
from decimal import Decimal
from app_project.models import ProjectMember, ProjectSalesMember, ProjectNode, ProjectStage

User = get_user_model()

class UserPerformanceListView(PanelAccessMixin, View):
    def get(self, request):
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        inc_start = request.GET.get('inc_start')
        inc_end = request.GET.get('inc_end')
        sort = request.GET.get('sort', '-effective')
        tab = request.GET.get('tab', 'rd')

        # --- A. 立项日期过滤条件 ---
        project_ids_in_period = None
        if start_date or end_date:
            node_qs = ProjectNode.objects.filter(stage=ProjectStage.INIT, order=1)
            if start_date: node_qs = node_qs.filter(updated_at__date__gte=start_date)
            if end_date: node_qs = node_qs.filter(updated_at__date__lte=end_date)
            project_ids_in_period = node_qs.values_list('project_id', flat=True)

        def build_data(member_model, member_rel, score_field='quality_score', node_score_field='final_score'):
            """统一聚合逻辑：score_field 区分研发(quality_score)和销售(sales_quality_score)"""
            cumulative_filter = Q()
            if project_ids_in_period is not None:
                cumulative_filter = Q(**{f'{member_rel}__project_id__in': project_ids_in_period})

            member_q = f'{member_rel}__project__{score_field}'
            workload_q = f'{member_rel}__workload_share'
            factor_q = f'{member_rel}__project__grade__factor'

            user_stats = User.objects.filter(is_active=True).annotate(
                effective_score=Coalesce(Sum(
                    ExpressionWrapper(
                        (F(member_q) * F(workload_q) / 100.0) *
                        Coalesce(F(factor_q), 1.0, output_field=DecimalField()),
                        output_field=DecimalField()
                    ), filter=cumulative_filter), 0.00, output_field=DecimalField()),
                workload_score=Coalesce(Sum(
                    ExpressionWrapper(
                        F(member_q) * F(workload_q) / 100.0,
                        output_field=DecimalField()
                    ), filter=cumulative_filter), 0.00, output_field=DecimalField())
            )

            inc_data_map = {}
            if inc_start and inc_end:
                def get_snapshot_subquery(date_val):
                    return Subquery(
                        ProjectNode.objects.filter(
                            project=OuterRef('project_id'),
                            updated_at__date__lte=date_val,
                            status__in=['DONE', 'FAILED', 'TERMINATED']
                        ).order_by('-order').values(node_score_field)[:1]
                    )

                member_incs = member_model.objects.annotate(
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

            data = []
            for user in user_stats:
                inc_info = inc_data_map.get(user.id, {})
                eff_inc = inc_info.get('total_inc_eff', Decimal('0.00')) or Decimal('0.00')
                work_inc = inc_info.get('total_inc_work', Decimal('0.00')) or Decimal('0.00')

                if user.effective_score > 0 or user.workload_score > 0 or eff_inc != 0:
                    m_count = getattr(user, f'{member_rel}_set').all()
                    if project_ids_in_period is not None:
                        m_count = m_count.filter(project_id__in=project_ids_in_period)

                    data.append({
                        'user': user,
                        'effective_score': user.effective_score,
                        'workload_score': user.workload_score,
                        'eff_inc': eff_inc,
                        'work_inc': work_inc,
                        'project_count': m_count.count(),
                    })

            reverse = sort.startswith('-')
            sort_key = sort.lstrip('-')
            mapping = {
                'effective': 'effective_score',
                'workload': 'workload_score',
                'inc_eff': 'eff_inc',
                'inc_work': 'work_inc',
            }
            actual_key = mapping.get(sort_key, 'effective_score')
            data.sort(key=lambda x: x.get(actual_key, 0), reverse=reverse)
            return data

        rd_data = build_data(ProjectMember, 'projectmember')
        sales_data = build_data(ProjectSalesMember, 'projectsalesmember', 'sales_quality_score', 'sales_final_score')

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
    def get(self, request, user_id):
        target_user = get_object_or_404(User, pk=user_id)
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        inc_start = request.GET.get('inc_start')
        inc_end = request.GET.get('inc_end')

        def build_memberships(member_model, score_field='quality_score', node_score_field='final_score'):
            qs = member_model.objects.filter(user=target_user).select_related(
                'project', 'project__grade', 'project__repository__customer'
            )

            if start_date or end_date:
                node_qs = ProjectNode.objects.filter(stage=ProjectStage.INIT, order=1)
                if start_date: node_qs = node_qs.filter(updated_at__date__gte=start_date)
                if end_date: node_qs = node_qs.filter(updated_at__date__lte=end_date)
                qs = qs.filter(project_id__in=node_qs.values_list('project_id', flat=True))

            qs = qs.annotate(
                cumulative_eff=ExpressionWrapper((F(f'project__{score_field}') * F('workload_share') / 100.0) * Coalesce(F('project__grade__factor'), 1.0, output_field=DecimalField()), output_field=DecimalField()),
                cumulative_work=ExpressionWrapper(F(f'project__{score_field}') * F('workload_share') / 100.0, output_field=DecimalField()),
            )

            if inc_start and inc_end:
                def get_snapshot_subquery(date_val):
                    return Subquery(
                        ProjectNode.objects.filter(project=OuterRef('project_id'), updated_at__date__lte=date_val, status__in=['DONE', 'FAILED', 'TERMINATED'])
                        .order_by('-order').values(node_score_field)[:1]
                    )

                qs = qs.annotate(
                    s_start=Coalesce(get_snapshot_subquery(inc_start), 0.00, output_field=DecimalField()),
                    s_end=Coalesce(get_snapshot_subquery(inc_end), 0.00, output_field=DecimalField()),
                    factor=Coalesce(F('project__grade__factor'), 1.0, output_field=DecimalField())
                ).annotate(
                    inc_eff=ExpressionWrapper((F('s_end') - F('s_start')) * F('workload_share') / 100.0 * F('factor'), output_field=DecimalField()),
                    inc_work=ExpressionWrapper((F('s_end') - F('s_start')) * F('workload_share') / 100.0, output_field=DecimalField())
                )
            else:
                qs = qs.annotate(
                    inc_eff=Value(0.00, output_field=DecimalField()),
                    inc_work=Value(0.00, output_field=DecimalField())
                )

            return qs.order_by('-project__created_at')

        rd_memberships = build_memberships(ProjectMember)
        sales_memberships = build_memberships(ProjectSalesMember, 'sales_quality_score', 'sales_final_score')

        rd_total_eff = sum(m.cumulative_eff for m in rd_memberships)
        rd_total_work = sum(m.cumulative_work for m in rd_memberships)
        sales_total_eff = sum(m.cumulative_eff for m in sales_memberships)
        sales_total_work = sum(m.cumulative_work for m in sales_memberships)

        rd_inc_eff = sum(m.inc_eff for m in rd_memberships) if inc_start and inc_end else 0
        rd_inc_work = sum(m.inc_work for m in rd_memberships) if inc_start and inc_end else 0
        sales_inc_eff = sum(m.inc_eff for m in sales_memberships) if inc_start and inc_end else 0
        sales_inc_work = sum(m.inc_work for m in sales_memberships) if inc_start and inc_end else 0

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
            'project_count': rd_memberships.count() + sales_memberships.count(),
            'page_title': f'绩效明细: {target_user.username}',
            'start_date': start_date, 'end_date': end_date,
            'inc_start': inc_start, 'inc_end': inc_end,
        }
        return render(request, 'apps/app_project/performance/detail.html', context)
