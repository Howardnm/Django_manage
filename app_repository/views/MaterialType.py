from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView

from app_repository.forms import MaterialTypeForm
from app_repository.models import MaterialType
from app_repository.utils.filters import MaterialTypeFilter

# ==========================================
# 4. 材料类型管理 (MaterialType)
# ==========================================

# 1. 材料类型列表
class MaterialTypeListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'app_repository.view_materialtype'
    model = MaterialType
    # 注意：建议检查路径是否有空格，通常是 material_info
    template_name = 'apps/app_repository/materialtype/type_list.html'
    context_object_name = 'types'
    paginate_by = 10

    def get_queryset(self):
        # 基础查询集
        qs = super().get_queryset().order_by('name')
        # 接入 Filter
        self.filterset = MaterialTypeFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        context['current_sort'] = self.request.GET.get('sort', '')
        # 页面标题，方便模板调用
        context['page_title'] = '材料类型管理'
        return context


class MaterialTypeCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'app_repository.add_materialtype'
    raise_exception = True
    model = MaterialType
    form_class = MaterialTypeForm
    template_name = 'apps/app_repository/form_generic.html'  # 复用通用模板
    success_url = reverse_lazy('repo_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增材料类型'
        return context


class MaterialTypeUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'app_repository.change_materialtype'
    raise_exception = True
    model = MaterialType
    form_class = MaterialTypeForm
    template_name = 'apps/app_repository/form_generic.html'
    success_url = reverse_lazy('repo_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑类型: {self.object.name}'
        return context
