import logging
from django.db import transaction
from django.db.models import Sum, Count
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

        Args:
            production_order: ProductionOrder 实例
            splits: list of dict {
                formula_id, sub_type ('FINISHED'|'FOR_INJECTION'),
                quantity, packaging_desc, storage_location
            }

        Returns:
            list of SampleInventory instances
        """
        samples = []
        for split in splits:
            if not split.get('quantity') or float(split['quantity']) <= 0:
                continue

            sample = SampleInventory.objects.create(
                type='PELLET',
                sub_type=split['sub_type'],
                status='IN_LAB',
                production_order=production_order,
                formula_id=split.get('formula_id'),
                trial_code=production_order.trial_code,
                quantity=split['quantity'],
                packaging_desc=split.get('packaging_desc', ''),
                storage_location=split.get('storage_location', ''),
            )
            samples.append(sample)

        # 按分拨明细的 KG 数量汇总更新工单实际产量
        total_kg = sum(float(s['quantity']) for s in splits if s.get('quantity'))
        if total_kg > 0:
            production_order.quantity_actual = total_kg
            production_order.save(update_fields=['quantity_actual', 'updated_at'])

        # 颗粒分拨完成 → 检查是否可推进工单（触发注塑/测试）
        from app_trial_production.services.order_service import ProductionOrderService
        ProductionOrderService.check_and_advance(production_order)

        logger.info(
            f"Created {len(samples)} pellet samples for order {production_order.code}"
            f" (total={total_kg}kg)"
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
    def get_pellet_summary(trial_code):
        """
        按试验单汇总颗粒样品统计。

        Returns:
            dict {
                'finished': {'count': int, 'total_kg': Decimal},
                'for_injection': {'count': int, 'total_kg': Decimal},
            }
        """
        qs = SampleInventory.objects.filter(
            trial_code=trial_code, type='PELLET',
        ).exclude(status='CONSUMED')

        finished = qs.filter(sub_type='FINISHED').aggregate(
            count=Count('id'),
            total_kg=Sum('quantity'),
        )
        for_injection = qs.filter(sub_type='FOR_INJECTION').aggregate(
            count=Count('id'),
            total_kg=Sum('quantity'),
        )

        return {
            'finished': finished,
            'for_injection': for_injection,
        }

    @staticmethod
    def get_specimen_summary(trial_code):
        """
        按试验单汇总样条样品统计。

        Returns:
            dict {
                'for_testing': {'count': int, 'total_specimens': int},
                'tested': {'count': int, 'total_specimens': int},
            }
        """
        qs = SampleInventory.objects.filter(
            trial_code=trial_code, type='SPECIMEN',
        )

        for_testing = qs.filter(sub_type='FOR_TESTING').aggregate(
            count=Count('id'),
            total_specimens=Sum('specimen_count'),
        )
        tested = qs.filter(sub_type='TESTED').aggregate(
            count=Count('id'),
            total_specimens=Sum('specimen_count'),
        )

        return {
            'for_testing': for_testing,
            'tested': tested,
        }

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
