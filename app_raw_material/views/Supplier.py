from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DetailView

from app_raw_material.models import Supplier, RawMaterial
from app_raw_material.forms import SupplierForm
from app_raw_material.utils.filters import SupplierFilter
from app_raw_material.mixins import RawMaterialAccessMixin


class SupplierListView(RawMaterialAccessMixin, ListView):
    """供应商列表：仅限定的研发中心角色组可见"""
    permission_required = 'app_raw_material.view_supplier'
    model = Supplier
    template_name = 'apps/app_raw_material/supplier/list.html'
    context_object_name = 'suppliers'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related('product_categories').annotate(
            raw_material_count=Count('rawmaterial')
        ).order_by('-created_at')
        self.filterset = SupplierFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        return context


class SupplierDetailView(RawMaterialAccessMixin, DetailView):
    """供应商详情：展示其提供的原材料清单"""
    permission_required = 'app_raw_material.view_supplier'
    model = Supplier
    template_name = 'apps/app_raw_material/supplier/detail.html'
    context_object_name = 'supplier'

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'供应商详情: {self.object.name}'

        related_materials_list = RawMaterial.objects.filter(supplier=self.object).select_related('category').order_by('-created_at')
        paginator = Paginator(related_materials_list, 10)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        context.update({
            'page_obj': page_obj,
            'paginator': paginator,
            'is_paginated': page_obj.has_other_pages()
        })
        return context


class SupplierCreateView(RawMaterialAccessMixin, CreateView):
    """新增供应商：采购/管理权限"""
    permission_required = 'app_raw_material.add_supplier'
    model = Supplier
    form_class = SupplierForm
    template_name = 'apps/app_raw_material/supplier/form.html'
    success_url = reverse_lazy('raw_supplier_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增供应商'
        return context

    def form_valid(self, form):
        messages.success(self.request, "供应商已添加")
        return super().form_valid(form)


class SupplierUpdateView(RawMaterialAccessMixin, UpdateView):
    """编辑供应商：采购/管理权限"""
    permission_required = 'app_raw_material.change_supplier'
    model = Supplier
    form_class = SupplierForm
    template_name = 'apps/app_raw_material/supplier/form.html'
    success_url = reverse_lazy('raw_supplier_list')

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '编辑供应商'
        return context

    def form_valid(self, form):
        self.check_edit_permission(self.object)
        messages.success(self.request, "供应商已更新")
        return super().form_valid(form)
