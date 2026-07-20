import logging

from django.db.models import Count
from django.views.generic import ListView, DetailView, View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from app_mold_injection.mixins import InjectionTaskAccessMixin
from app_mold_injection.models import InjectionTask
from app_mold_injection.forms import InjectionCompleteForm
from app_mold_injection.services import InjectionTaskService
from common_utils.state_machine import InvalidStateTransition

logger = logging.getLogger(__name__)


def _build_mold_formula_matrix(mold_requirements):
    """从 mold_requirements QuerySet 构建 (formulas, matrix_rows) 元组。

    供 InjectionDetailView 和 InjectionCompleteView 共用，
    避免重复的两层循环遍历逻辑。
    """
    formula_map = {}
    for req in mold_requirements:
        for detail in req.formula_details.all():
            if detail.formula_id and detail.formula_id not in formula_map:
                formula_map[detail.formula_id] = detail.formula
    formulas = sorted(formula_map.values(), key=lambda f: f.version)

    matrix_rows = []
    for req in mold_requirements:
        qty_map = {}
        row_total = 0
        for detail in req.formula_details.all():
            if detail.formula_id:
                qty_map[detail.formula_id] = detail.specimen_quantity
            row_total += detail.specimen_quantity
        matrix_rows.append({
            'mold': req.mold,
            'quantities': [qty_map.get(f.pk, 0) for f in formulas],
            'total': row_total,
        })
    return formulas, matrix_rows


class InjectionTaskListView(InjectionTaskAccessMixin, ListView):
    """注塑任务列表"""
    model = InjectionTask
    template_name = 'apps/app_mold_injection/injection/list.html'
    context_object_name = 'injection_tasks'
    paginate_by = 20

    def get_queryset(self):
        from app_mold_injection.filters import InjectionTaskFilter
        qs = super().get_queryset()
        if qs is None:
            qs = self.model.objects.all()
        qs = qs.select_related(
            'production_order', 'operator', 'sample_inventory',
        ).prefetch_related(
            'mold_requirements__mold',
        ).annotate(
            mold_count=Count('mold_requirements'),
        )
        self.filter = InjectionTaskFilter(self.request.GET, queryset=qs)
        qs = self.filter.qs
        if not self.request.GET.get('sort'):
            qs = qs.order_by('-created_at')
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = getattr(self, 'filter', None)
        context['current_sort'] = self.request.GET.get('sort', '')
        return context


class InjectionDetailView(InjectionTaskAccessMixin, DetailView):
    """注塑任务详情"""
    model = InjectionTask
    template_name = 'apps/app_mold_injection/injection/detail.html'
    context_object_name = 'injection_task'

    def get_queryset(self):
        qs = super().get_queryset()
        if qs is None:
            return self.model.objects.all()
        return qs.select_related(
            'production_order', 'sample_inventory', 'source_project', 'operator',
        ).prefetch_related(
            'mold_requirements__mold', 'mold_requirements__formula_details__formula',
            'output_specimens__mold',
        )

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        task = self.object

        formulas, matrix_rows = _build_mold_formula_matrix(
            task.mold_requirements.all())

        ctx['mold_matrix_formulas'] = formulas
        ctx['mold_matrix_rows'] = matrix_rows
        ctx['has_mold_requirements'] = len(matrix_rows) > 0

        ctx['show_start_btn'] = task.status == 'PENDING'
        ctx['show_complete_btn'] = task.status == 'IN_PROGRESS'
        ctx['has_output_specimens'] = task.output_specimens.exists()
        ctx['source_css_class'] = 'purple' if task.source == 'INVENTORY' else 'cyan'

        # ── 样条产出矩阵 — 模具 × 配方 ──
        if ctx['has_output_specimens']:
            specimens = list(task.output_specimens.select_related('mold', 'formula'))
            # 收集所有出现过的配方版本（排序列）
            out_formula_map = {}
            for sp in specimens:
                if sp.formula_id and sp.formula_id not in out_formula_map:
                    out_formula_map[sp.formula_id] = sp.formula
            out_formulas = sorted(out_formula_map.values(), key=lambda f: f.version)

            # 按模具分组，构建矩阵行（跳过 mold_id 为空的无效数据）
            mold_specimens = {}
            for sp in specimens:
                if not sp.mold_id or not sp.mold:
                    continue
                mold_key = sp.mold_id
                if mold_key not in mold_specimens:
                    mold_specimens[mold_key] = {
                        'mold': sp.mold,
                        'cells': {},
                        'storage_location': sp.storage_location or '',
                        'batch_label': sp.batch_label or '',
                    }
                if sp.formula_id:
                    mold_specimens[mold_key]['cells'][sp.formula_id] = sp

            out_matrix_rows = []
            grand_total_count = 0
            grand_total_qualified = 0
            formula_totals = {f.pk: {'count': 0, 'qualified': 0} for f in out_formulas}

            for entry in mold_specimens.values():
                row = {'mold': entry['mold'], 'cells': [], 'row_total_count': 0,
                       'row_total_qualified': 0, 'storage_location': entry['storage_location'],
                       'batch_label': entry['batch_label']}
                for f in out_formulas:
                    sp = entry['cells'].get(f.pk)
                    count = sp.specimen_count or 0 if sp else 0
                    qualified = sp.specimen_qualified or 0 if sp else 0
                    row['cells'].append({'formula_pk': f.pk, 'count': count, 'qualified': qualified})
                    row['row_total_count'] += count
                    row['row_total_qualified'] += qualified
                    formula_totals[f.pk]['count'] += count
                    formula_totals[f.pk]['qualified'] += qualified
                grand_total_count += row['row_total_count']
                grand_total_qualified += row['row_total_qualified']
                out_matrix_rows.append(row)

            # 转为列表格式，模板可直接 .count / .qualified 访问
            out_formula_totals = [
                {'formula_pk': f.pk, 'count': formula_totals[f.pk]['count'],
                 'qualified': formula_totals[f.pk]['qualified']}
                for f in out_formulas
            ]

            ctx['out_formulas'] = out_formulas
            ctx['out_matrix_rows'] = out_matrix_rows
            ctx['out_formula_totals'] = out_formula_totals
            ctx['out_grand_total_count'] = grand_total_count
            ctx['out_grand_total_qualified'] = grand_total_qualified
            ctx['out_matrix_colspan'] = 3 + len(out_formulas) * 2 + 2

        return ctx


