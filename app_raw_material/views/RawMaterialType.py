from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView

from app_raw_material.models import RawMaterialType
from app_raw_material.forms import RawMaterialTypeForm
from app_raw_material.utils.filters import RawMaterialTypeFilter
from app_raw_material.mixins import RawMaterialAccessMixin


class RawMaterialTypeListView(RawMaterialAccessMixin, ListView):
    """类型管理：全员(内部)可见"""
    permission_required = 'app_raw_material.view_rawmaterialtype'
    model = RawMaterialType
    template_name = 'apps/app_raw_material/type/list.html'
    context_object_name = 'types'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().order_by('order', 'name')
        self.filterset = RawMaterialTypeFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'filter': self.filterset,
            'current_sort': self.request.GET.get('sort', ''),
            'page_title': '原材料类型管理'
        })
        return context


class RawMaterialTypeCreateView(RawMaterialAccessMixin, CreateView):
    """新增类型：需 add 权限"""
    permission_required = 'app_raw_material.add_rawmaterialtype'
    model = RawMaterialType
    form_class = RawMaterialTypeForm
    template_name = 'apps/app_raw_material/type/form.html'
    success_url = reverse_lazy('raw_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增原材料类型'
        return context

    def form_valid(self, form):
        messages.success(self.request, "类型已添加")
        return super().form_valid(form)


class RawMaterialTypeUpdateView(RawMaterialAccessMixin, UpdateView):
    """编辑类型：需 change 权限"""
    permission_required = 'app_raw_material.change_rawmaterialtype'
    model = RawMaterialType
    form_class = RawMaterialTypeForm
    template_name = 'apps/app_raw_material/type/form.html'
    success_url = reverse_lazy('raw_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '编辑原材料类型'
        return context

    def form_valid(self, form):
        messages.success(self.request, "类型已更新")
        return super().form_valid(form)
