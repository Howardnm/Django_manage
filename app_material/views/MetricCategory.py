from django.db.models import Count
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView

from app_material.forms import MetricCategoryForm
from app_material.models.material import MetricCategory
from app_material.utils.filters import MetricCategoryFilter
from app_material.mixins import MaterialAccessMixin


# ==========================================
# 6. 测试分类管理 (MetricCategory)
# ==========================================

class MetricCategoryListView(MaterialAccessMixin, ListView):
    """测试分类列表：全员可见"""
    permission_required = 'app_material.view_metriccategory'
    model = MetricCategory
    template_name = 'apps/app_material/metric_category/list.html'
    context_object_name = 'categories'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset().annotate(
            testconfig_count=Count('testconfig')
        ).order_by('order', 'name')
        self.filterset = MetricCategoryFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'filter': self.filterset,
            'current_sort': self.request.GET.get('sort', ''),
            'page_title': '测试分类管理',
        })
        return context


class MetricCategoryCreateView(MaterialAccessMixin, CreateView):
    """新增测试分类：需 add 权限"""
    permission_required = 'app_material.add_metriccategory'
    model = MetricCategory
    form_class = MetricCategoryForm
    template_name = 'apps/app_material/form_generic.html'
    success_url = reverse_lazy('metric_category_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增测试分类'
        return context


class MetricCategoryUpdateView(MaterialAccessMixin, UpdateView):
    """编辑测试分类：需 change 权限"""
    permission_required = 'app_material.change_metriccategory'
    model = MetricCategory
    form_class = MetricCategoryForm
    template_name = 'apps/app_material/form_generic.html'
    success_url = reverse_lazy('metric_category_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑分类: {self.object.name}'
        return context
