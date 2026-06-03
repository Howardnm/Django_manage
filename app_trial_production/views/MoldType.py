from django.views.generic import ListView, CreateView, UpdateView
from django.urls import reverse_lazy
from app_trial_production.mixins import TrialProductionAccessMixin
from app_trial_production.models import MoldType
from app_trial_production.forms import MoldTypeForm


class MoldTypeListView(TrialProductionAccessMixin, ListView):
    model = MoldType
    template_name = 'apps/app_trial_production/mold/list.html'
    context_object_name = 'molds'
    enforce_dept_isolation = False


class MoldTypeCreateView(TrialProductionAccessMixin, CreateView):
    model = MoldType
    form_class = MoldTypeForm
    template_name = 'apps/app_trial_production/mold/form.html'
    success_url = reverse_lazy('trial_mold_type_list')


class MoldTypeUpdateView(TrialProductionAccessMixin, UpdateView):
    model = MoldType
    form_class = MoldTypeForm
    template_name = 'apps/app_trial_production/mold/form.html'
    success_url = reverse_lazy('trial_mold_type_list')
