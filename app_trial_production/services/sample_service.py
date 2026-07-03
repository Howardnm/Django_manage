import logging
from django.db import transaction

from django.utils import timezone

from app_trial_production.models import SampleInventory

logger = logging.getLogger(__name__)


class SampleInventoryService:
    """样品库存业务"""

    @staticmethod
    @transaction.atomic
    def create_pellet_batch(production_order, splits):
        """
        挤出后创建颗粒样品批次入库记录。

        同一工单 + 同一配方版本 → 同一批次号。
        批次号格式: {工单号}-V{配方版本}，例如 PO-2024-001-V1

        Args:
            production_order: ProductionOrder 实例
            splits: list of dict {
                formula_id, sub_type ('FINISHED'|'FOR_INJECTION'),
                quantity, packaging_desc, storage_location
            }

        Returns:
            list of SampleInventory instances
        """
        from app_formula.models import LabFormula

        # 预取所有配方版本号 + SAP物料号（沿 formula→project→material 链），避免逐个查询
        formula_ids = {s['formula_id'] for s in splits if s.get('formula_id')}
        formula_meta = LabFormula.objects.filter(pk__in=formula_ids).values_list(
            'pk', 'version', 'project__material__sap_material_code',
        )
        formula_version_map = {pk: version for pk, version, _ in formula_meta}
        formula_sap_map = {pk: sap or '' for pk, _, sap in formula_meta}

        # 按 formula_id 分组，同组共享同一 batch_number
        grouped = {}
        for split in splits:
            fid = split.get('formula_id')
            if fid:
                grouped.setdefault(fid, []).append(split)

        samples = []
        for formula_id, items in grouped.items():
            version = formula_version_map.get(formula_id, '?')
            batch_number = f"{production_order.code}-V{version}"
            sap_code = formula_sap_map.get(formula_id, '')

            for item in items:
                if not item.get('quantity') or float(item['quantity']) <= 0:
                    continue

                sample = SampleInventory.objects.create(
                    type='PELLET',
                    sub_type=item['sub_type'],
                    status='IN_LAB',
                    production_order=production_order,
                    formula_id=formula_id,
                    trial_code=production_order.trial_code,
                    batch_number=batch_number,
                    quantity=item['quantity'],
                    packaging_desc=item.get('packaging_desc', ''),
                    storage_location=item.get('storage_location', ''),
                    sap_material_code=sap_code,
                )
                samples.append(sample)

        # 按分拨明细的 KG 数量汇总更新工单实际产量
        total_kg = sum(float(s['quantity']) for s in splits if s.get('quantity'))
        if total_kg > 0:
            production_order.quantity_actual = total_kg
            production_order.save(update_fields=['quantity_actual', 'updated_at'])

        # 标记挤出任务颗粒分拨已完成
        ext = getattr(production_order, 'extrusion_task', None)
        if ext and not ext.pellet_split_completed:
            ext.pellet_split_completed = True
            ext.save(update_fields=['pellet_split_completed'])

        # 颗粒分拨完成 → 检查是否可推进工单（触发注塑/测试）
        from app_trial_production.services.order_service import ProductionOrderService
        ProductionOrderService.check_and_advance(production_order)

        batch_numbers = {s.batch_number for s in samples}
        logger.info(
            f"Created {len(samples)} pellet samples ({len(batch_numbers)} batches) "
            f"for order {production_order.code} (total={total_kg}kg)"
        )
        return samples

    @staticmethod
    @transaction.atomic
    def create_specimen_batch(injection_task, specimen_outputs):
        """
        注塑后创建样条样品批次入库记录。

        Args:
            injection_task: InjectionTask 实例
            specimen_outputs: list of dict {
                mold_id, specimen_count, specimen_qualified,
                storage_location, batch_label, formula_id
            }

        Returns:
            list of SampleInventory instances
        """
        samples = []
        trial_code = ''
        if injection_task.production_order:
            trial_code = injection_task.production_order.trial_code
        elif injection_task.sample_inventory:
            trial_code = injection_task.sample_inventory.trial_code

        for output in specimen_outputs:
            if not output.get('specimen_count') or int(output['specimen_count']) <= 0:
                continue

            sample = SampleInventory.objects.create(
                type='SPECIMEN',
                sub_type='FOR_TESTING',
                status='IN_LAB',
                production_order=injection_task.production_order,
                formula_id=output.get('formula_id'),
                trial_code=trial_code,
                specimen_count=output['specimen_count'],
                specimen_qualified=output.get('specimen_qualified', 0),
                storage_location=output.get('storage_location', ''),
                batch_label=output.get('batch_label', ''),
                injection_task=injection_task,
                mold_id=output.get('mold_id'),
            )
            samples.append(sample)

        logger.info(
            f"Created {len(samples)} specimen samples for injection task {injection_task.pk}"
        )
        return samples

    @staticmethod
    @transaction.atomic
    def sap_warehouse_entry(sample, sap_fields, user=None):
        """
        执行 SAP 入库操作 — 更新样品状态为已入SAP仓库。

        Args:
            sample: SampleInventory 实例
            sap_fields: dict {
                sap_material_code, sap_batch_number,
                sap_warehouse_date, sap_storage_location
            }
            user: 操作用户
        """
        if not sample.can_sap_entry:
            raise ValueError(f"样品 {sample} 当前状态不允许SAP入库")

        sample.sap_material_code = sap_fields.get('sap_material_code', '')
        sample.sap_batch_number = sap_fields.get('sap_batch_number', '')
        sample.sap_warehouse_date = sap_fields.get('sap_warehouse_date') or timezone.now().date()
        sample.sap_storage_location = sap_fields.get('sap_storage_location', '')
        sample.status = 'SAP_STORED'
        sample.save()

        logger.info(
            f"Sample {sample.pk} entered SAP warehouse "
            f"(material={sample.sap_material_code}, batch={sample.sap_batch_number})"
        )
        return sample

    @staticmethod
    def get_available_for_injection():
        """获取所有可用的待打样颗粒（供注塑取料列表）"""
        return SampleInventory.objects.filter(
            type='PELLET',
            sub_type='FOR_INJECTION',
            status='IN_LAB',
        ).select_related(
            'production_order', 'formula',
        ).order_by('-created_at')

    @staticmethod
    def get_lifecycle(sample):
        """构建单个样品的生命周期事件时间线。

        按时间顺序返回事件列表，每个事件标注是否为当前状态。

        Returns:
            list[dict] — [{label, description, timestamp, is_current, icon}]
        """
        events = []

        if sample.is_pellet:
            # 1) 工单创建
            if sample.production_order:
                events.append({
                    'label': '工单创建',
                    'description': str(sample.production_order),
                    'timestamp': sample.production_order.created_at,
                    'is_current': False,
                    'icon': 'ti ti-file-text',
                })

            # 2) 挤出完成
            if sample.production_order and hasattr(sample.production_order, 'extrusion_task'):
                ext = sample.production_order.extrusion_task
                if ext and ext.completed_at:
                    events.append({
                        'label': '挤出完成',
                        'description': f'挤出任务 (操作员: {ext.operator or "-"})',
                        'timestamp': ext.completed_at,
                        'is_current': False,
                        'icon': 'ti ti-tool',
                    })

            # 3) 颗粒分拨入库（当前，除非已消耗/已SAP）
            events.append({
                'label': '颗粒分拨入库',
                'description': (
                    f'{sample.quantity or 0}kg, {sample.get_sub_type_display()}'
                ),
                'timestamp': sample.created_at,
                'is_current': sample.status == SampleInventory.Status.IN_LAB,
                'icon': 'ti ti-package',
            })

            # 4) 待注塑消耗（FOR_INJECTION 已关联注塑任务但尚未消耗）
            if (sample.sub_type == SampleInventory.SubType.FOR_INJECTION
                    and sample.injection_task
                    and sample.status != SampleInventory.Status.CONSUMED):
                events.append({
                    'label': '待注塑消耗',
                    'description': f'预留工单注塑任务 #{sample.injection_task.pk}',
                    'timestamp': sample.injection_task.created_at,
                    'is_current': sample.status == SampleInventory.Status.IN_LAB,
                    'icon': 'ti ti-injection',
                })

            # 5) SAP 入库（成品颗粒）或 注塑消耗（FOR_INJECTION 已消耗）
            if sample.status == SampleInventory.Status.SAP_STORED:
                events.append({
                    'label': 'SAP入库',
                    'description': (
                        f'物料号: {sample.sap_material_code or "-"}, '
                        f'批次: {sample.sap_batch_number or "-"}'
                    ),
                    'timestamp': sample.sap_warehouse_date or sample.updated_at,
                    'is_current': True,
                    'icon': 'ti ti-building-warehouse',
                })

            # 6) 注塑消耗（FOR_INJECTION 已被消耗）
            if sample.status == SampleInventory.Status.CONSUMED:
                tasks = sample.injection_tasks.all()
                for task in tasks:
                    events.append({
                        'label': '注塑消耗',
                        'description': f'注塑任务 #{task.pk}',
                        'timestamp': task.created_at,
                        'is_current': True,
                        'icon': 'ti ti-injection',
                    })

        elif sample.is_specimen:
            # 1) 注塑任务
            if sample.injection_task:
                events.append({
                    'label': '注塑任务',
                    'description': f'注塑任务 #{sample.injection_task.pk}',
                    'timestamp': sample.injection_task.created_at,
                    'is_current': False,
                    'icon': 'ti ti-injection',
                })

            # 2) 样条入库
            events.append({
                'label': '样条入库',
                'description': (
                    f'{sample.specimen_count or 0}条'
                    f'（合格 {sample.specimen_qualified or 0}条）'
                ),
                'timestamp': sample.created_at,
                'is_current': sample.sub_type == SampleInventory.SubType.FOR_TESTING,
                'icon': 'ti ti-clipboard',
            })

            # 3) 测试完成
            if sample.sub_type == SampleInventory.SubType.TESTED:
                events.append({
                    'label': '测试完成',
                    'description': '已测试样条',
                    'timestamp': sample.updated_at,
                    'is_current': True,
                    'icon': 'ti ti-microscope',
                })

        return events

    @staticmethod
    def get_order_sap_material_code(production_order):
        """沿工单 trial_code→LabFormula→project→material 链查找 SAP 物料号。

        Args:
            production_order: ProductionOrder 实例

        Returns:
            str: 第一个非空 SAP 物料号，找不到返回空字符串
        """
        from app_formula.models import LabFormula

        if not production_order.trial_code:
            return ''

        formulas = LabFormula.objects.filter(
            code=production_order.trial_code,
            project__material__sap_material_code__gt='',
        ).select_related('project__material')[:1]

        for f in formulas:
            if f.project and f.project.material:
                return f.project.material.sap_material_code
        return ''

    @staticmethod
    def compute_orphan_summary(orphan_samples):
        """计算独立样品的汇总统计。

        Args:
            orphan_samples: list of SampleInventory

        Returns:
            dict with pellet/kg and specimen counts
        """
        summary = {
            'total': len(orphan_samples),
            'pellet_finished_count': 0,
            'pellet_finished_kg': 0.0,
            'pellet_finished_in_lab': 0,
            'pellet_for_injection_count': 0,
            'pellet_for_injection_kg': 0.0,
            'specimen_for_testing_count': 0,
            'specimen_tested_count': 0,
        }
        for s in orphan_samples:
            if s.type == 'PELLET':
                qty = float(s.quantity or 0)
                if s.sub_type == 'FINISHED':
                    summary['pellet_finished_count'] += 1
                    summary['pellet_finished_kg'] += qty
                    if s.status == 'IN_LAB':
                        summary['pellet_finished_in_lab'] += 1
                elif s.sub_type == 'FOR_INJECTION':
                    summary['pellet_for_injection_count'] += 1
                    summary['pellet_for_injection_kg'] += qty
            elif s.type == 'SPECIMEN':
                if s.sub_type == 'FOR_TESTING':
                    summary['specimen_for_testing_count'] += 1
                elif s.sub_type == 'TESTED':
                    summary['specimen_tested_count'] += 1
        return summary

    @staticmethod
    def get_order_sample_summaries(production_order_ids, sample_qs):
        """按工单汇总已筛选样品的统计信息。

        Args:
            production_order_ids: set/list of ProductionOrder pk
            sample_qs: QuerySet[SampleInventory] — 已应用筛选条件的样品 QuerySet

        Returns:
            dict: {order_id: {
                'total_samples': int,
                'pellet_finished_kg': Decimal,
                'pellet_for_injection_kg': Decimal,
                'specimen_for_testing_count': int,
                'specimen_tested_count': int,
                'active_status': str,  # 该工单组中最多见的非CONSUMED状态
            }}
        """
        from collections import Counter
        from django.db.models import Q

        summaries = {}
        if not production_order_ids:
            return summaries

        status_counter = {}

        for sample in sample_qs.select_related(None).prefetch_related(None):
            oid = sample.production_order_id
            if not oid or oid not in production_order_ids:
                continue
            if oid not in summaries:
                summaries[oid] = {
                    'total_samples': 0,
                    'pellet_finished_kg': 0,
                    'pellet_for_injection_kg': 0,
                    'specimen_for_testing_count': 0,
                    'specimen_tested_count': 0,
                    'pellet_finished_sap': 0,   # 已入SAP的成品颗粒数
                    'pellet_finished_in_lab': 0,  # 仍在实验房的成品颗粒数
                }
                status_counter[oid] = Counter()

            s = summaries[oid]
            s['total_samples'] += 1
            status_counter[oid][sample.status] += 1

            if sample.type == 'PELLET':
                qty = float(sample.quantity or 0)
                if sample.sub_type == 'FINISHED':
                    s['pellet_finished_kg'] += qty
                    if sample.status == 'SAP_STORED':
                        s['pellet_finished_sap'] += 1
                    elif sample.status == 'IN_LAB':
                        s['pellet_finished_in_lab'] += 1
                elif sample.sub_type == 'FOR_INJECTION':
                    s['pellet_for_injection_kg'] += qty
            elif sample.type == 'SPECIMEN':
                if sample.sub_type == 'FOR_TESTING':
                    s['specimen_for_testing_count'] += 1
                elif sample.sub_type == 'TESTED':
                    s['specimen_tested_count'] += 1

        for oid, counter in status_counter.items():
            # 优先 IN_LAB > SAP_STORED > 其他，取最活跃的状态
            active = 'IN_LAB' if 'IN_LAB' in counter else (
                'SAP_STORED' if 'SAP_STORED' in counter else (
                    counter.most_common(1)[0][0] if counter else ''
                )
            )
            summaries[oid]['active_status'] = active

        return summaries

    @staticmethod
    def build_order_groups(samples_qs):
        """按 production_order 分组样品 + 计算汇总统计（供列表页复用）。

        将已筛选的 SampleInventory QuerySet 分为两组：
        - 关联工单的样品 → 按工单分组，每组附带汇总统计
        - 独立样品（无工单关联）→ 平铺列表

        Args:
            samples_qs: QuerySet[SampleInventory] — 已应用筛选条件的样品

        Returns:
            (groups, orphan_samples)
            groups: list[dict] — [{'order': ProductionOrder, 'samples': [...], 'summary': {...}, 'samples_count': int}, ...]
            orphan_samples: list[SampleInventory] — production_order=None 的样品
        """
        from collections import OrderedDict
        from app_trial_production.models import ProductionOrder

        order_samples = OrderedDict()
        orphan = []
        for s in samples_qs:
            if s.production_order_id:
                key = s.production_order_id
                if key not in order_samples:
                    order_samples[key] = []
                order_samples[key].append(s)
            else:
                orphan.append(s)

        order_ids = list(order_samples.keys())
        orders_map = {}
        if order_ids:
            orders = ProductionOrder.objects.filter(
                pk__in=order_ids,
            ).select_related('project', 'creator')
            orders_map = {o.pk: o for o in orders}

        summaries = SampleInventoryService.get_order_sample_summaries(
            set(orders_map.keys()),
            samples_qs.filter(production_order__in=order_ids),
        )

        groups = []
        for oid, samples in order_samples.items():
            order = orders_map.get(oid)
            if not order:
                orphan.extend(samples)
                continue
            summary = summaries.get(oid, {})
            groups.append({
                'order': order,
                'samples': samples,
                'summary': summary,
                'samples_count': len(samples),
            })

        groups.sort(key=lambda g: g['order'].code or '', reverse=True)
        return groups, orphan

    @staticmethod
    @transaction.atomic
    def create_standalone_sample(data):
        """创建不关联工单的独立样品。

        用于样品库手动新增场景，不绑定任何 ProductionOrder。

        Args:
            data: dict with keys matching SampleInventory fields:
                type, sub_type, formula_id (optional), trial_code (optional),
                quantity (for PELLET), specimen_count/specimen_qualified (for SPECIMEN),
                storage_location, packaging_desc, mold_id (optional), batch_label (optional)

        Returns:
            SampleInventory 实例
        """
        sample = SampleInventory.objects.create(
            type=data['type'],
            sub_type=data['sub_type'],
            status='IN_LAB',
            production_order=None,
            formula_id=data.get('formula_id'),
            trial_code=data.get('trial_code', ''),
            quantity=data.get('quantity'),
            specimen_count=data.get('specimen_count'),
            specimen_qualified=data.get('specimen_qualified'),
            storage_location=data.get('storage_location', ''),
            packaging_desc=data.get('packaging_desc', ''),
            mold_id=data.get('mold_id'),
            batch_label=data.get('batch_label', ''),
            batch_number=data.get('batch_label', ''),  # 独立样品用 batch_label 作为批次号
        )

        logger.info(f"Standalone sample {sample.pk} created (type={sample.type}, sub_type={sample.sub_type})")
        return sample
