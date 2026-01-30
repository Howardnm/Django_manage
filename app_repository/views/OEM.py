from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView

from app_repository.forms import OEMForm
from app_repository.models import OEM
from app_repository.utils.filters import OEMFilter

# ==========================================
# 7. 主机厂管理 (OEM)
# ==========================================
class OEMListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'app_repository.view_oem'
    model = OEM
    template_name = 'apps/app_repository/project_repo_info/oem_list.html'
    context_object_name = 'oems'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset().order_by('name')
        self.filterset = OEMFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        context['current_sort'] = self.request.GET.get('sort', '')
        return context


class OEMCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'app_repository.add_oem'
    raise_exception = True
    model = OEM
    form_class = OEMForm
    template_name = 'apps/app_repository/form_generic.html'  # 复用通用表单
    success_url = reverse_lazy('repo_oem_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增主机厂 (OEM)'
        return context


class OEMUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'app_repository.change_oem'
    raise_exception = True
    model = OEM
    form_class = OEMForm
    template_name = 'apps/app_repository/form_generic.html'
    success_url = reverse_lazy('repo_oem_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑主机厂: {self.object.name}'
        return context
