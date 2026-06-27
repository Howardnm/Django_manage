import logging

from django.db.models import Q
from django.http import JsonResponse
from django.views.generic import ListView, DetailView, View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone

from app_trial_production.mixins import SampleInventoryAccessMixin
from app_trial_production.models import SampleInventory
from app_trial_production.filters import SampleInventoryFilter
from app_trial_production.forms import SapEntryForm
from app_trial_production.services import SampleInventoryService

logger = logging.getLogger(__name__)


class SampleInventoryListView(SampleInventoryAccessMixin, ListView):
    """
    统一样品库存列表页 — 平铺表格 + 多维度筛选。

    取消旧版 PELLET/SPECIMEN Tab 切换，
    type/sub_type 改为 filter 下拉选择，支持组合筛选。
    """
    model = SampleInventory
    template_name = 'apps/app_trial_production/sample/inventory.html'
    context_object_name = 'samples'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset()
        if qs is None:
            qs = self.model.objects.all()

        # 应用 FilterSet
        self.filter = SampleInventoryFilter(self.request.GET, queryset=qs)
        qs = self.filter.qs

        # 首页默认：在实验房 + 颗粒 + 成品颗粒
        # 若用户已主动切换 type，则不再强加 sub_type 默认值（"全部颗粒"按钮生效）
        status_param = self.request.GET.get('status', '')
        if status_param == 'ALL':
            qs = qs.exclude(status=SampleInventory.Status.CONSUMED)
        elif not status_param:
            qs = qs.filter(status=SampleInventory.Status.IN_LAB)

        if not self.request.GET.get('type'):
            qs = qs.filter(type=SampleInventory.Type.PELLET)
            if not self.request.GET.get('sub_type'):
                qs = qs.filter(sub_type=SampleInventory.SubType.FINISHED)

        return qs.select_related(
            'production_order',
            'production_order__project',
            'formula',
            'mold',
            'injection_task',
        ).prefetch_related(
            'injection_tasks',
        ).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filter
        # Tab 状态（首页预选：在实验房 + 颗粒 + 成品颗粒）
        context['current_type'] = self.request.GET.get('type', 'PELLET')
        context['current_sub_type'] = self.request.GET.get('sub_type',
            'FINISHED' if not self.request.GET.get('type') else '')
        context['current_status'] = self.request.GET.get('status', 'IN_LAB')
        return context


class SampleInventoryDetailView(SampleInventoryAccessMixin, DetailView):
    """
    样品详情页 — 生命周期时间线 + 关联样品。

    展示样品从创建到消耗/入库的完整生命周期，
    以及同实验单号下的关联样品。
    """
    model = SampleInventory
    template_name = 'apps/app_trial_production/sample/detail.html'
    context_object_name = 'sample'

    def get_queryset(self):
        qs = super().get_queryset()
        if qs is None:
            return self.model.objects.all()
        return qs.select_related(
            'production_order',
            'production_order__project',
            'production_order__extrusion_task',
            'formula',
            'injection_task',
            'injection_task__production_order',
            'mold',
        ).prefetch_related(
            'injection_tasks',
        )

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sample = self.object

        # 生命周期时间线
        context['lifecycle'] = SampleInventoryService.get_lifecycle(sample)

        # 同排产工单关联样品（排除自身 + 已消耗，最多 10 条）
        related_qs = SampleInventory.objects.filter(
            production_order=sample.production_order,
        ).exclude(
            pk=sample.pk,
        ).exclude(
            status=SampleInventory.Status.CONSUMED,
        ).select_related(
            'formula', 'mold',
        ).order_by('-created_at')
        context['related_samples'] = related_qs[:10]
        context['related_has_more'] = related_qs.count() > 10

        # 下游注塑任务（预留或已消耗的待打样颗粒）
        if sample.is_pellet and sample.sub_type == SampleInventory.SubType.FOR_INJECTION:
            if sample.injection_task:
                context['downstream_injection'] = sample.injection_task

        # 上游注塑任务（产出该样条的注塑任务）
        if sample.is_specimen and sample.injection_task:
            context['upstream_injection'] = sample.injection_task

        context['can_sap_entry'] = sample.can_sap_entry
        return context


