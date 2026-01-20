from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView

from app_process.models import ScrewCombination
from app_process.forms import ScrewCombinationForm
from app_process.utils.filters import ScrewCombinationFilter

class ScrewCombinationListView(LoginRequiredMixin, ListView):
    model = ScrewCombination
    template_name = 'apps/app_process/screw/list.html'
    context_object_name = 'screws'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related('machines', 'suitable_materials').order_by('-created_at')
        self.filterset = ScrewCombinationFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        return context

class ScrewCombinationCreateView(LoginRequiredMixin, CreateView):
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

class ScrewCombinationUpdateView(LoginRequiredMixin, UpdateView):
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
