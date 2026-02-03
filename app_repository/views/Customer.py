from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView

from app_repository.forms import CustomerForm
from app_repository.models import Customer
from app_repository.utils.filters import CustomerFilter

# ==========================================
# 1. 客户库视图 (Customer)
# ==========================================
class CustomerListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'app_repository.view_customer'
    model = Customer
    template_name = 'apps/app_repository/customer/customer_list.html'
    context_object_name = 'customers'  # 随便起一个名方便复用分页模板，但不能为 page_obj
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset().order_by('-id')
        # 实例化 Filter
        self.filterset = CustomerFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 传递 filter 对象供前端渲染搜索栏
        context['filter'] = self.filterset
        # 传递 current_sort 供前端渲染表头排序图标
        context['current_sort'] = self.request.GET.get('sort', '')
        return context


class CustomerCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'app_repository.add_customer'
    raise_exception = True
    model = Customer
    form_class = CustomerForm
    template_name = 'apps/app_repository/form_generic.html'  # 通用表单模板
    success_url = reverse_lazy('repo_customer_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增客户'
        return context


class CustomerUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'app_repository.change_customer'
    raise_exception = True
    model = Customer
    form_class = CustomerForm
    template_name = 'apps/app_repository/form_generic.html'
    success_url = reverse_lazy('repo_customer_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑客户: {self.object.company_name}'
        return context
