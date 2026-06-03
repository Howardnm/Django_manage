from django.views.generic import ListView, UpdateView
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse_lazy
from django.utils import timezone
from app_trial_production.mixins import TrialProductionAccessMixin
from app_trial_production.models import SampleInventory


class SampleInventoryListView(TrialProductionAccessMixin, ListView):
    model = SampleInventory
    template_name = 'apps/app_trial_production/sample/inventory_list.html'
    context_object_name = 'samples'
    paginate_by = 20

    def get_queryset(self):
        status_filter = self.request.GET.get('status', '')
        qs = SampleInventory.objects.select_related(
            'production_order', 'sample_split', 'sample_split__formula',
        )
        if status_filter:
            qs = qs.filter(status=status_filter)
        else:
            qs = qs.exclude(status='USED')
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_status'] = self.request.GET.get('status', '')
        context['status_choices'] = SampleInventory.STATUS_CHOICES
        return context


class SampleInventoryShipView(TrialProductionAccessMixin, UpdateView):
    model = SampleInventory
    fields = ['customer_name', 'tracking_number']
    template_name = 'apps/app_trial_production/sample/ship.html'

    def form_valid(self, form):
        form.instance.status = 'SHIPPED'
        form.instance.shipping_date = timezone.now().date()
        messages.success(self.request, '样品已标记为寄出')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('trial_sample_inventory')
