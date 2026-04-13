from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Count
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView

from app_material.forms import MaterialCharacteristicForm
from app_material.models.material import MaterialCharacteristic
from common_utils.filters import TablerFilterMixin
import django_filters

# 过滤器
class CharacteristicFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(lookup_expr='icontains', label='搜索特征')
    class Meta:
        model = MaterialCharacteristic
        fields = ['q']

# 列表视图
class CharacteristicListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'app_material.view_materialcharacteristic'
    model = MaterialCharacteristic
    template_name = 'apps/app_material/characteristic/list.html'
    context_object_name = 'characteristics'
    paginate_by = 15

    def get_queryset(self):
        qs = super().get_queryset().annotate(
            material_count=Count('materials')
        ).order_by('name')
        self.filterset = CharacteristicFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        context['page_title'] = '材料特征属性管理'
        return context

# 创建视图
class CharacteristicCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'app_material.add_materialcharacteristic'
    model = MaterialCharacteristic
    form_class = MaterialCharacteristicForm
    template_name = 'apps/app_material/form_generic.html'
    success_url = reverse_lazy('characteristic_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增材料特征'
        return context

# 更新视图
class CharacteristicUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'app_material.change_materialcharacteristic'
    model = MaterialCharacteristic
    form_class = MaterialCharacteristicForm
    template_name = 'apps/app_material/form_generic.html'
    success_url = reverse_lazy('characteristic_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑特征: {self.object.name}'
        return context
