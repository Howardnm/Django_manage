import logging

from django.views.generic import ListView, DetailView, View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Count
from collections import OrderedDict
from app_trial_production.mixins import SampleInventoryAccessMixin
from app_trial_production.models import SampleInventory
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
            return self.model.objects.all()

        # Tab 过滤
        active_tab = self.request.GET.get('tab', 'PELLET')
        qs = qs.filter(type=active_tab)

        # 状态过滤
        status = self.request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        else:
            qs = qs.exclude(status='CONSUMED')

        return qs.select_related(
            'production_order', 'formula', 'mold', 'injection_task',
        ).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        active_tab = self.request.GET.get('tab', 'PELLET')
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


class PelletSplitView(SampleInventoryAccessMixin, View):
    """挤出后颗粒分拨"""
    template_name = 'apps/app_trial_production/pellet/split.html'

    def _resolve_order(self):
        if not hasattr(self, '_order'):
            from app_trial_production.models import ProductionOrder
            self._order = get_object_or_404(ProductionOrder, pk=self.kwargs['order_pk'])
        return self._order

    def _get_formulas(self):
        from app_formula.models import LabFormula
        order = self._resolve_order()
        return LabFormula.objects.filter(
            code=order.trial_code, project=order.project,
        ).order_by('version')

    def get(self, request, order_pk):
        from app_trial_production.forms import PelletSplitFormSet
        order = self._resolve_order()
        formulas = self._get_formulas()

        formset = PelletSplitFormSet()
        for form in formset.forms:
            form.fields['formula'].queryset = formulas

        return render(request, self.template_name, {
            'production_order': order,
            'formset': formset,
            'formulas': formulas,
        })

    def post(self, request, order_pk):
        from app_trial_production.forms import PelletSplitFormSet
        order = self._resolve_order()
        formulas = self._get_formulas()

        formset = PelletSplitFormSet(request.POST)
        for form in formset.forms:
            form.fields['formula'].queryset = formulas

        if formset.is_valid():
            splits = []
            for form in formset:
                if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                    splits.append({
                        'formula_id': form.cleaned_data.get('formula').pk if form.cleaned_data.get('formula') else None,
                        'sub_type': form.cleaned_data['sub_type'],
                        'quantity': form.cleaned_data['quantity'],
                        'packaging_desc': form.cleaned_data.get('packaging_desc', ''),
                        'storage_location': form.cleaned_data.get('storage_location', ''),
                    })

            SampleInventoryService.create_pellet_batch(order, splits)
            messages.success(request, f'已创建 {len(splits)} 条颗粒样品入库记录')
            return redirect('trial_order_detail', pk=order_pk)

        return render(request, self.template_name, {
            'production_order': order,
            'formset': formset,
            'formulas': formulas,
        })
