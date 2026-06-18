from django.views.generic import CreateView
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from app_trial_production.mixins import ExtrusionTaskAccessMixin
from app_trial_production.models import ExtrusionRecord, ProductionOrder
from app_trial_production.forms import ExtrusionRecordForm


class ExtrusionRecordCreateView(ExtrusionTaskAccessMixin, CreateView):
    model = ExtrusionRecord
    form_class = ExtrusionRecordForm
    template_name = 'apps/app_trial_production/extrusion/record_form.html'

    def _resolve_order(self):
        """鉴权后懒加载工单 + 操作员归属校验"""
        if not hasattr(self, '_order'):
            self._order = get_object_or_404(ProductionOrder, pk=self.kwargs['order_pk'])
            if self._order.extruder_operator_id and self._order.extruder_operator_id != self.request.user.pk:
                raise PermissionDenied("您不是该工单分配的挤出操作员")
        return self._order

    def get_initial(self):
        initial = super().get_initial()
        order = self._resolve_order()
        if order.process_profile:
            pp = order.process_profile
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
        form.instance.production_order = self._resolve_order()
        form.instance.recorded_by = self.request.user
        messages.success(self.request, '挤出生产记录已保存')
        return super().form_valid(form)

    def get_success_url(self):
        return redirect('trial_production_order_detail', pk=self._resolve_order().pk).url

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['production_order'] = self._resolve_order()
        return context
