from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView

from app_process.models import MachineModel
from app_process.forms import MachineModelForm
from app_process.utils.filters import MachineModelFilter
from app_process.mixins import ProcessAccessMixin


class MachineModelListView(ProcessAccessMixin, ListView):
    """机台型号列表：内部可见，不设部门隔离"""
    permission_required = 'app_process.view_machinemodel'
    model = MachineModel
    template_name = 'apps/app_process/machine/list.html'
    context_object_name = 'machines'
    paginate_by = 20
    
    enforce_dept_isolation = False

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related('suitable_materials')
        self.filterset = MachineModelFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        return context


class MachineModelCreateView(ProcessAccessMixin, CreateView):
    """新增机台：需相应权限"""
    permission_required = 'app_process.add_machinemodel'
    model = MachineModel
    form_class = MachineModelForm
    template_name = 'apps/app_process/machine/form.html'
    success_url = reverse_lazy('process_machine_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增机台型号'
        return context

    def form_valid(self, form):
        messages.success(self.request, "机台型号已添加")
        return super().form_valid(form)


class MachineModelUpdateView(ProcessAccessMixin, UpdateView):
    """编辑机台：需相应权限"""
    permission_required = 'app_process.change_machinemodel'
    model = MachineModel
    form_class = MachineModelForm
    template_name = 'apps/app_process/machine/form.html'
    success_url = reverse_lazy('process_machine_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '编辑机台型号'
        return context

    def form_valid(self, form):
        messages.success(self.request, "机台型号已更新")
        return super().form_valid(form)
