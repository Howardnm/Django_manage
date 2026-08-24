import logging

from django.views.generic import ListView, DetailView, View
from django.shortcuts import redirect, render, get_object_or_404
from django.contrib import messages
from django.db import models
from django.db.models import Count, OuterRef, Subquery
from app_material_testing.mixins import TestingAccessMixin, TestingTaskAccessMixin
from app_material_testing.models import TestingTask, TrialTestResult
from app_material_testing.services import TestingTaskService
from common_utils.state_machine import InvalidStateTransition

logger = logging.getLogger(__name__)


class TestingTaskListView(TestingTaskAccessMixin, ListView):
    """测试任务列表"""
    permission_required = 'app_material_testing.view_testingtask'
    model = TestingTask
    template_name = 'apps/app_material_testing/list.html'
    context_object_name = 'testing_tasks'
    paginate_by = 20

    def get_queryset(self):
        from app_material_testing.filters import TestingTaskFilter
        qs = super().get_queryset()
        if qs is None:
            return self.model.objects.all()
        from app_trial_production.models import ProductionOrderFormulaDetail
        formula_count_sub = ProductionOrderFormulaDetail.objects.filter(
            production_order_id=OuterRef('production_order_id'),
        ).values('production_order_id').annotate(
            _count=Count('id')).values('_count')
        qs = qs.select_related(
            'production_order', 'production_order__project', 'assigned_to',
        ).prefetch_related('test_items').annotate(
            test_item_count=Count('test_items'),
            formula_count=Subquery(formula_count_sub, output_field=models.IntegerField()),
        )
        self.filter = TestingTaskFilter(self.request.GET, queryset=qs)
        qs = self.filter.qs

        # 状态 tab 筛选（卡片头部 tab，非 django_filters 字段）
        status_param = self.request.GET.get('status', '')
        valid_statuses = {s.value for s in TestingTask.Status}
        if status_param == 'ALL':
            pass  # 显示全部状态
        elif status_param in valid_statuses:
            qs = qs.filter(status=status_param)

        if not self.request.GET.get('sort'):
            qs = qs.order_by('-created_at')
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = getattr(self, 'filter', None)
        context['current_sort'] = self.request.GET.get('sort', '')
        context['current_status'] = self.request.GET.get('status', 'ALL')
        return context


class TestingTaskDetailView(TestingTaskAccessMixin, DetailView):
    """测试任务详情"""
    permission_required = 'app_material_testing.view_testingtask'
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
    permission_required = 'app_material_testing.change_testingtask'
    template_name = 'apps/app_material_testing/fill_results.html'

    def _get_task(self):
        task = get_object_or_404(
            TestingTask.objects.select_related('production_order'),
            pk=self.kwargs['pk'])
        self.check_object_permission(task)
        return task

    def _get_formulas(self, task):
        from app_formula.models import LabFormula
        return list(LabFormula.objects.filter(
            code=task.production_order.trial_code,
            project=task.production_order.project,
        ).order_by('version'))

    def _build_matrix(self, task):
        """Build read-only matrix for GET display — single bulk query, no N+1."""
        formulas = self._get_formulas(task)
        # Batch fetch all results, index by (test_config_id, formula_id)
        all_results = TrialTestResult.objects.filter(testing_task=task)
        results_dict = {(r.test_config_id, r.formula_id): r for r in all_results}

        matrix = []
        for item in task.test_items.all():
            row = {'test_config': item, 'formula_results': [], 'test_date': None, 'remark': ''}
            for f in formulas:
                result = results_dict.get((item.pk, f.pk))
                if result is None:
                    result = TrialTestResult(
                        testing_task=task, test_config=item, formula=f)
                row['formula_results'].append({'formula': f, 'result': result})
                if result:
                    row['test_date'] = result.test_date
                    row['remark'] = result.remark
            matrix.append(row)
        return matrix, formulas

    def get(self, request, pk):
        task = self._get_task()
        matrix, formulas = self._build_matrix(task)
        return render(request, self.template_name, {
            'testing_task': task,
            'results_matrix': matrix,
            'formulas': formulas,
        })

    def post(self, request, pk):
        task = self._get_task()
        if task.status == TestingTask.Status.RESULTS_WRITTEN_BACK:
            messages.warning(request, '测试结果已回写，无法再修改')
            return redirect('material_testing:detail', pk=pk)

        from app_material_testing.forms import TestResultMatrixForm
        form = TestResultMatrixForm(request.POST, testing_task=task)
        if not form.is_valid():
            for error in form.errors.get('__all__', []):
                messages.error(request, str(error))
            # Rebuild GET-like context on validation failure
            matrix, formulas = self._build_matrix(task)
            return render(request, self.template_name, {
                'testing_task': task,
                'results_matrix': matrix,
                'formulas': formulas,
            })

        # NOTE: test_date 和 remark 按测试项行（per test_config）解析，同一测试项的
        # 所有配方版本共享相同的测试日期和备注。TrialTestResult 模型中这些字段是 per-cell，
        # 但实际使用场景中同一测试项的日期/备注通常相同，此设计为有意的 UI 简化。
        results_matrix = form.cleaned_data['results_matrix']
        from app_material_testing.services import TestingTaskService
        TestingTaskService.fill_results(task, results_matrix, request.user)
        messages.success(request, '测试结果已保存')
        return redirect('material_testing:detail', pk=pk)


