import logging
from collections import OrderedDict

from django.views.generic import ListView, DetailView, View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Count

from app_trial_production.mixins import SampleInventoryAccessMixin
from app_trial_production.models import SampleInventory
from app_trial_production.filters import SampleInventoryFilter
from app_trial_production.forms import SapEntryForm
from app_trial_production.services import SampleInventoryService

logger = logging.getLogger(__name__)


class SampleInventoryListView(SampleInventoryAccessMixin, ListView):
    """
    统一样品库页面 — 顶部 Tab 切换颗粒样品/样条样品。
    按试验单号 (trial_code) 分组展示。
    """
    model = SampleInventory
    template_name = 'apps/app_trial_production/sample/inventory.html'
    context_object_name = 'samples'
    paginate_by = 50

    def get_queryset(self):
        qs = super().get_queryset()
        if qs is None:
            qs = self.model.objects.all()

        # Tab → type 映射（视图级路由，不属用户筛选）
        active_tab = self.request.GET.get('tab', 'PELLET')
        qs = qs.filter(type=active_tab)

        # 用户筛选：复用 SampleInventoryFilter
        self.filter = SampleInventoryFilter(self.request.GET, queryset=qs)
        qs = self.filter.qs

        # 默认排除已消耗（未指定 status 时生效）
        if not self.request.GET.get('status'):
            qs = qs.exclude(status='CONSUMED')

        return qs.select_related(
            'production_order', 'formula', 'mold', 'injection_task',
        ).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        active_tab = self.request.GET.get('tab', 'PELLET')
        context['filter'] = getattr(self, 'filter', None)
        context['active_tab'] = active_tab
        context['tab_choices'] = SampleInventory.Type.choices
        context['status_choices'] = SampleInventory.Status.choices
        context['current_status'] = self.request.GET.get('status', '')

        # 按 trial_code 分组
        samples = context['samples']
        grouped = OrderedDict()
        for s in samples:
            code = s.trial_code or '(未知)'
            if code not in grouped:
                grouped[code] = {
                    'trial_code': code,
                    'production_order': s.production_order,
                    'items': [],
                }
            grouped[code]['items'].append(s)
        context['grouped_samples'] = list(grouped.values())

        # 待打样颗粒列表（供注塑取料入口）
        if active_tab == 'PELLET':
            context['available_for_injection'] = SampleInventoryService.get_available_for_injection()[:10]

        return context


class SampleInventoryDetailView(SampleInventoryAccessMixin, DetailView):
    """样品详情"""
    model = SampleInventory
    template_name = 'apps/app_trial_production/sample/detail.html'
    context_object_name = 'sample'

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_sap_entry'] = self.object.can_sap_entry
        return context


class SapEntryView(SampleInventoryAccessMixin, View):
    """SAP 入库操作"""
    template_name = 'apps/app_trial_production/sample/sap_entry.html'

    def get(self, request, pk):
        sample = get_object_or_404(SampleInventory, pk=pk)
        if not sample.can_sap_entry:
            messages.warning(request, '当前样品状态不允许SAP入库')
            return redirect('trial_sample_detail', pk=pk)

        form = SapEntryForm(instance=sample)
        return render(request, self.template_name, {
            'sample': sample, 'form': form,
        })

    def post(self, request, pk):
        sample = get_object_or_404(SampleInventory, pk=pk)
        form = SapEntryForm(request.POST, instance=sample)
        if form.is_valid():
            try:
                SampleInventoryService.sap_warehouse_entry(
                    sample, form.cleaned_data, request.user)
                messages.success(request, '样品已入SAP仓库')
                return redirect('trial_sample_detail', pk=pk)
            except Exception:
                logger.exception(f"SAP entry failed for sample {sample.pk}")
                messages.error(request, 'SAP入库操作失败，请稍后重试')

        return render(request, self.template_name, {
            'sample': sample, 'form': form,
        })
