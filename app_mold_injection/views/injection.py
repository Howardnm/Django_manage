import logging

from django.db.models import Count
from django.views.generic import ListView, DetailView, View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from app_mold_injection.mixins import InjectionTaskAccessMixin
from app_trial_production.mixins import RndAccessMixin
from app_mold_injection.models import InjectionTask, MoldType
from app_mold_injection.forms import InjectionCompleteForm
from app_mold_injection.services import InjectionTaskService
from app_trial_production.services.sample_service import SampleInventoryService
from app_trial_production.models import ProductionOrder

logger = logging.getLogger(__name__)


class InjectionTaskListView(InjectionTaskAccessMixin, ListView):
    """注塑任务列表"""
    model = InjectionTask
    template_name = 'apps/app_mold_injection/injection/list.html'
    context_object_name = 'injection_tasks'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        if qs is None:
            qs = self.model.objects.all()
        return qs.select_related(
            'production_order', 'operator', 'sample_inventory',
        ).prefetch_related(
            'mold_requirements__mold',
        ).annotate(
            mold_count=Count('mold_requirements'),
        ).order_by('-created_at')


class InjectionCreateView(InjectionTaskAccessMixin, View):
    """渠道A：从排产工单创建注塑任务"""
    template_name = 'apps/app_mold_injection/injection/form.html'

    def _resolve_order(self):
        if not hasattr(self, '_order'):
            self._order = get_object_or_404(ProductionOrder, pk=self.kwargs.get('order_pk'))
            if self._order.project:
                RndAccessMixin.check_project_ownership(
                    self._order.project, self.request.user)
        return self._order

    def get(self, request, *args, **kwargs):
        order = self._resolve_order()
        from app_formula.models import LabFormula
        formulas = LabFormula.objects.filter(
            code=order.trial_code, project=order.project,
        ).order_by('version')
        return render(request, self.template_name, {
            'production_order': order,
            'mold_types': MoldType.objects.filter(status='AVAILABLE').order_by('mold_code'),
            'formulas': formulas,
        })

    def post(self, request, *args, **kwargs):
        order = self._resolve_order()
        from app_formula.models import LabFormula
        formulas = list(LabFormula.objects.filter(
            code=order.trial_code, project=order.project,
        ).order_by('version'))

        mold_requirements = []
        mold_count = int(request.POST.get('mold_count', 0))
        for i in range(mold_count):
            mold_id = request.POST.get(f'mold_{i}')
            if not mold_id:
                continue
            for formula in formulas:
                qty_val = request.POST.get(f'variant_qty_{i}_{formula.pk}', '0')
                try:
                    qty = int(qty_val)
                except (ValueError, TypeError):
                    qty = 0
                if qty > 0:
                    mold_requirements.append({
                        'mold_id': int(mold_id),
                        'formula_id': formula.pk,
                        'specimen_quantity': qty,
                    })

        task = InjectionTaskService.create_from_order(
            production_order=order,
            operator_id=request.POST.get('operator') or None,
            injection_params_note=request.POST.get('injection_params_note', ''),
            mold_requirements=mold_requirements,
        )
        messages.success(request, '注塑任务已创建')
        return redirect('mold_injection:task_detail', pk=task.pk)


class InjectionCreateFromInventoryView(InjectionTaskAccessMixin, View):
    """渠道B：从样品库取料创建独立注塑任务"""
    template_name = 'apps/app_mold_injection/injection/form_from_inventory.html'

    def get(self, request):
        available = SampleInventoryService.get_available_for_injection()
        return render(request, self.template_name, {
            'available_samples': available,
            'mold_types': MoldType.objects.filter(status='AVAILABLE').order_by('mold_code'),
        })

    def post(self, request):
        sample_id = request.POST.get('sample_inventory')
        sample = get_object_or_404(
            SampleInventoryService.get_available_for_injection(), pk=sample_id)
        project_id = request.POST.get('source_project') or None

        mold_requirements = []
        mold_count = int(request.POST.get('mold_count', 0))
        for i in range(mold_count):
            mold_id = request.POST.get(f'mold_{i}')
            qty = request.POST.get(f'qty_{i}', '0')
            if mold_id and int(qty) > 0:
                mold_requirements.append({
                    'mold_id': int(mold_id),
                    'formula_id': None,
                    'specimen_quantity': int(qty),
                })

        from app_project.models import Project
        project = None
        if project_id:
            project = get_object_or_404(Project, pk=project_id)

        task = InjectionTaskService.create_from_inventory(
            sample_inventory=sample,
            project=project,
            operator_id=request.POST.get('operator') or None,
            injection_params_note=request.POST.get('injection_params_note', ''),
            mold_requirements=mold_requirements,
        )
        messages.success(request, '独立注塑任务已创建')
        return redirect('mold_injection:task_detail', pk=task.pk)


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

        # --- 构建模具 x 配方矩阵 ---
        mold_requirements = task.mold_requirements.all()

        # 收集所有不重复的配方版本（排序列）
        formula_map = {}  # formula_id -> formula
        for req in mold_requirements:
            for detail in req.formula_details.all():
                if detail.formula_id and detail.formula_id not in formula_map:
                    formula_map[detail.formula_id] = detail.formula
        formulas = sorted(formula_map.values(), key=lambda f: f.version)

        # 构建每行的数量映射
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

        ctx['mold_matrix_formulas'] = formulas
        ctx['mold_matrix_rows'] = matrix_rows
        ctx['has_mold_requirements'] = len(matrix_rows) > 0

        ctx['show_start_btn'] = task.status == 'PENDING'
        ctx['show_complete_btn'] = task.status == 'IN_PROGRESS'
        ctx['has_output_specimens'] = task.output_specimens.exists()
        ctx['source_css_class'] = 'purple' if task.source == 'INVENTORY' else 'cyan'
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
        except Exception:
            logger.exception(f"Injection start failed: pk={pk}")
            messages.error(request, '系统错误，请稍后重试')
        return redirect('mold_injection:task_detail', pk=pk)


