from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView
from django.db.models import Q

from app_process.models import MachineModel, ScrewCombination
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


class ProcessAutocompleteView(ProcessAccessMixin, View):
    """Tom Select 远程搜索接口：机台型号 / 螺杆组合"""
    permission_required = 'app_process.view_machinemodel'

    def get(self, request):
        model_name = request.GET.get('model')
        query = request.GET.get('q', '')
        results = []
        if model_name == 'machinemodel':
            queryset = MachineModel.objects.filter(
                Q(brand__icontains=query) |
                Q(model_name__icontains=query) |
                Q(machine_code__icontains=query)
            ).order_by('brand', 'model_name')[:20]
            for item in queryset:
                results.append({'value': item.pk, 'text': str(item)})
        elif model_name == 'screwcombination':
            queryset = ScrewCombination.objects.filter(
                Q(name__icontains=query) |
                Q(combination_code__icontains=query)
            ).order_by('name')[:20]
            for item in queryset:
                results.append({'value': item.pk, 'text': str(item)})
        return JsonResponse(results, safe=False)
