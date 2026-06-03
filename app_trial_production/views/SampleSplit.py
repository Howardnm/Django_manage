from django.views.generic import View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from app_trial_production.mixins import TrialProductionAccessMixin
from app_trial_production.models import ProductionOrder, ProductionOutput
from app_trial_production.forms import ProductionOutputForm, SampleSplitFormSet


class SampleSplitManageView(TrialProductionAccessMixin, View):
    template_name = 'apps/app_trial_production/sample/split_manage.html'

    def dispatch(self, request, *args, **kwargs):
        self.production_order = get_object_or_404(
            ProductionOrder.objects.select_related('production_output'),
            pk=kwargs['order_pk'])
        return super().dispatch(request, *args, **kwargs)

    def _get_formulas(self):
        from app_formula.models import LabFormula
        return list(LabFormula.objects.filter(
            code=self.production_order.trial_code,
            project=self.production_order.project,
        ).order_by('version'))

    def _get_formula_split_data(self):
        """按配方版本分组分拨记录，预计算合计"""
        formulas = self._get_formulas()
        data = []
        for f in formulas:
            splits = list(self.production_order.sample_splits.filter(formula=f))
            total = sum(float(s.quantity) for s in splits)
            data.append({
                'formula': f,
                'splits': splits,
                'total': total,
            })
        return data

    def get(self, request, *args, **kwargs):
        output = getattr(self.production_order, 'production_output', None)
        output_form = ProductionOutputForm(instance=output)
        split_formset = SampleSplitFormSet(instance=self.production_order)
        return render(request, self.template_name, {
            'production_order': self.production_order,
            'output_form': output_form,
            'split_formset': split_formset,
            'formula_split_data': self._get_formula_split_data(),
            'computed_total': self.production_order.computed_total_output,
        })

    def post(self, request, *args, **kwargs):
        output = getattr(self.production_order, 'production_output', None)
        output_form = ProductionOutputForm(request.POST, instance=output)
        if output_form.is_valid():
            output = output_form.save(commit=False)
            output.production_order = self.production_order
            output.save()

        split_formset = SampleSplitFormSet(
            request.POST, instance=self.production_order)
        if split_formset.is_valid():
            split_formset.save()
            messages.success(request, '样品分拨已保存')
            return redirect('trial_production_order_detail', pk=self.production_order.pk)

        return render(request, self.template_name, {
            'production_order': self.production_order,
            'output_form': output_form,
            'split_formset': split_formset,
            'formula_split_data': self._get_formula_split_data(),
            'computed_total': self.production_order.computed_total_output,
        })
