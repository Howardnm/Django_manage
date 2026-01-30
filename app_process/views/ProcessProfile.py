from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.db import transaction
from django.shortcuts import redirect

from app_process.models import ProcessProfile
from app_process.forms import ProcessProfileForm
from app_process.utils.filters import ProcessProfileFilter

class ProcessProfileListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'app_process.view_processprofile'
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

class ProcessProfileDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = 'app_process.view_processprofile'
    model = ProcessProfile
    template_name = 'apps/app_process/profile/detail.html'
    context_object_name = 'profile'

    def get_queryset(self):
        # 【修改】移除 process_type 关联查询
        return super().get_queryset().select_related('machine', 'screw_combination')

class ProcessProfileCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'app_process.add_processprofile'
    raise_exception = True
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

# 【新增】工艺方案复制视图
class ProcessProfileDuplicateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'app_process.add_processprofile'
    raise_exception = True
    model = ProcessProfile
    form_class = ProcessProfileForm
    template_name = 'apps/app_process/profile/form.html'

    def get_object(self, queryset=None):
        original_profile = super().get_object(queryset)
        return original_profile

    # 重新实现为 CreateView 逻辑
    def dispatch(self, request, *args, **kwargs):
        self.original_profile = self.get_object()
        return super().dispatch(request, *args, **kwargs)
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '复制工艺方案'
        return context

    def get_initial(self):
        initial = super().get_initial()
        # 预填充主表单数据
        initial.update({
            'name': f"{self.original_profile.name} (副本)",
            'machine': self.original_profile.machine,
            'screw_combination': self.original_profile.screw_combination,
            'material_types': self.original_profile.material_types.all(),
            'throughput': self.original_profile.throughput,
            'screw_speed': self.original_profile.screw_speed,
            'torque': self.original_profile.torque,
            'melt_temp': self.original_profile.melt_temp,
            'melt_pressure': self.original_profile.melt_pressure,
            'vacuum': self.original_profile.vacuum,
            'temp_zone_1': self.original_profile.temp_zone_1,
            'temp_zone_2': self.original_profile.temp_zone_2,
            'temp_zone_3': self.original_profile.temp_zone_3,
            'temp_zone_4': self.original_profile.temp_zone_4,
            'temp_zone_5': self.original_profile.temp_zone_5,
            'temp_zone_6': self.original_profile.temp_zone_6,
            'temp_zone_7': self.original_profile.temp_zone_7,
            'temp_zone_8': self.original_profile.temp_zone_8,
            'temp_zone_9': self.original_profile.temp_zone_9,
            'temp_zone_10': self.original_profile.temp_zone_10,
            'temp_zone_11': self.original_profile.temp_zone_11,
            'temp_zone_12': self.original_profile.temp_zone_12,
            'temp_head': self.original_profile.temp_head,
            'description': self.original_profile.description,
        })
        return initial

    def form_valid(self, form):
        with transaction.atomic():
            # 创建新工艺方案
            form.instance.pk = None # 确保是新建
            self.object = form.save()
                
        messages.success(self.request, "工艺方案已复制并创建")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('process_profile_detail', kwargs={'pk': self.object.pk})

class ProcessProfileUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'app_process.change_processprofile'
    raise_exception = True
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