class SapEntryView(SampleInventoryAccessMixin, View):
    """
    SAP 入库操作 — 支持单样品 + 批量两种模式。

    单样品：  /samples/<pk>/sap-entry/
    批量：    /samples/batch/sap-entry/?ids=1,2,3
    """
    template_name = 'apps/app_trial_production/sample/sap_entry.html'

    # ── 单样品模式 ──────────────────────────────────────────

    def _get_single(self, request, pk):
        sample = get_object_or_404(SampleInventory, pk=pk)
        if not sample.can_sap_entry:
            messages.warning(request, '当前样品状态不允许SAP入库')
            return redirect('trial_sample_detail', pk=pk)

        form = SapEntryForm(instance=sample)
        return render(request, self.template_name, {
            'samples': [sample],
            'form': form,
            'is_batch': False,
        })

    def _post_single(self, request, pk):
        sample = get_object_or_404(SampleInventory, pk=pk)
        if not sample.can_sap_entry:
            messages.warning(request, '当前样品状态不允许SAP入库')
            return redirect('trial_sample_detail', pk=pk)

        form = SapEntryForm(request.POST, instance=sample)
        if form.is_valid():
            try:
                SampleInventoryService.sap_warehouse_entry(
                    sample, form.cleaned_data, request.user,
                )
                messages.success(request, f'样品 [{sample.trial_code}] 已入SAP仓库')
                return redirect('trial_sample_detail', pk=pk)
            except Exception:
                logger.exception(f"SAP entry failed for sample {sample.pk}")
                messages.error(request, 'SAP入库操作失败，请稍后重试')

        return render(request, self.template_name, {
            'samples': [sample],
            'form': form,
            'is_batch': False,
        })

    # ── 批量模式 ────────────────────────────────────────────

    def _get_batch(self, request):
        ids = self._parse_ids(request)
        if not ids:
            messages.warning(request, '请先选择需要入库的样品')
            return redirect('trial_sample_list')

        # 仅成品颗粒允许入SAP（待打样颗粒/样条会被后续工序消耗）
        samples = SampleInventory.objects.filter(
            pk__in=ids,
            type=SampleInventory.Type.PELLET,
            sub_type=SampleInventory.SubType.FINISHED,
            status=SampleInventory.Status.IN_LAB,
        ).select_related('formula', 'production_order').order_by('-created_at')

        if not samples:
            messages.warning(request, '所选样品均不满足入库条件（仅"在实验房"的"成品颗粒"允许入SAP）')
            return redirect('trial_sample_list')

        form = SapEntryForm()
        return render(request, self.template_name, {
            'samples': samples,
            'form': form,
            'is_batch': True,
            'sample_ids': ','.join(str(s.pk) for s in samples),
        })

    def _post_batch(self, request):
        ids = self._parse_ids(request)
        if not ids:
            messages.warning(request, '请先选择需要入库的样品')
            return redirect('trial_sample_list')

        # 仅成品颗粒允许入SAP（待打样颗粒/样条会被后续工序消耗）
        samples = SampleInventory.objects.filter(
            pk__in=ids,
            type=SampleInventory.Type.PELLET,
            sub_type=SampleInventory.SubType.FINISHED,
            status=SampleInventory.Status.IN_LAB,
        ).select_related('formula', 'production_order')

        if not samples:
            messages.warning(request, '所选样品均不满足入库条件（仅"在实验房"的"成品颗粒"允许入SAP）')
            return redirect('trial_sample_list')

        form = SapEntryForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {
                'samples': samples,
                'form': form,
                'is_batch': True,
                'sample_ids': ','.join(str(s.pk) for s in samples),
            })

        success = 0
        failed = 0
        for sample in samples:
            try:
                SampleInventoryService.sap_warehouse_entry(
                    sample, form.cleaned_data, request.user,
                )
                success += 1
            except Exception:
                logger.exception(f"Batch SAP entry failed for sample {sample.pk}")
                failed += 1

        if success:
            messages.success(request, f'已成功入库 {success} 条样品')
        if failed:
            messages.error(request, f'{failed} 条样品入库失败，请检查后重试')

        return redirect('trial_sample_list')

    # ── 工具方法 ────────────────────────────────────────────

    @staticmethod
    def _parse_ids(request):
        """从 GET/POST 中提取样品 ID 列表"""
        raw = request.GET.get('ids', '') or request.POST.get('ids', '')
        if not raw:
            return []
        try:
            return [int(x) for x in raw.split(',') if x.strip()]
        except (ValueError, TypeError):
            return []

    # ── 路由分发 ────────────────────────────────────────────

    def get(self, request, pk=None):
        if pk is not None:
            return self._get_single(request, pk)
        return self._get_batch(request)

    def post(self, request, pk=None):
        if pk is not None:
            return self._post_single(request, pk)
        return self._post_batch(request)


class SampleInventoryApiView(SampleInventoryAccessMixin, View):
    """
    JSON API — 供 TomSelect 远程搜索 + 检查批量操作可行性。

    ?q=xxx      全文检索（trial_code / batch_number）
    ?action=    可选: 'check_batch' 检查指定 IDs 的可操作状态
    """

    def get(self, request):
        q = request.GET.get('q', '').strip()
        action = request.GET.get('action', '')

        if action == 'check_batch':
            ids_raw = request.GET.get('ids', '')
            try:
                ids = [int(x) for x in ids_raw.split(',') if x.strip()]
            except (ValueError, TypeError):
                return JsonResponse({'valid': False, 'count': 0})

            # 仅成品颗粒允许入SAP
            count = SampleInventory.objects.filter(
                pk__in=ids,
                type=SampleInventory.Type.PELLET,
                sub_type=SampleInventory.SubType.FINISHED,
                status=SampleInventory.Status.IN_LAB,
            ).count()
            return JsonResponse({'valid': count > 0, 'count': count})

        # 默认：TomSelect 搜索
        if not q:
            return JsonResponse({'results': []})

        results = SampleInventory.objects.filter(
            Q(trial_code__icontains=q) |
            Q(batch_number__icontains=q)
        ).values('id', 'trial_code', 'batch_number', 'type', 'sub_type')[:20]

        return JsonResponse({'results': list(results)})
