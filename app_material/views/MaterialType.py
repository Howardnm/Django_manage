from django.db.models import Count
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView

from app_material.forms import MaterialTypeForm
from app_material.models.material import MaterialType
from app_material.utils.filters import MaterialTypeFilter
from app_material.mixins import MaterialAccessMixin


# ==========================================
# 4. 材料类型管理 (MaterialType)
# ==========================================

class MaterialTypeListView(MaterialAccessMixin, ListView):
    """材料分类列表：全员可见"""
    permission_required = 'app_material.view_materialtype'
    model = MaterialType
    template_name = 'apps/app_material/materialtype/type_list.html'
    context_object_name = 'types'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset().annotate(
            material_count=Count('materiallibrary')
        ).order_by('name')
        self.filterset = MaterialTypeFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'filter': self.filterset,
            'current_sort': self.request.GET.get('sort', ''),
            'page_title': '材料类型管理'
        })
        return context


class MaterialTypeCreateView(MaterialAccessMixin, CreateView):
    """新增分类：需 add 权限"""
    permission_required = 'app_material.add_materialtype'
    model = MaterialType
    form_class = MaterialTypeForm
    template_name = 'apps/app_material/form_generic.html'
    success_url = reverse_lazy('type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增材料类型'
        return context


class MaterialTypeUpdateView(MaterialAccessMixin, UpdateView):
    """编辑分类：需 change 权限"""
    permission_required = 'app_material.change_materialtype'
    model = MaterialType
    form_class = MaterialTypeForm
    template_name = 'apps/app_material/form_generic.html'
    success_url = reverse_lazy('type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑类型: {self.object.name}'
        return context
