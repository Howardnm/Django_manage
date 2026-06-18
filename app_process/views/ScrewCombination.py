from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DetailView

from app_process.models import ScrewCombination
from app_process.forms import ScrewCombinationForm
from app_process.utils.filters import ScrewCombinationFilter
from app_process.mixins import ProcessAccessMixin


class ScrewCombinationListView(ProcessAccessMixin, ListView):
    """螺杆组合列表：不设部门隔离"""
    permission_required = 'app_process.view_screwcombination'
    model = ScrewCombination
    template_name = 'apps/app_process/screw/list.html'
    context_object_name = 'screws'
    paginate_by = 20
    
    enforce_dept_isolation = False

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related('machines', 'suitable_materials')
        self.filterset = ScrewCombinationFilter(self.request.GET, queryset=qs)
        qs = self.filterset.qs
        sort_param = self.request.GET.get('sort')
        allowed_sorts = ['name', '-name', 'combination_code', '-combination_code', 'created_at', '-created_at']
        if sort_param in allowed_sorts:
            qs = qs.order_by(sort_param)
        else:
            qs = qs.order_by('-created_at')
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        context['current_sort'] = self.request.GET.get('sort', '')
        return context


class ScrewCombinationCreateView(ProcessAccessMixin, CreateView):
    """新增组合"""
    permission_required = 'app_process.add_screwcombination'
    model = ScrewCombination
    form_class = ScrewCombinationForm
    template_name = 'apps/app_process/screw/form.html'
    success_url = reverse_lazy('process_screw_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增螺杆组合'
        return context

    def form_valid(self, form):
        messages.success(self.request, "螺杆组合已添加")
        return super().form_valid(form)


class ScrewCombinationUpdateView(ProcessAccessMixin, UpdateView):
    """编辑组合"""
    permission_required = 'app_process.change_screwcombination'
    model = ScrewCombination
    form_class = ScrewCombinationForm
    template_name = 'apps/app_process/screw/form.html'
    success_url = reverse_lazy('process_screw_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '编辑螺杆组合'
        return context

    def form_valid(self, form):
        messages.success(self.request, "螺杆组合已更新")
        return super().form_valid(form)


class ScrewCombinationDetailView(ProcessAccessMixin, DetailView):
    """螺杆组合详情页"""
    permission_required = 'app_process.view_screwcombination'
    model = ScrewCombination
    template_name = 'apps/app_process/screw/detail.html'
    context_object_name = 'screw'

    enforce_dept_isolation = False

    def get_queryset(self):
        return super().get_queryset().prefetch_related('machines', 'suitable_materials')

    def get_object(self, queryset=None):
        return self.get_object_or_deny()
