import logging

from django import forms as django_forms
from django.views.generic import View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum

from app_trial_production.mixins import ExtrusionTaskAccessMixin
from app_trial_production.models import SampleInventory
from app_trial_production.forms import PelletSplitForm, PelletSplitFormSet
from app_trial_production.services import SampleInventoryService

logger = logging.getLogger(__name__)


class PelletSplitView(ExtrusionTaskAccessMixin, View):
    """挤出后颗粒分拨 — 仅挤出操作员"""
    template_name = 'apps/app_trial_production/pellet/split.html'

    def _resolve_order(self):
        if not hasattr(self, '_order'):
            from app_trial_production.models import ProductionOrder
            self._order = get_object_or_404(ProductionOrder, pk=self.kwargs['pk'])
        return self._order

    def _get_formulas(self):
        from app_formula.models import LabFormula
        order = self._resolve_order()
        return LabFormula.objects.filter(
            code=order.trial_code, project=order.project,
        ).order_by('version')

    def get(self, request, pk):
        order = self._resolve_order()
        formulas = self._get_formulas()

        # 配方明细（计划产量）+ 已分拨汇总
        formula_details = order.formula_details.select_related('formula').order_by('formula__version')
        existing_splits = SampleInventory.objects.filter(
            production_order=order, type='PELLET',
        ).values('formula_id', 'sub_type').annotate(
            total_qty=Sum('quantity'),
        )
        split_map = {}
        for s in existing_splits:
            key = (s['formula_id'], s['sub_type'])
            split_map[key] = float(s['total_qty'] or 0)

        formula_summaries = []
        for fd in formula_details:
            finished_qty = split_map.get((fd.formula_id, 'FINISHED'), 0)
            for_injection_qty = split_map.get((fd.formula_id, 'FOR_INJECTION'), 0)
            formula_summaries.append({
                'formula': fd.formula,
                'planned_qty': float(fd.planned_quantity or 0),
                'finished_qty': finished_qty,
                'for_injection_qty': for_injection_qty,
                'total_split': finished_qty + for_injection_qty,
            })

        # 按「配方版本 × 分拨类型」排列组合预设所有行
        _formulas = formulas
        extra_rows = len(formulas) * 2

        initial_data = []
        for f in formulas:
            initial_data.append({'formula': f.pk, 'sub_type': 'FINISHED'})
            initial_data.append({'formula': f.pk, 'sub_type': 'FOR_INJECTION'})

        class _SplitForm(PelletSplitForm):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.fields['formula'].queryset = _formulas

        DynamicFormSet = django_forms.formset_factory(
            _SplitForm, extra=0, can_delete=True,
        )
        formset = DynamicFormSet(initial=initial_data)

        # 将标签注入每个 form 实例，供模板读取
        idx = 0
        for f in formulas:
            formset.forms[idx].row_label = {'version': f.version, 'type_label': '颗粒成品', 'type_css': 'bg-green-lt'}
            idx += 1
            formset.forms[idx].row_label = {'version': f.version, 'type_label': '待打样颗粒', 'type_css': 'bg-orange-lt'}
            idx += 1

        return render(request, self.template_name, {
            'production_order': order,
            'formset': formset,
            'formulas': formulas,
            'formula_summaries': formula_summaries,
        })

    def post(self, request, pk):
        order = self._resolve_order()
        formulas = self._get_formulas()

        _formulas = formulas

        class _SplitForm(PelletSplitForm):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.fields['formula'].queryset = _formulas

        DynamicFormSet = django_forms.formset_factory(
            _SplitForm, extra=1, can_delete=True,
        )
        formset = DynamicFormSet(request.POST)

        # 构建配方分拨概览（error 重渲染时需要）
        formula_details = order.formula_details.select_related('formula').order_by('formula__version')
        existing_splits = SampleInventory.objects.filter(
            production_order=order, type='PELLET',
        ).values('formula_id', 'sub_type').annotate(total_qty=Sum('quantity'))
        split_map = {}
        for s in existing_splits:
            key = (s['formula_id'], s['sub_type'])
            split_map[key] = float(s['total_qty'] or 0)
        formula_summaries = []
        for fd in formula_details:
            finished_qty = split_map.get((fd.formula_id, 'FINISHED'), 0)
            for_injection_qty = split_map.get((fd.formula_id, 'FOR_INJECTION'), 0)
            formula_summaries.append({
                'formula': fd.formula,
                'planned_qty': float(fd.planned_quantity or 0),
                'finished_qty': finished_qty,
                'for_injection_qty': for_injection_qty,
                'total_split': finished_qty + for_injection_qty,
            })

        if formset.is_valid():
            splits = []
            for form in formset:
                if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                    qty = form.cleaned_data.get('quantity')
                    if qty is None:
                        continue
                    splits.append({
                        'formula_id': form.cleaned_data.get('formula').pk if form.cleaned_data.get('formula') else None,
                        'sub_type': form.cleaned_data['sub_type'],
                        'quantity': qty,
                    })

            if not splits:
                messages.warning(request, '请至少填写一条分拨明细（含数量和类型）')
            else:
                try:
                    SampleInventoryService.create_pellet_batch(order, splits)
                    messages.success(request, f'已创建 {len(splits)} 条颗粒样品入库记录')
                except Exception:
                    logger.exception(f"Pellet split failed for order {order.code}")
                    messages.error(request, '分拨操作失败，请稍后重试')
            return redirect('trial_order_detail', pk=pk)

        # 校验失败：重新渲染，注入 row_label 供模板使用
        idx = 0
        for f in formulas:
            if idx < len(formset.forms):
                formset.forms[idx].row_label = {'version': f.version, 'type_label': '颗粒成品', 'type_css': 'bg-green-lt'}
            idx += 1
            if idx < len(formset.forms):
                formset.forms[idx].row_label = {'version': f.version, 'type_label': '待打样颗粒', 'type_css': 'bg-orange-lt'}
            idx += 1

        return render(request, self.template_name, {
            'production_order': order,
            'formset': formset,
            'formulas': formulas,
            'formula_summaries': formula_summaries,
        })
