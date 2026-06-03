from django.views.generic import ListView
from app_trial_production.mixins import DashboardAccessMixin
from app_trial_production.models import ProductionOrder


class TrialDashboardView(DashboardAccessMixin, ListView):
    model = ProductionOrder
    template_name = 'apps/app_trial_production/dashboard.html'
    context_object_name = 'orders'
    paginate_by = 20

    def get_queryset(self):
        qs = ProductionOrder.objects.select_related(
            'project', 'creator', 'process_profile',
        ).prefetch_related('formula_details__formula')
        status_filter = self.request.GET.get('status', '')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        status_filter = self.request.GET.get('status', '')
        context['status_filter'] = status_filter
        context['status_choices'] = ProductionOrder.STATUS_CHOICES

        context['total_orders'] = ProductionOrder.objects.count()
        context['active_orders'] = ProductionOrder.objects.filter(
            status__in=ProductionOrder.ACTIVE_STATUSES,
        ).count()
        context['completed_orders'] = ProductionOrder.objects.filter(
            status='COMPLETED',
        ).count()
        context['draft_orders'] = ProductionOrder.objects.filter(
            status='DRAFT',
        ).count()

        orders_by_status = []
        for status in ProductionOrder.STATUS_FLOW_ORDER:
            count = ProductionOrder.objects.filter(status=status).count()
            orders_by_status.append({
                'status': status,
                'label': dict(ProductionOrder.STATUS_CHOICES).get(status, status),
                'css_class': ProductionOrder.STATUS_CSS_MAP.get(status, 'bg-secondary-lt'),
                'count': count,
            })
        context['orders_by_status'] = orders_by_status
        return context
