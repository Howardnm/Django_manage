from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DetailView

from app_process.models import ProcessProfile
from app_process.forms import ProcessProfileForm
from app_process.utils.filters import ProcessProfileFilter

class ProcessProfileListView(LoginRequiredMixin, ListView):
    model = ProcessProfile
    template_name = 'apps/app_process/profile/list.html'
    context_object_name = 'profiles'
    paginate_by = 20

    def get_queryset(self):
        # 【修改】预加载 material_types (多对多)
        qs = super().get_queryset().select_related('machine', 'screw_combination').prefetch_related('material_types').order_by('-created_at')
        self.filterset = ProcessProfileFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        return context

class ProcessProfileDetailView(LoginRequiredMixin, DetailView):
    model = ProcessProfile
    template_name = 'apps/app_process/profile/detail.html'
    context_object_name = 'profile'

    def get_queryset(self):
        # 【修改】移除 process_type 关联查询
        return super().get_queryset().select_related('machine', 'screw_combination')

class ProcessProfileCreateView(LoginRequiredMixin, CreateView):
    model = ProcessProfile
    form_class = ProcessProfileForm
    template_name = 'apps/app_process/profile/form.html'
    success_url = reverse_lazy('process_profile_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增工艺方案'
        return context

    def form_valid(self, form):
        messages.success(self.request, "工艺方案已添加")
        return super().form_valid(form)

class ProcessProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = ProcessProfile
    form_class = ProcessProfileForm
    template_name = 'apps/app_process/profile/form.html'
    success_url = reverse_lazy('process_profile_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '编辑工艺方案'
        return context

    def form_valid(self, form):
        messages.success(self.request, "工艺方案已更新")
        return super().form_valid(form)
