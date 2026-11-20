"""原材料当前非限制库存合计。

守护 BOM 明细「库存」列的口径：每个（物料, 工厂）只加最新同步批次的
CLABS，再跨工厂相加。旧批次和安全库存都不算。没有快照的物料不出现。
"""

import uuid
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from app_raw_material.models import (
    Plant,
    RawMaterial,
    RawMaterialStockSnapshot,
    RawMaterialType,
)


class UnrestrictedStockTotalsTests(TestCase):
    def setUp(self):
        self.category = RawMaterialType.objects.create(name='树脂')
        self.plant_a = Plant.objects.create(code='3011', name='上海')
        self.plant_b = Plant.objects.create(code='3020', name='昆山')
        self.stocked = RawMaterial.objects.create(
            name='PA66', warehouse_code='A01005000013', category=self.category,
        )
        self.zeroed = RawMaterial.objects.create(
            name='PA6', warehouse_code='A01005000014', category=self.category,
        )
        self.unsynced = RawMaterial.objects.create(
            name='玻纤', warehouse_code='A01005000015', category=self.category,
        )

    def _snap(self, rm, plant, *, batch, loc='0001', charg='B1', clabs='0', eisbe='0', synced_at=None):
        snap = RawMaterialStockSnapshot.objects.create(
            sync_batch_id=batch,
            raw_material=rm,
            plant=plant,
            storage_location=loc,
            batch=charg,
            unrestricted_stock=Decimal(clabs),
            safety_stock=Decimal(eisbe),
        )
        if synced_at is not None:
            RawMaterialStockSnapshot.objects.filter(pk=snap.pk).update(synced_at=synced_at)
        return snap

    def test_sums_current_batches_across_plants_and_locations(self):
        now = timezone.now()
        old_batch = uuid.uuid4()
        current_a = uuid.uuid4()
        current_b = uuid.uuid4()
        # 旧批次的大库存不能算进去
        self._snap(
            self.stocked, self.plant_a, batch=old_batch,
            clabs='999.000', eisbe='1.000', synced_at=now - timedelta(days=2),
        )
        # 当前批次：同一工厂两个库位，安全库存再大也不加
        self._snap(
            self.stocked, self.plant_a, batch=current_a, loc='0001', charg='B1',
            clabs='10.500', eisbe='80.000', synced_at=now,
        )
        self._snap(
            self.stocked, self.plant_a, batch=current_a, loc='0002', charg='B2',
            clabs='2.250', eisbe='80.000', synced_at=now,
        )
        self._snap(
            self.stocked, self.plant_b, batch=current_b,
            clabs='3.000', eisbe='1.000', synced_at=now,
        )

        totals = RawMaterial.unrestricted_stock_totals([
            self.stocked.pk, self.zeroed.pk, self.unsynced.pk,
        ])

        self.assertEqual(totals[self.stocked.pk], Decimal('15.750'))

    def test_zero_snapshot_is_present(self):
        self._snap(self.zeroed, self.plant_a, batch=uuid.uuid4(), clabs='0.000', eisbe='5.000')

        totals = RawMaterial.unrestricted_stock_totals([self.zeroed.pk])

        self.assertEqual(totals[self.zeroed.pk], Decimal('0.000'))

    def test_material_without_snapshot_is_absent(self):
        totals = RawMaterial.unrestricted_stock_totals([self.unsynced.pk, self.stocked.pk])

        self.assertNotIn(self.unsynced.pk, totals)
        self.assertNotIn(self.stocked.pk, totals)

    def test_empty_ids_returns_empty_dict(self):
        self.assertEqual(RawMaterial.unrestricted_stock_totals([]), {})
        self.assertEqual(RawMaterial.unrestricted_stock_totals([None]), {})
