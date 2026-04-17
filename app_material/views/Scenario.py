from django.db.models import Count
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView

from app_material.forms import ApplicationScenarioForm
from app_material.models.material import ApplicationScenario
from app_material.utils.filters import ScenarioFilter
from app_material.mixins import MaterialAccessMixin


# ==========================================
# 5. 应用场景管理 (ApplicationScenario)
# ==========================================

class ScenarioListView(MaterialAccessMixin, ListView):
    """应用场景列表：内部可见"""
    permission_required = 'app_material.view_applicationscenario'
    model = ApplicationScenario
    template_name = 'apps/app_material/scenario/scenario_list.html'
    context_object_name = 'scenarios'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset().annotate(
            material_count=Count('materials')
        ).order_by('name')
        self.filterset = ScenarioFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'filter': self.filterset,
            'current_sort': self.request.GET.get('sort', ''),
            'page_title': '应用场景管理'
        })
        return context


class ScenarioCreateView(MaterialAccessMixin, CreateView):
    """新增场景：需 add 权限"""
    permission_required = 'app_material.add_applicationscenario'
    model = ApplicationScenario
    form_class = ApplicationScenarioForm
    template_name = 'apps/app_material/form_generic.html'
    success_url = reverse_lazy('scenario_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增应用场景'
        return context


class ScenarioUpdateView(MaterialAccessMixin, UpdateView):
    """编辑场景：需 change 权限"""
    permission_required = 'app_material.change_applicationscenario'
    model = ApplicationScenario
    form_class = ApplicationScenarioForm
    template_name = 'apps/app_material/form_generic.html'
    success_url = reverse_lazy('scenario_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑场景: {self.object.name}'
        return context
