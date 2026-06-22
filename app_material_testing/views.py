import logging

from django.views.generic import ListView, DetailView, View
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Count
from app_material_testing.mixins import TestingAccessMixin
from app_material_testing.models import TestingTask, TrialTestResult
from app_material_testing.services import TestingTaskService

logger = logging.getLogger(__name__)


class TestingTaskListView(TestingAccessMixin, ListView):
    """测试任务列表"""
    permission_required = []
    model = TestingTask
    template_name = 'apps/app_material_testing/list.html'
    context_object_name = 'testing_tasks'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        if qs is None:
            return self.model.objects.all()
        return qs.select_related(
            'production_order', 'assigned_to',
        ).prefetch_related('test_items').annotate(
            test_item_count=Count('test_items'),
        ).order_by('-created_at')


class TestingTaskDetailView(TestingAccessMixin, DetailView):
    """测试任务详情"""
    permission_required = []
    model = TestingTask
    template_name = 'apps/app_material_testing/detail.html'
    context_object_name = 'testing_task'

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def get_queryset(self):
        qs = super().get_queryset()
        if qs is None:
            return self.model.objects.all()
        return qs.select_related(
            'production_order__project', 'production_order__project_node',
            'assigned_to',
        ).prefetch_related(
            'test_items', 'test_results__test_config', 'test_results__formula',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from app_formula.models import LabFormula

        formulas = list(LabFormula.objects.filter(
            code=self.object.production_order.trial_code,
            project=self.object.production_order.project,
        ).order_by('version'))
        context['formulas'] = formulas

        # Build matrix rows for efficient template rendering
        test_items = list(self.object.test_items.all())
        results_qs = list(self.object.test_results.all())
        results_dict = {}
        for r in results_qs:
            results_dict[(r.test_config_id, r.formula_id)] = r

        matrix_rows = []
        for item in test_items:
            row = {'test_config': item, 'cells': []}
            for f in formulas:
                result = results_dict.get((item.pk, f.pk))
                row['cells'].append(result)
            first_result = next(
                (r for r in results_qs if r.test_config_id == item.pk), None)
            row['test_date'] = first_result.test_date if first_result else None
            first_formula_result = (
                results_dict.get((item.pk, formulas[0].pk))
                if formulas else None
            )
            row['is_written_back'] = (
                first_formula_result.is_written_back
                if first_formula_result else False
            )
            matrix_rows.append(row)

        context['matrix_rows'] = matrix_rows
        context['can_fill_results'] = (
            self.object.status != TestingTask.Status.RESULTS_WRITTEN_BACK
        )
        context['can_writeback'] = (
            self.object.test_results.exists()
            and self.object.status != TestingTask.Status.RESULTS_WRITTEN_BACK
        )

        # 项目历史测试结果
        project = self.object.production_order.project
        if project:
            historical = TestingTask.objects.filter(
                production_order__project=project,
            ).select_related(
                'production_order', 'assigned_to',
            ).prefetch_related(
                'test_results__test_config', 'test_results__formula',
            ).order_by('-created_at')
            groups = {}
            for task in historical:
                code = task.production_order.trial_code
                if code not in groups:
                    groups[code] = {'code': code, 'tasks': []}
                groups[code]['tasks'].append(task)
            context['historical_test_groups'] = list(groups.values())
        return context


class FillResultsView(TestingAccessMixin, View):
    """填写测试结果矩阵"""
    permission_required = []
    template_name = 'apps/app_material_testing/fill_results.html'

    def _get_task(self):
        return get_object_or_404(
            TestingTask.objects.select_related('production_order'),
            pk=self.kwargs['pk'])

    def _get_formulas(self, task):
        from app_formula.models import LabFormula
        return list(LabFormula.objects.filter(
            code=task.production_order.trial_code,
            project=task.production_order.project,
        ).order_by('version'))

    def _build_matrix(self, task):
        """Build read-only matrix for GET display."""
        formulas = self._get_formulas(task)
        matrix = []
        for item in task.test_items.all():
            row = {'test_config': item, 'formula_results': [], 'test_date': None, 'remark': ''}
            for f in formulas:
                try:
                    result = TrialTestResult.objects.get(
                        testing_task=task, test_config=item, formula=f)
                except TrialTestResult.DoesNotExist:
                    result = TrialTestResult(
                        testing_task=task, test_config=item, formula=f)
                row['formula_results'].append({'formula': f, 'result': result})
                row['test_date'] = result.test_date
                row['remark'] = result.remark
            matrix.append(row)
        return matrix, formulas

    def get(self, request, pk):
        task = self._get_task()
        matrix, formulas = self._build_matrix(task)
        from django.shortcuts import render
        return render(request, self.template_name, {
            'testing_task': task,
            'results_matrix': matrix,
            'formulas': formulas,
        })

    def post(self, request, pk):
        task = self._get_task()
        if task.status == 'RESULTS_WRITTEN_BACK':
            messages.warning(request, '测试结果已回写，无法再修改')
            return redirect('material_testing:detail', pk=pk)

        # Build results matrix from POST data
        formulas = self._get_formulas(task)
        results_matrix = []
        for item in task.test_items.all():
            test_date = request.POST.get(f'test_date_{item.pk}') or None
            remark = request.POST.get(f'remark_{item.pk}', '')
            for f in formulas:
                value = request.POST.get(f'value_{item.pk}_{f.pk}') or None
                value_text = request.POST.get(f'value_text_{item.pk}_{f.pk}', '')
                if value or value_text:
                    results_matrix.append({
                        'test_config_id': item.pk,
                        'formula_id': f.pk,
                        'value': value,
                        'value_text': value_text,
                        'test_date': test_date,
                        'remark': remark,
                    })

        from app_material_testing.services import TestingTaskService
        TestingTaskService.fill_results(task, results_matrix, request.user)
        messages.success(request, '测试结果已保存')
        return redirect('material_testing:detail', pk=pk)


class WriteBackView(TestingAccessMixin, View):
    """测试结果回写"""
    permission_required = []

    def post(self, request, pk):
        task = get_object_or_404(TestingTask, pk=pk)
        if task.status == 'RESULTS_WRITTEN_BACK':
            messages.warning(request, '测试结果已回写，无需重复操作')
            return redirect('material_testing:detail', pk=pk)

        try:
            written = TestingTaskService.write_back_results(task)
            if written:
                messages.success(request, f'已将 {written} 条测试结果回写到配方')
            else:
                messages.warning(request, '没有可回写的测试结果')
        except Exception:
            logger.exception(f"Write-back failed for task {task.pk}")
            messages.error(request, '回写测试结果时发生错误，请稍后重试')
        return redirect('material_testing:detail', pk=pk)