class WriteBackView(TestingAccessMixin, View):
    """测试结果回写"""
    permission_required = 'app_material_testing.change_testingtask'

    def post(self, request, pk):
        task = get_object_or_404(TestingTask, pk=pk)
        self.check_object_permission(task)
        if task.status == TestingTask.Status.RESULTS_WRITTEN_BACK:
            messages.warning(request, '测试结果已回写，无需重复操作')
            return redirect('material_testing:detail', pk=pk)

        try:
            written = TestingTaskService.write_back_results(task)
            if written:
                messages.success(request, f'已将 {written} 条测试结果回写到配方')
            else:
                messages.warning(request, '没有可回写的测试结果')
        except InvalidStateTransition as e:
            logger.exception(f"Write-back failed for task {task.pk}")
            messages.error(request, f'回写测试结果失败：{e}')
        return redirect('material_testing:detail', pk=pk)


class ForceCompleteWriteBackView(TestingAccessMixin, View):
    """手动完成并回写 — 数据缺失时强制结束任务，回写已填结果。"""
    permission_required = 'app_material_testing.change_testingtask'

    def post(self, request, pk):
        task = get_object_or_404(TestingTask, pk=pk)
        self.check_object_permission(task)
        if task.status == TestingTask.Status.RESULTS_WRITTEN_BACK:
            messages.warning(request, '测试任务已回写，无需重复操作')
            return redirect('material_testing:detail', pk=pk)

        try:
            written = TestingTaskService.force_complete_and_writeback(task)
            messages.success(request, f'测试任务已手动完成，回写 {written} 条测试结果')
        except InvalidStateTransition as e:
            logger.exception(f"Force complete failed for task {task.pk}")
            messages.error(request, f'手动完成失败：{e}')
        return redirect('material_testing:detail', pk=pk)


# ── 样条库存（测试中心管辖） ──────────────────────────────────────────

class TestingSampleListView(TestingAccessMixin, View):
    """
    测试中心样条库存列表 — 全部样条（FOR_TESTING + TESTED），按工单分组表格呈现。

    设计说明: 此视图位于 app_material_testing 而非 app_trial_production，因为:
    1. 它服务于测试团队的工作流（测试人员查看待测试样条）
    2. 权限模型使用 TestingAccessMixin (identity_required=TESTING_TEAM)
    3. 底层数据模型(SampleInventory)属于排产模块，通过服务层调用实现数据访问
    4. 子类型筛选(FOR_TESTING/CONSUMED)体现测试领域的关注点
    """

    template_name = 'apps/app_material_testing/specimens.html'
    paginate_by = 20
    permission_required = 'app_material_testing.view_testingtask'

    def _get_filtered_qs(self, request):
        from app_trial_production.models import SampleInventory
        from app_trial_production.filters import SampleInventoryFilter

        qs = SampleInventory.objects.select_related(
            'production_order',
            'production_order__project',
            'formula',
            'mold',
            'injection_task',
        ).prefetch_related('injection_tasks')

        # Hard-code 范围：所有样条
        qs = qs.filter(type='SPECIMEN')

        self.filter = SampleInventoryFilter(request.GET, queryset=qs)
        qs = self.filter.qs

        # 子类型/状态筛选（默认全部样条）
        sub_type_param = request.GET.get('sub_type', '')
        if sub_type_param == 'FOR_TESTING':
            qs = qs.filter(sub_type='FOR_TESTING', status='IN_LAB')
        elif sub_type_param == 'CONSUMED':
            qs = qs.filter(status='CONSUMED')

        return qs.order_by('-created_at')

    def get(self, request):
        from django.core.paginator import Paginator
        from app_trial_production.services import SampleInventoryService

        samples_qs = self._get_filtered_qs(request)
        order_groups, _ = SampleInventoryService.build_order_groups(samples_qs)

        page_num = int(request.GET.get('page', 1))
        paginator = Paginator(order_groups, self.paginate_by)
        page_obj = paginator.get_page(page_num)

        context = {
            'order_groups': order_groups,
            'page_obj': page_obj,
            'paginator': paginator,
            'filter': self.filter,
            'current_sub_type': request.GET.get('sub_type', ''),
        }
        return render(request, self.template_name, context)
