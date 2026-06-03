from django.views.generic import CreateView
from django.shortcuts import redirect
from django.contrib import messages
from app_trial_production.mixins import ExtrusionTaskAccessMixin
from app_trial_production.models import ExtrusionRecord, ProductionOrder
from app_trial_production.forms import ExtrusionRecordForm


class ExtrusionRecordCreateView(ExtrusionTaskAccessMixin, CreateView):
    model = ExtrusionRecord
    form_class = ExtrusionRecordForm
    template_name = 'apps/app_trial_production/extrusion/record_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.production_order = ProductionOrder.objects.get(pk=kwargs['order_pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        if self.production_order.process_profile:
            pp = self.production_order.process_profile
            for field in ['temp_zone_1', 'temp_zone_2', 'temp_zone_3', 'temp_zone_4',
                          'temp_zone_5', 'temp_zone_6', 'temp_zone_7', 'temp_zone_8',
                          'temp_zone_9', 'temp_zone_10', 'temp_zone_11', 'temp_zone_12',
                          'temp_head', 'screw_speed', 'torque', 'current',
                          'melt_pressure', 'melt_temp', 'vacuum',
                          'main_feeder_speed', 'side_feeder_speed', 'liquid_pump_speed',
                          'throughput', 'cooling_method', 'strand_count',
                          'water_temp', 'water_bath_length', 'air_knife_pressure',
                          'pelletizing_speed', 'screen_mesh']:
                initial[field] = getattr(pp, field, None) or ''
        return initial

    def form_valid(self, form):
        form.instance.production_order = self.production_order
        form.instance.recorded_by = self.request.user
        messages.success(self.request, '挤出生产记录已保存')
        return super().form_valid(form)

    def get_success_url(self):
        return redirect('trial_production_order_detail', pk=self.production_order.pk).url

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['production_order'] = self.production_order
        return context
