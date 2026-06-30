import logging

from django.db.models import Q
from django.http import JsonResponse
from django.views.generic import DetailView, View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone

from app_trial_production.mixins import SampleInventoryAccessMixin
from app_trial_production.models import SampleInventory
from app_trial_production.filters import SampleInventoryFilter
from app_trial_production.forms import SapEntryForm
from app_trial_production.services import SampleInventoryService

logger = logging.getLogger(__name__)


class SampleInventoryListView(SampleInventoryAccessMixin, View):
    """成品颗粒库存列表页 — 排产模块管辖（PELLET + FINISHED），按工单分组表格呈现。"""

    template_name = 'apps/app_trial_production/sample/inventory.html'
    paginate_by = 20

    # ── 获取筛选后的样品 QuerySet ──
    def _get_filtered_qs(self, request):
        qs = SampleInventory.objects.select_related(
            'production_order',
            'production_order__project',
            'formula',
            'mold',
            'injection_task',
        ).prefetch_related('injection_tasks')

        # Hard-code 范围：排产模块只管控成品颗粒
        qs = qs.filter(type=SampleInventory.Type.PELLET, sub_type=SampleInventory.SubType.FINISHED)

        self.filter = SampleInventoryFilter(request.GET, queryset=qs)
        qs = self.filter.qs

        # 首页默认：在实验房
        status_param = request.GET.get('status', '')
        if status_param == 'ALL':
            pass  # 显示全部状态（含 SAP_STORED）
        elif not status_param:
            qs = qs.filter(status=SampleInventory.Status.IN_LAB)

        return qs.order_by('-created_at')

    def get(self, request):
        samples_qs = self._get_filtered_qs(request)
        order_groups, orphan_samples = SampleInventoryService.build_order_groups(samples_qs)

        # 当前激活的数据集：独立样品 Tab 时显示孤儿样品，否则显示工单分组
        has_order = request.GET.get('has_order', '')
        show_orphan_only = (has_order == 'false')

        from django.core.paginator import Paginator
        page_num = int(request.GET.get('page', 1))

        if show_orphan_only:
            paginator = Paginator(orphan_samples, self.paginate_by)
            page_obj = paginator.get_page(page_num)
        else:
            paginator = Paginator(order_groups, self.paginate_by)
            page_obj = paginator.get_page(page_num)

        context = {
            'order_groups': order_groups,
            'orphan_samples': orphan_samples,
            'page_obj': page_obj,
            'paginator': paginator,
            'filter': self.filter,
            'current_status': request.GET.get('status', 'IN_LAB'),
            'show_orphan_only': show_orphan_only,
            'orphan_count': len(orphan_samples),
        }
        return render(request, self.template_name, context)


class SampleInventoryCreateView(SampleInventoryAccessMixin, View):
    """独立成品颗粒创建 — 不关联任何工单，type/sub_type 固定为 PELLET+FINISHED"""

    template_name = 'apps/app_trial_production/sample/create.html'

    def get(self, request):
        from app_trial_production.forms import StandaloneSampleForm
        form = StandaloneSampleForm(initial={
            'type': 'PELLET',
            'sub_type': 'FINISHED',
        })
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        from app_trial_production.forms import StandaloneSampleForm

        form = StandaloneSampleForm(request.POST)
        if form.is_valid():
            data = {
                'type': 'PELLET',
                'sub_type': 'FINISHED',
                'formula_id': form.cleaned_data.get('formula'),
                'trial_code': form.cleaned_data.get('trial_code', ''),
                'quantity': form.cleaned_data.get('quantity'),
                'specimen_count': form.cleaned_data.get('specimen_count'),
                'specimen_qualified': form.cleaned_data.get('specimen_qualified') or 0,
                'storage_location': form.cleaned_data.get('storage_location', ''),
                'packaging_desc': form.cleaned_data.get('packaging_desc', ''),
                'mold_id': form.cleaned_data.get('mold'),
                'batch_label': form.cleaned_data.get('batch_label', ''),
            }
            sample = SampleInventoryService.create_standalone_sample(data)
            messages.success(request, f'样品 [{sample.trial_code or sample.pk}] 已创建')
            return redirect('trial_sample_list')

        return render(request, self.template_name, {'form': form})


