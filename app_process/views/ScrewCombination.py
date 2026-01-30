from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView

from app_process.models import ScrewCombination
from app_process.forms import ScrewCombinationForm
from app_process.utils.filters import ScrewCombinationFilter

class ScrewCombinationListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'app_process.view_screwcombination'
    model = ScrewCombination
    template_name = 'apps/app_process/screw/list.html'
    context_object_name = 'screws'
    paginate_by = 20

    def get_queryset(self):
        # 1. 基础查询集
        qs = super().get_queryset().prefetch_related('machines', 'suitable_materials')
        
        # 2. 筛选 (Filter)
        self.filterset = ScrewCombinationFilter(self.request.GET, queryset=qs)
        qs = self.filterset.qs

        # 3. 排序 (Sort) - 处理 URL 中的 sort 参数
        sort_param = self.request.GET.get('sort')
        if sort_param:
            # 允许排序的字段白名单，防止 SQL 注入
            allowed_sorts = ['name', '-name', 'combination_code', '-combination_code', 'created_at', '-created_at']
            if sort_param in allowed_sorts:
                qs = qs.order_by(sort_param)
        else:
            # 默认排序
            qs = qs.order_by('-created_at')
            
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        # 将当前排序参数传给模板，用于高亮表头
        context['current_sort'] = self.request.GET.get('sort', '')
        return context

class ScrewCombinationCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'app_process.add_screwcombination'
    raise_exception = True
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

class ScrewCombinationUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'app_process.change_screwcombination'
    raise_exception = True
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
