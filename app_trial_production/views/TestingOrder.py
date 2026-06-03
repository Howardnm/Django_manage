from django.views.generic import ListView, DetailView, UpdateView
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse
from app_trial_production.mixins import TestingTaskAccessMixin
from app_trial_production.models import TestingOrder, TrialTestResult


class TestingOrderListView(TestingTaskAccessMixin, ListView):
    model = TestingOrder
    template_name = 'apps/app_trial_production/testing/list.html'
    context_object_name = 'testing_orders'
    paginate_by = 20

    def get_queryset(self):
        return TestingOrder.objects.select_related(
            'production_order', 'assigned_to',
        ).prefetch_related('test_items', 'specimens').order_by('-created_at')

class TestingOrderDetailView(TestingTaskAccessMixin, DetailView):
    model = TestingOrder
    template_name = 'apps/app_trial_production/testing/detail.html'
    context_object_name = 'testing_order'

    def get_queryset(self):
        return TestingOrder.objects.select_related(
            'production_order__project', 'production_order__project_node',
            'assigned_to',
        ).prefetch_related(
            'test_items', 'specimens__mold',
            'test_results__test_config',
            'test_results__formula',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from app_formula.models import LabFormula
        context['formulas'] = LabFormula.objects.filter(
            code=self.object.production_order.trial_code,
            project=self.object.production_order.project,
        ).order_by('version')

        # 项目历史测试结果侧边栏
        project = self.object.production_order.project
        if project:
            historical = TestingOrder.objects.filter(
                production_order__project=project,
            ).select_related(
                'production_order', 'assigned_to',
            ).prefetch_related(
                'test_results__test_config', 'test_results__formula',
            ).order_by('-created_at')
            groups = {}
            for order in historical:
                code = order.production_order.trial_code
                if code not in groups:
                    groups[code] = {'code': code, 'orders': []}
                groups[code]['orders'].append(order)
            context['historical_test_groups'] = list(groups.values())
        else:
            context['historical_test_groups'] = []

        return context


class TestingOrderFillResultsView(TestingTaskAccessMixin, UpdateView):
    model = TestingOrder
    fields = []
    template_name = 'apps/app_trial_production/testing/fill_results.html'
    context_object_name = 'testing_order'

    def _get_formulas(self):
        from app_formula.models import LabFormula
        return list(LabFormula.objects.filter(
            code=self.object.production_order.trial_code,
            project=self.object.production_order.project,
        ).order_by('version'))

    def _build_matrix(self, post_data=None):
        formulas = self._get_formulas()
        matrix = []
        for item in self.object.test_items.all():
            row = {'test_config': item, 'formula_results': [], 'test_date': None, 'remark': ''}
            for f in formulas:
                result, _ = TrialTestResult.objects.get_or_create(
                    testing_order=self.object, test_config=item, formula=f)
                if post_data:
                    result.value = post_data.get(f'value_{item.pk}_{f.pk}') or None
                    result.value_text = post_data.get(f'value_text_{item.pk}_{f.pk}', '')
                    result.test_date = post_data.get(f'test_date_{item.pk}') or None
                    result.remark = post_data.get(f'remark_{item.pk}', '')
                    result.save()
                row['formula_results'].append({'formula': f, 'result': result})
                row['test_date'] = result.test_date
                row['remark'] = result.remark
            matrix.append(row)
        return matrix

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['results_matrix'] = self._build_matrix(self.request.POST)
        else:
            context['results_matrix'] = self._build_matrix()
        context['formulas'] = self._get_formulas()
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.status == 'RESULTS_WRITTEN_BACK':
            messages.warning(request, '测试结果已回写，无法再修改')
            return redirect('trial_testing_detail', pk=self.object.pk)
        self.get_context_data()
        messages.success(request, '测试结果已保存')
        return redirect('trial_testing_detail', pk=self.object.pk)


class TestingOrderWriteBackView(TestingTaskAccessMixin, UpdateView):
    model = TestingOrder
    fields = []

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        from app_formula.models import FormulaTestResult

        order = self.object

        if order.status == 'RESULTS_WRITTEN_BACK':
            messages.warning(request, '测试结果已回写，无需重复操作')
            return redirect('trial_testing_detail', pk=order.pk)

        written = 0
        for trial_result in order.test_results.filter(is_written_back=False):
            if (trial_result.value is not None or trial_result.value_text) and trial_result.formula:
                FormulaTestResult.objects.update_or_create(
                    formula=trial_result.formula,
                    test_config=trial_result.test_config,
                    defaults={
                        'value': trial_result.value,
                        'value_text': trial_result.value_text,
                    },
                )
                trial_result.is_written_back = True
                trial_result.save()
                written += 1

        if written:
            order.status = 'RESULTS_WRITTEN_BACK'
            order.save()
            messages.success(request, f'已将 {written} 条测试结果回写到配方')
        else:
            messages.warning(request, '没有可回写的测试结果')
        return redirect('trial_testing_detail', pk=order.pk)
