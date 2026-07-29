import logging

from django.contrib import messages
from django.urls import reverse
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.db import transaction
from django.shortcuts import redirect
from django.db.models import Subquery, OuterRef, DecimalField, Q

from app_process.models import ProcessProfile
from app_process.forms import ProcessProfileForm
from app_process.utils.filters import ProcessProfileFilter
from app_process.mixins import ProcessAccessMixin

logger = logging.getLogger(__name__)


class ProcessProfileListView(ProcessAccessMixin, ListView):
    """工艺方案列表：准入及部门隔离"""
    permission_required = 'app_process.view_processprofile'
    model = ProcessProfile
    template_name = 'apps/app_process/profile/list.html'
    context_object_name = 'profiles'
    paginate_by = 20

    def get_queryset(self):
        # 1. 调用 Mixin 执行部门隔离
        qs = super().get_queryset().select_related('machine', 'screw_combination', 'creator').prefetch_related('material_types')
        
        # 2. 筛选
        self.filterset = ProcessProfileFilter(self.request.GET, queryset=qs)
        qs = self.filterset.qs

        # 3. 排序
        sort_param = self.request.GET.get('sort')
        allowed_sorts = ['name', '-name', 'machine__machine_code', '-machine__machine_code', 
                          'screw_combination__combination_code', '-screw_combination__combination_code',
                          'throughput', '-throughput', 'created_at', '-created_at']
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


class ProcessProfileDetailView(ProcessAccessMixin, DetailView):
    """工艺详情：拦截跨部门"""
    permission_required = 'app_process.view_processprofile'
    model = ProcessProfile
    template_name = 'apps/app_process/profile/detail.html'
    context_object_name = 'profile'

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def get_queryset(self):
        return super().get_queryset().select_related('machine', 'screw_combination', 'creator')


class ProcessProfileCreateView(ProcessAccessMixin, CreateView):
    """新增工艺：绑定创建人"""
    permission_required = 'app_process.add_processprofile'
    model = ProcessProfile
    form_class = ProcessProfileForm
    template_name = 'apps/app_process/profile/form.html'

    def form_valid(self, form):
        form.instance.creator = self.request.user
        messages.success(self.request, "工艺方案已添加")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('process_profile_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增工艺方案'
        return context


class ProcessProfileDuplicateView(ProcessAccessMixin, UpdateView):
    """复制工艺：拦截跨部门源数据"""
    permission_required = 'app_process.add_processprofile'
    model = ProcessProfile
    form_class = ProcessProfileForm
    template_name = 'apps/app_process/profile/form.html'

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    @property
    def original_profile(self):
        """鉴权后懒加载原工艺方案"""
        if not hasattr(self, '_original_profile'):
            self._original_profile = self.get_object()
        return self._original_profile

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '复制工艺方案'
        return context

    def get_initial(self):
        initial = super().get_initial()
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
            form.instance.pk = None 
            form.instance.creator = self.request.user
            self.object = form.save()
        messages.success(self.request, "工艺方案已复制并创建")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('process_profile_detail', kwargs={'pk': self.object.pk})


class ProcessProfileUpdateView(ProcessAccessMixin, UpdateView):
    """编辑工艺：拦截跨部门"""
    permission_required = 'app_process.change_processprofile'
    model = ProcessProfile
    form_class = ProcessProfileForm
    template_name = 'apps/app_process/profile/form.html'

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def get_success_url(self):
        return reverse('process_profile_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, "工艺方案已更新")
        return super().form_valid(form)
