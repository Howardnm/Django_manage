from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView

from app_raw_material.models import Supplier
from app_raw_material.forms import SupplierForm
from app_raw_material.utils.filters import SupplierFilter

class SupplierListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'app_raw_material.view_supplier'
    model = Supplier
    template_name = 'apps/app_raw_material/supplier/list.html'
    context_object_name = 'suppliers'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related('product_categories').order_by('-created_at')
        self.filterset = SupplierFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        return context

class SupplierCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'app_raw_material.add_supplier'
    raise_exception = True
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

class SupplierUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'app_raw_material.change_supplier'
    raise_exception = True
    model = Supplier
    form_class = SupplierForm
    template_name = 'apps/app_raw_material/supplier/form.html'
    success_url = reverse_lazy('raw_supplier_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '编辑供应商'
        return context

    def form_valid(self, form):
        messages.success(self.request, "供应商已更新")
        return super().form_valid(form)
