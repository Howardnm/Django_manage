from django.views.generic import View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from app_trial_production.mixins import TrialProductionAccessMixin, RndAccessMixin
from app_user.mixins import IdentityConfig
from app_trial_production.models import ProductionOrder, ProductionOutput
from app_trial_production.forms import ProductionOutputForm, SampleSplitFormSet


class SampleSplitManageView(TrialProductionAccessMixin, View):
    permission_required = []  # 仅依赖 L1 角色 + L2 等级准入，不做 L3 权限码校验
    template_name = 'apps/app_trial_production/sample/split_manage.html'
    identity_required = IdentityConfig.TECH_CORE

    def _resolve_order(self):
        """鉴权后懒加载工单，避免 dispatch 中先查询后鉴权违规"""
        if not hasattr(self, '_order'):
            self._order = get_object_or_404(
                ProductionOrder.objects.select_related('production_output'),
                pk=self.kwargs['order_pk'])
            if self._order.project:
                RndAccessMixin.check_project_ownership(
                    self._order.project, self.request.user)
        return self._order

    def _get_formulas(self):
        from app_formula.models import LabFormula
        order = self._resolve_order()
        return list(LabFormula.objects.filter(
            code=order.trial_code,
            project=order.project,
        ).order_by('version'))

    def _get_formula_split_data(self):
        """按配方版本分组分拨记录，预计算合计"""
        formulas = self._get_formulas()
        data = []
        for f in formulas:
            splits = list(self._resolve_order().sample_splits.filter(formula=f))
            total = sum(float(s.quantity) for s in splits)
            data.append({
                'formula': f,
                'splits': splits,
                'total': total,
            })
        return data

    def get(self, request, *args, **kwargs):
        output = getattr(self._resolve_order(), 'production_output', None)
        output_form = ProductionOutputForm(instance=output)
        split_formset = SampleSplitFormSet(instance=self._resolve_order())
        return render(request, self.template_name, {
            'production_order': self._resolve_order(),
            'output_form': output_form,
            'split_formset': split_formset,
            'formula_split_data': self._get_formula_split_data(),
            'computed_total': self._resolve_order().computed_total_output,
        })

    def post(self, request, *args, **kwargs):
        output = getattr(self._resolve_order(), 'production_output', None)
        output_form = ProductionOutputForm(request.POST, instance=output)
        if output_form.is_valid():
            output = output_form.save(commit=False)
            output.production_order = self._resolve_order()
            output.save()

        split_formset = SampleSplitFormSet(
            request.POST, instance=self._resolve_order())
        if split_formset.is_valid():
            split_formset.save()
            messages.success(request, '样品分拨已保存')
            return redirect('trial_production_order_detail', pk=self._resolve_order().pk)

        return render(request, self.template_name, {
            'production_order': self._resolve_order(),
            'output_form': output_form,
            'split_formset': split_formset,
            'formula_split_data': self._get_formula_split_data(),
            'computed_total': self._resolve_order().computed_total_output,
        })
