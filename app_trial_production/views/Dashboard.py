from django.views.generic import ListView
from django.db.models import Count, Q
from app_trial_production.mixins import DashboardAccessMixin
from app_trial_production.models import ProductionOrder
from app_trial_production.filters import ProductionOrderFilter


class TrialDashboardView(DashboardAccessMixin, ListView):
    """排产总览面板"""
    model = ProductionOrder
    template_name = 'apps/app_trial_production/dashboard.html'
    context_object_name = 'orders'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        if qs is None:
            qs = self.model.objects.all()
        qs = qs.select_related(
            'project', 'creator', 'process_profile',
        ).prefetch_related('formula_details__formula').annotate(
            formula_count=Count('formula_details'),
        )
        self.filter = ProductionOrderFilter(self.request.GET, queryset=qs)
        qs = self.filter.qs
        # 仅在未指定排序时使用默认排序，否则 filter.OrderingFilter 已处理
        if not self.request.GET.get('sort'):
            qs = qs.order_by('-created_at')
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filter

        # 当前排序状态（供模板 sort_toggle 使用）
        sort_list = self.request.GET.getlist('sort')
        context['current_sort'] = sort_list[0] if sort_list else ''

        # 单次聚合查询替代4个独立COUNT
        agg = ProductionOrder.objects.aggregate(
            total=Count('pk'),
            active=Count('pk', filter=Q(status__in=ProductionOrder.ACTIVE_STATUSES)),
            completed=Count('pk', filter=Q(status='COMPLETED')),
            draft=Count('pk', filter=Q(status='DRAFT')),
        )
        context['total_orders'] = agg['total']
        context['active_orders'] = agg['active']
        context['completed_orders'] = agg['completed']
        context['draft_orders'] = agg['draft']

        # 单次annotate查询替代N个COUNT
        status_counts = dict(
            ProductionOrder.objects.values_list('status').annotate(count=Count('pk'))
        )
        orders_by_status = []
        for status in ProductionOrder.STATUS_FLOW_ORDER:
            orders_by_status.append({
                'status': status,
                'label': status.label,
                'css_class': ProductionOrder.STATUS_CSS_MAP.get(status, 'bg-secondary-lt'),
                'count': status_counts.get(status.value, 0),
            })
        context['orders_by_status'] = orders_by_status
        return context
