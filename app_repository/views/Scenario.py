from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView

from app_repository.forms import ApplicationScenarioForm
from app_repository.models import ApplicationScenario
from app_repository.utils.filters import ScenarioFilter

# ==========================================
# 5. 应用场景管理 (ApplicationScenario)
# ==========================================

# 2. 应用场景列表
class ScenarioListView(LoginRequiredMixin, ListView):
    model = ApplicationScenario
    template_name = 'apps/app_repository/material_info/scenario_list.html'
    context_object_name = 'scenarios'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset().order_by('name')
        self.filterset = ScenarioFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        context['current_sort'] = self.request.GET.get('sort', '')
        context['page_title'] = '应用场景管理'
        return context


class ScenarioCreateView(LoginRequiredMixin, CreateView):
    model = ApplicationScenario
    form_class = ApplicationScenarioForm
    template_name = 'apps/app_repository/form_generic.html'
    success_url = reverse_lazy('repo_scenario_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增应用场景'
        return context


class ScenarioUpdateView(LoginRequiredMixin, UpdateView):
    model = ApplicationScenario
    form_class = ApplicationScenarioForm
    template_name = 'apps/app_repository/form_generic.html'
    success_url = reverse_lazy('repo_scenario_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑场景: {self.object.name}'
        return context
