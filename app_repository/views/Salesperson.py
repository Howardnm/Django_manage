from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView

from app_repository.forms import SalespersonForm
from app_repository.models import Salesperson
from app_repository.utils.filters import SalespersonFilter

# ==========================================
# 6. 业务员管理 (Salesperson)
# ==========================================
class SalespersonListView(LoginRequiredMixin, ListView):
    model = Salesperson
    template_name = 'apps/app_repository/project_repo_info/salesperson_list.html'
    context_object_name = 'salespersons' # 统一改为 page_obj 配合分页组件
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset().order_by('name')
        # 【修改】接入 FilterSet
        self.filterset = SalespersonFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 【关键】把 filter 传给模板，搜索框才会显示！
        context['filter'] = self.filterset
        return context


class SalespersonCreateView(LoginRequiredMixin, CreateView):
    model = Salesperson
    form_class = SalespersonForm
    template_name = 'apps/app_repository/form_generic.html'  # 复用通用表单
    success_url = reverse_lazy('repo_sales_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增业务员'
        return context


class SalespersonUpdateView(LoginRequiredMixin, UpdateView):
    model = Salesperson
    form_class = SalespersonForm
    template_name = 'apps/app_repository/form_generic.html'
    success_url = reverse_lazy('repo_sales_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑业务员: {self.object.name}'
        return context
