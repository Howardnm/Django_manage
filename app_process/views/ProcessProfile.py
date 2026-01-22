from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
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
        # 1. 基础查询集
        qs = super().get_queryset().select_related('machine', 'screw_combination').prefetch_related('material_types')
        
        # 2. 筛选 (Filter)
        self.filterset = ProcessProfileFilter(self.request.GET, queryset=qs)
        qs = self.filterset.qs

        # 3. 排序 (Sort) - 处理 URL 中的 sort 参数
        sort_param = self.request.GET.get('sort')
        if sort_param:
            # 允许排序的字段白名单，防止 SQL 注入
            allowed_sorts = [
                'name', '-name', 
                'machine__machine_code', '-machine__machine_code', 
                'screw_combination__combination_code', '-screw_combination__combination_code',
                'throughput', '-throughput',
                'created_at', '-created_at'
            ]
            if sort_param in allowed_sorts:
                qs = qs.order_by(sort_param)
        else:
            # 默认排序
            qs = qs.order_by('-created_at')
            
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        # 【修复】将当前排序参数传给模板，用于高亮表头
        context['current_sort'] = self.request.GET.get('sort', '')
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
    # success_url = reverse_lazy('process_profile_list') # 移除静态 success_url

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增工艺方案'
        return context

    def get_success_url(self):
        # 跳转到详情页
        return reverse('process_profile_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, "工艺方案已添加")
        return super().form_valid(form)

class ProcessProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = ProcessProfile
    form_class = ProcessProfileForm
    template_name = 'apps/app_process/profile/form.html'
    # success_url = reverse_lazy('process_profile_list') # 移除静态 success_url

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '编辑工艺方案'
        return context

    def get_success_url(self):
        # 跳转到详情页
        return reverse('process_profile_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, "工艺方案已更新")
        return super().form_valid(form)