class InjectionCompleteView(InjectionTaskAccessMixin, View):
    """完成注塑任务 — 含样条产出"""
    template_name = 'apps/app_mold_injection/injection/complete.html'

    @staticmethod
    def _build_matrix_context(task):
        """构建模具 × 配方矩阵上下文，供 GET 和 POST(form invalid) 共用。"""
        mold_requirements = task.mold_requirements.all()

        formula_map = {}
        for req in mold_requirements:
            for detail in req.formula_details.all():
                if detail.formula_id and detail.formula_id not in formula_map:
                    formula_map[detail.formula_id] = detail.formula
        formulas = sorted(formula_map.values(), key=lambda f: f.version)
        is_inventory_source = (task.source == InjectionTask.Source.INVENTORY)

        matrix_rows = []
        for req in mold_requirements:
            qty_map = {}
            for detail in req.formula_details.all():
                key = detail.formula_id if detail.formula_id else 'none'
                qty_map[key] = detail.specimen_quantity

            if formulas:
                cells = [
                    {'formula': f, 'formula_key': f.pk, 'planned_qty': qty_map.get(f.pk, 0)}
                    for f in formulas
                ]
            else:
                cells = [
                    {'formula': None, 'formula_key': 'none', 'planned_qty': qty_map.get('none', 0)}
                ]

            matrix_rows.append({'mold': req.mold, 'cells': cells})

        return {
            'formulas': formulas,
            'matrix_rows': matrix_rows,
            'is_inventory_source': is_inventory_source,
            'has_mold_requirements': mold_requirements.exists(),
        }

    @staticmethod
    def _parse_specimen_outputs(task, post_data):
        """从矩阵 POST 数据解析样条产出记录。

        遍历 task.mold_requirements 及其 formula_details，
        提取每个 (模具, 配方版本) 单元格的产出/合格数量，
        结合每行的存放位置和批次标签。
        """
        specimen_outputs = []
        for req in task.mold_requirements.all().select_related('mold').prefetch_related('formula_details'):
            location = post_data.get(f'location_{req.mold_id}', '').strip()
            batch = post_data.get(f'batch_{req.mold_id}', '').strip()
            for detail in req.formula_details.all():
                fid = str(detail.formula_id) if detail.formula_id else 'none'
                try:
                    qty = int(post_data.get(f'qty_{req.mold_id}_{fid}', '0'))
                except (ValueError, TypeError):
                    qty = 0
                if qty <= 0:
                    continue
                try:
                    qualified = int(post_data.get(f'qualified_{req.mold_id}_{fid}', '0'))
                except (ValueError, TypeError):
                    qualified = 0
                specimen_outputs.append({
                    'mold_id': req.mold_id,
                    'specimen_count': qty,
                    'specimen_qualified': qualified,
                    'storage_location': location,
                    'batch_label': batch,
                    'formula_id': detail.formula_id,
                })
        return specimen_outputs

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

        specimen_outputs = self._parse_specimen_outputs(task, request.POST)
        task.remark = form.cleaned_data.get('remark', '')
        try:
            InjectionTaskService.complete_task(task, request.user, specimen_outputs)
            messages.success(request, '注塑任务已完成，样条已入库')
        except Exception:
            logger.exception(f"Injection complete failed: pk={pk}")
            messages.error(request, '系统错误，请稍后重试')
        return redirect('mold_injection:task_detail', pk=pk)
