from django.views.generic import ListView
from django.db.models import Count, Q
from app_trial_production.mixins import DashboardAccessMixin
from app_trial_production.models import ProductionOrder


class TrialDashboardView(DashboardAccessMixin, ListView):
    """排产总览面板"""
    model = ProductionOrder
    template_name = 'apps/app_trial_production/dashboard.html'
    context_object_name = 'orders'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        if qs is None:
            return self.model.objects.all()
        qs = qs.select_related(
            'project', 'creator', 'process_profile',
        ).prefetch_related('formula_details__formula').annotate(
            formula_count=Count('formula_details'),
        )
        status_filter = self.request.GET.get('status', '')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        status_filter = self.request.GET.get('status', '')
        context['status_filter'] = status_filter
        context['status_choices'] = ProductionOrder.Status.choices

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