class InjectionStartView(InjectionTaskAccessMixin, View):
    """开始注塑任务"""

    def post(self, request, pk):
        task = get_object_or_404(InjectionTask, pk=pk)
        if task.status != 'PENDING':
            messages.warning(request, '任务状态不允许开始')
            return redirect('mold_injection:task_detail', pk=pk)

        try:
            InjectionTaskService.start_task(task, request.user)
            messages.success(request, '注塑任务已开始')
        except InvalidStateTransition as e:
            logger.exception(f"Injection start failed: pk={pk}")
            messages.error(request, f'注塑任务启动失败：{e}')
        return redirect('mold_injection:task_detail', pk=pk)


class InjectionCompleteView(InjectionTaskAccessMixin, View):
    """完成注塑任务 — 含样条产出"""
    template_name = 'apps/app_mold_injection/injection/complete.html'

    @staticmethod
    def _build_matrix_context(task):
        """构建模具 × 配方矩阵上下文，供 GET 和 POST(form invalid) 共用。"""
        formulas, base_rows = _build_mold_formula_matrix(
            task.mold_requirements.all())
        is_inventory_source = (task.source == InjectionTask.Source.INVENTORY)

        matrix_rows = []
        for row in base_rows:
            if formulas:
                cells = [
                    {'formula': f, 'formula_key': f.pk, 'planned_qty': qty}
                    for f, qty in zip(formulas, row['quantities'])
                ]
            else:
                cells = [{'formula': None, 'formula_key': 'none', 'planned_qty': row['total']}]
            matrix_rows.append({'mold': row['mold'], 'cells': cells})

        return {
            'formulas': formulas,
            'matrix_rows': matrix_rows,
            'is_inventory_source': is_inventory_source,
            'has_mold_requirements': len(matrix_rows) > 0,
        }

    def get(self, request, pk):
        task = get_object_or_404(
            InjectionTask.objects.prefetch_related(
                'mold_requirements__mold', 'mold_requirements__formula_details__formula',
            ),
            pk=pk,
        )
        matrix_ctx = self._build_matrix_context(task)
        return render(request, self.template_name, {
            'injection_task': task,
            'form': InjectionCompleteForm(instance=task),
            'mold_matrix_formulas': matrix_ctx['formulas'],
            'mold_matrix_rows': matrix_ctx['matrix_rows'],
            'is_inventory_source': matrix_ctx['is_inventory_source'],
            'has_mold_requirements': matrix_ctx['has_mold_requirements'],
        })

    def post(self, request, pk):
        task = get_object_or_404(
            InjectionTask.objects.prefetch_related(
                'mold_requirements__mold', 'mold_requirements__formula_details__formula',
            ),
            pk=pk,
        )
        if task.status != 'IN_PROGRESS':
            messages.warning(request, '当前任务状态不允许完成')
            return redirect('mold_injection:task_detail', pk=pk)

        form = InjectionCompleteForm(request.POST, instance=task)
        if not form.is_valid():
            matrix_ctx = self._build_matrix_context(task)
            return render(request, self.template_name, {
                'injection_task': task,
                'form': form,
                'mold_matrix_formulas': matrix_ctx['formulas'],
                'mold_matrix_rows': matrix_ctx['matrix_rows'],
                'is_inventory_source': matrix_ctx['is_inventory_source'],
                'has_mold_requirements': matrix_ctx['has_mold_requirements'],
            })

        specimen_outputs = InjectionTaskService.parse_specimen_outputs(task, request.POST)
        task.remark = form.cleaned_data.get('remark', '')
        try:
            InjectionTaskService.complete_task(task, request.user, specimen_outputs)
            messages.success(request, '注塑任务已完成，样条已入库')
        except InvalidStateTransition as e:
            logger.exception(f"Injection complete failed: pk={pk}")
            messages.error(request, f'注塑任务完成失败：{e}')
        return redirect('mold_injection:task_detail', pk=pk)