class OrderSampleDetailView(SampleInventoryAccessMixin, View):
    """工单维度样品详情页 — 按模块来源过滤样品范围 + 表格批量 SAP 入库（仅排产模块）。"""

    template_name = 'apps/app_trial_production/sample/order_detail.html'

    # ── 模块范围定义 ─────────────────────────────────────────
    MODULE_FILTERS = {
        'trial': {'type': 'PELLET', 'sub_type': 'FINISHED'},
        'mold_injection': None,  # 特殊处理: (PELLET+FOR_INJECTION) OR (SPECIMEN+FOR_TESTING)
        'material_testing': {'type': 'SPECIMEN'},
    }

    MODULE_CONFIG = {
        'trial': {
            'list_url': 'trial_sample_list',
            'list_name': '成品颗粒库存',
            'breadcrumb_parent_url': 'trial_dashboard',
            'breadcrumb_parent_name': '排产总览',
        },
        'mold_injection': {
            'list_url': 'mold_injection:sample_list',
            'list_name': '样品库存',
            'breadcrumb_parent_url': 'mold_injection:task_list',
            'breadcrumb_parent_name': '模具注塑中心',
        },
        'material_testing': {
            'list_url': 'material_testing:specimens',
            'list_name': '样条库存',
            'breadcrumb_parent_url': 'material_testing:list',
            'breadcrumb_parent_name': '材料测试中心',
        },
    }

    @classmethod
    def _filter_by_module(cls, samples_qs, from_module):
        """按模块范围过滤样品 QuerySet。"""
        filter_def = cls.MODULE_FILTERS.get(from_module, cls.MODULE_FILTERS['trial'])
        if filter_def is None and from_module == 'mold_injection':
            from django.db.models import Q
            return samples_qs.filter(
                Q(type='PELLET', sub_type='FOR_INJECTION') |
                Q(type='SPECIMEN', sub_type='FOR_TESTING')
            )
        if filter_def:
            return samples_qs.filter(**filter_def)
        return samples_qs

    @classmethod
    def _get_module_context(cls, from_module):
        """获取模块上下文（面包屑 + 返回链接）。"""
        return cls.MODULE_CONFIG.get(from_module, cls.MODULE_CONFIG['trial'])

    def _get_order(self, order_pk):
        from app_trial_production.models import ProductionOrder

        return get_object_or_404(
            ProductionOrder.objects.select_related('project'),
            pk=order_pk,
        )

    def get(self, request, order_pk):
        order = self._get_order(order_pk)
        from_module = request.GET.get('from', 'trial')

        # 按模块范围过滤样品
        base_qs = SampleInventory.objects.filter(
            production_order=order,
        ).select_related(
            'formula', 'mold', 'injection_task',
        ).order_by('-created_at')

        filtered_qs = self._filter_by_module(base_qs, from_module)
        all_samples = list(filtered_qs)

        # SAP 入库仅对排产模块（成品颗粒）开放
        sap_eligible = []
        if from_module == 'trial':
            sap_eligible = [
                s for s in all_samples
                if s.type == 'PELLET' and s.sub_type == 'FINISHED' and s.status == 'IN_LAB'
            ]

        sap_material_code = SampleInventoryService.get_order_sap_material_code(order)

        context = {
            'order': order,
            'all_samples': all_samples,
            'sap_eligible': sap_eligible,
            'sap_material_code': sap_material_code,
            'module': self._get_module_context(from_module),
            'from_module': from_module,
        }

        if sap_eligible:
            from django.forms import modelformset_factory
            SapFormsetClass = modelformset_factory(
                SampleInventory, form=SapEntryForm, extra=0,
            )
            formset = SapFormsetClass(
                queryset=SampleInventory.objects.filter(
                    pk__in=[s.pk for s in sap_eligible],
                ),
                prefix='sap',
            )

            today = timezone.now().date()
            for form in formset.forms:
                sample = form.instance
                form.initial.update({
                    'sap_material_code': sap_material_code,
                    'sap_batch_number': sample.batch_number,
                    'sap_warehouse_date': today,
                    'sap_storage_location': sample.storage_location,
                })
            context['formset'] = formset

        return render(request, self.template_name, context)

    def post(self, request, order_pk):
        order = self._get_order(order_pk)
        from_module = request.GET.get('from', 'trial')

        sap_eligible = SampleInventory.objects.filter(
            production_order=order,
            type='PELLET',
            sub_type='FINISHED',
            status='IN_LAB',
        )

        if not sap_eligible.exists():
            messages.warning(request, '没有可入库的样品')
            return redirect('trial_sample_order_detail', order_pk=order_pk)

        from django.forms import modelformset_factory
        SapFormsetClass = modelformset_factory(
            SampleInventory, form=SapEntryForm, extra=0,
        )
        formset = SapFormsetClass(
            data=request.POST,
            queryset=sap_eligible,
            prefix='sap',
        )

        if formset.is_valid():
            success = 0
            failed = 0
            for form in formset.forms:
                if form.cleaned_data.get('DELETE', False):
                    continue
                sap_code = form.cleaned_data.get('sap_material_code', '')
                if not sap_code:
                    continue
                sample = form.instance
                try:
                    SampleInventoryService.sap_warehouse_entry(
                        sample, form.cleaned_data, request.user,
                    )
                    success += 1
                except Exception:
                    logger.exception(
                        f"Order SAP entry failed for sample {sample.pk}"
                    )
                    failed += 1

            if success:
                messages.success(
                    request,
                    f'工单 [{order.code}] 已成功入库 {success} 条样品',
                )
            if failed:
                messages.error(request, f'{failed} 条样品入库失败，请检查后重试')

            return redirect(f'{request.path}?from={from_module}')

        # formset 验证失败，重新渲染
        base_qs = SampleInventory.objects.filter(
            production_order=order,
        ).select_related(
            'formula', 'mold', 'injection_task',
        ).order_by('-created_at')
        all_samples = list(self._filter_by_module(base_qs, from_module))
        sap_material_code = SampleInventoryService.get_order_sap_material_code(order)

        return render(request, self.template_name, {
            'order': order,
            'all_samples': all_samples,
            'sap_eligible': sap_eligible,
            'sap_material_code': sap_material_code,
            'formset': formset,
            'module': self._get_module_context(from_module),
            'from_module': from_module,
        })


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

        # ── 模块来源上下文（面包屑 + 返回链接） ──
        from_module = self.request.GET.get('from', 'trial')
        module_config = {
            'trial': {
                'list_url': 'trial_sample_list',
                'list_name': '成品颗粒库存',
                'breadcrumb_parent_url': 'trial_dashboard',
                'breadcrumb_parent_name': '排产总览',
            },
            'mold_injection': {
                'list_url': 'mold_injection:sample_list',
                'list_name': '样品库存',
                'breadcrumb_parent_url': 'mold_injection:task_list',
                'breadcrumb_parent_name': '模具注塑中心',
            },
            'material_testing': {
                'list_url': 'material_testing:specimens',
                'list_name': '样条库存',
                'breadcrumb_parent_url': 'material_testing:list',
                'breadcrumb_parent_name': '材料测试中心',
            },
        }
        context['module'] = module_config.get(from_module, module_config['trial'])

        # 生命周期时间线
        context['lifecycle'] = SampleInventoryService.get_lifecycle(sample)

        # 关联样品：仅显示与当前样品同类型+同子类型的（即属于同一模块管辖范围）
        related_qs = SampleInventory.objects.filter(
            production_order=sample.production_order,
            type=sample.type,
            sub_type=sample.sub_type,
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
        sample = get_object_or_404(
            SampleInventory.objects.select_related('formula__project__material'),
            pk=pk,
        )
        if not sample.can_sap_entry:
            messages.warning(request, '当前样品状态不允许SAP入库')
            return redirect('trial_sample_detail', pk=pk)

        # 沿 formula→project→material 链预填 SAP 物料号
        initial = {}
        sap_code = self._lookup_sap_code(sample)
        if sap_code:
            initial['sap_material_code'] = sap_code
        form = SapEntryForm(instance=sample, initial=initial)
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
        ).select_related('formula__project__material', 'production_order').order_by('-created_at')

        if not samples:
            messages.warning(request, '所选样品均不满足入库条件（仅"在实验房"的"成品颗粒"允许入SAP）')
            return redirect('trial_sample_list')

        # 若所有样品共享同一 SAP 物料号，则预填
        initial = {}
        sap_codes = {self._lookup_sap_code(s) for s in samples}
        sap_codes.discard('')
        if len(sap_codes) == 1:
            initial['sap_material_code'] = sap_codes.pop()
        form = SapEntryForm(initial=initial)
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
    def _lookup_sap_code(sample):
        """沿 formula→project→material 链查找 SAP 物料号，找不到返回空字符串"""
        if sample.formula and sample.formula.project and sample.formula.project.material:
            return sample.formula.project.material.sap_material_code or ''
        return ''

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
