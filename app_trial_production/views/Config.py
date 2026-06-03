from django.views.generic import UpdateView
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse
from app_trial_production.mixins import TrialProductionAccessMixin
from app_trial_production.models import TrialProductionConfig


class TrialConfigView(TrialProductionAccessMixin, UpdateView):
    model = TrialProductionConfig
    fields = ['workflow_definition']
    template_name = 'apps/app_trial_production/config/form.html'

    def get_object(self, queryset=None):
        return TrialProductionConfig.get()

    def form_valid(self, form):
        messages.success(self.request, '排产配置已保存')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('trial_production_config')
