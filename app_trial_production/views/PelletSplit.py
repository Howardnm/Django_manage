import logging
import re
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import View

from app_trial_production.mixins import ExtrusionTaskAccessMixin
from app_trial_production.services import ExtrusionTaskService, ProductionOrderService
from app_trial_production.models import ExtrusionTask, ProductionOrder

logger = logging.getLogger(__name__)

# 与 ProductionOrderFormulaDetail 的 Decimal(max_digits=10, decimal_places=2) 对齐。
# 模板 input name 必须与这两个函数一致：finished_pellet_kg_<pk> / specimen_pellet_kg_<pk>
_KG_QUANT = Decimal('0.01')
_KG_PATTERN = re.compile(r'^\d{1,8}(?:\.\d{1,2})?$')


def _finished_field(detail_pk):
    return f'finished_pellet_kg_{detail_pk}'


def _specimen_field(detail_pk):
    return f'specimen_pellet_kg_{detail_pk}'


def _parse_kg(raw):
    """必填，且为不小于 0、最多两位小数的数字。失败返回 (None, 错误文案)。"""
    text = '' if raw is None else str(raw).strip()
    if not text:
        return None, '必填'
    if not _KG_PATTERN.fullmatch(text):
        return None, '须为不小于 0 的数字，最多两位小数'
    return Decimal(text).quantize(_KG_QUANT), ''


def _format_kg(value):
    return format(Decimal(value).quantize(_KG_QUANT), 'f')


class PelletSplitView(ExtrusionTaskAccessMixin, View):
    """产量登记 — 挤出完成后填写每个配方版本的成品颗粒与样条颗粒。"""

    template_name = 'apps/app_trial_production/pellet/split.html'

    def _resolve_order(self, pk):
        if not hasattr(self, '_order'):
            self._order = get_object_or_404(
                ProductionOrder.objects.select_related('extrusion_task'),
                pk=pk,
            )
        return self._order

    def _formula_details(self, order):
        return list(
            order.formula_details.select_related('formula').order_by('formula__version', 'pk')
        )

    def _in_progress_task_or_redirect(self, request, order):
        task = order.extrusion_task if hasattr(order, 'extrusion_task') else None
        if task is None or task.status != ExtrusionTask.Status.IN_PROGRESS:
            messages.warning(request, '挤出任务未开始，不能完成挤出')
            return None, redirect('trial_order_detail', pk=order.pk)
        return task, None

    def _bind(self, details, data=None):
        """回显公斤数。POST 时校验，并把行级错误挂到明细上供卡片读取。"""
        valid = True
        for fd in details:
            if data is None:
                fd.finished_pellet_input = _format_kg(fd.finished_pellet_kg)
                fd.specimen_pellet_input = _format_kg(fd.specimen_pellet_kg)
                fd.finished_pellet_error = ''
                fd.specimen_pellet_error = ''
                continue
            finished_raw = data.get(_finished_field(fd.pk), '')
            specimen_raw = data.get(_specimen_field(fd.pk), '')
            fd.finished_pellet_input = str(finished_raw).strip()
            fd.specimen_pellet_input = str(specimen_raw).strip()
            finished, finished_error = _parse_kg(fd.finished_pellet_input)
            specimen, specimen_error = _parse_kg(fd.specimen_pellet_input)
            fd.finished_pellet_error = finished_error
            fd.specimen_pellet_error = specimen_error
            fd.finished_pellet_value = finished
            fd.specimen_pellet_value = specimen
            if finished_error or specimen_error:
                valid = False
        return valid

    def _render(self, request, order, details):
        task = order.extrusion_task if hasattr(order, 'extrusion_task') else None
        return render(request, self.template_name, {
            'production_order': order,
            'formula_details': details,
            'extrusion_task': task,
        })

    def get(self, request, pk):
        order = self._resolve_order(pk)
        _task, bounce = self._in_progress_task_or_redirect(request, order)
        if bounce:
            return bounce
        details = self._formula_details(order)
        self._bind(details)
        return self._render(request, order, details)

    def post(self, request, pk):
        order = self._resolve_order(pk)
        task, bounce = self._in_progress_task_or_redirect(request, order)
        if bounce:
            return bounce
        if task.operator_id and task.operator_id != request.user.pk and not request.user.is_superuser:
            messages.error(request, '您不是该任务分配的挤出操作员')
            return redirect('trial_order_detail', pk=order.pk)

        details = self._formula_details(order)
        if not details:
            messages.warning(request, '该工单没有配方明细，无法登记产量')
            return self._render(request, order, details)

        if not self._bind(details, request.POST):
            messages.error(request, '请修正标红的产量后再提交')
            return self._render(request, order, details)

        try:
            with transaction.atomic():
                for fd in details:
                    fd.finished_pellet_kg = fd.finished_pellet_value
                    fd.specimen_pellet_kg = fd.specimen_pellet_value
                    fd.save(update_fields=['finished_pellet_kg', 'specimen_pellet_kg'])
                ProductionOrderService.record_actual_quantity(order)
                ExtrusionTaskService.complete_task(task, request.user)
        except Exception:
            logger.exception('Yield register failed for order %s', order.pk)
            messages.error(request, '完成挤出失败，请稍后重试')
            return self._render(request, order, details)

        messages.success(request, '挤出已完成')
        return redirect('trial_order_detail', pk=order.pk)
