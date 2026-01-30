from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView
from django.db.models import Q
from django import forms

from app_repository.models import TestConfig, MetricCategory
from app_repository.forms import TestConfigForm
from common_utils.filters import TablerFilterMixin
import django_filters

# 过滤器
class TestConfigFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')
    
    # 【修改】显式定义 category 字段并添加 widget 样式
    category = django_filters.ModelChoiceFilter(
        queryset=MetricCategory.objects.all(),
        label='分类',
        empty_label="所有分类",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = TestConfig
        fields = ['q', 'category']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(name__icontains=value) |
            Q(standard__icontains=value) |
            Q(condition__icontains=value)
        )

# 列表视图
class TestConfigListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'app_repository.view_testconfig'
    model = TestConfig
    template_name = 'apps/app_repository/test_config/list.html'
    context_object_name = 'configs'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related('category')
        
        # 排序逻辑
        sort_param = self.request.GET.get('sort', '')
        if sort_param:
            # 支持多字段排序，例如按分类和权重
            if sort_param == 'category':
                qs = qs.order_by('category__order', 'order')
            elif sort_param == '-category':
                qs = qs.order_by('-category__order', 'order')
            else:
                qs = qs.order_by(sort_param)
        else:
            # 默认排序
            qs = qs.order_by('category__order', 'order')
            
        self.filterset = TestConfigFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        context['current_sort'] = self.request.GET.get('sort', '')
        return context

# 创建视图
class TestConfigCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'app_repository.add_testconfig'
    raise_exception = True
    model = TestConfig
    form_class = TestConfigForm
    template_name = 'apps/app_repository/test_config/form.html'
    success_url = reverse_lazy('repo_test_config_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增测试标准'
        return context

    def form_valid(self, form):
        messages.success(self.request, "测试标准已添加")
        return super().form_valid(form)

# 更新视图
class TestConfigUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'app_repository.change_testconfig'
    raise_exception = True
    model = TestConfig
    form_class = TestConfigForm
    template_name = 'apps/app_repository/test_config/form.html'
    success_url = reverse_lazy('repo_test_config_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '编辑测试标准'
        return context

    def form_valid(self, form):
        messages.success(self.request, "测试标准已更新")
        return super().form_valid(form)
