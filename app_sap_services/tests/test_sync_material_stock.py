"""库存同步命令回归：缺席补 0、未变化只刷新日期、按保留期清历史。

全部 mock `_query_sap` / `sap_health_check`，不连真实 SAP。
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import polars as pl

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from app_raw_material.models import (
    Plant,
    RawMaterial,
    RawMaterialStockSnapshot,
    RawMaterialType,
)
from app_sap_services.management.commands.sync_material_stock import Command


HEALTH = {"status": "healthy", "ashost": "192.168.103.182", "client": "800"}
HEALTH_PATCH = (
    "app_sap_services.management.commands.sync_material_stock.sap_health_check"
)


def sap_df(rows=None) -> pl.DataFrame:
    schema = {
        "MATNR": pl.Utf8,
        "MAKTX": pl.Utf8,
        "WERKS": pl.Utf8,
        "LGORT": pl.Utf8,
        "CHARG": pl.Utf8,
        "CLABS": pl.Float64,
        "EISBE": pl.Float64,
    }
    if not rows:
        return pl.DataFrame(schema=schema)
    normalized = []
    for row in rows:
        normalized.append({
            "MATNR": row.get("MATNR", ""),
            "MAKTX": row.get("MAKTX", ""),
            "WERKS": row.get("WERKS", ""),
            "LGORT": row.get("LGORT", ""),
            "CHARG": row.get("CHARG", ""),
            "CLABS": float(row.get("CLABS", 0) or 0),
            "EISBE": float(row.get("EISBE", 0) or 0),
        })
    return pl.DataFrame(normalized, schema=schema)


def sap_row(matnr, werks, loc="0001", charg="B1", clabs=10, eisbe=1):
    return {
        "MATNR": matnr,
        "MAKTX": "",
        "WERKS": werks,
        "LGORT": loc,
        "CHARG": charg,
        "CLABS": clabs,
        "EISBE": eisbe,
    }


class StockSyncTests(TestCase):
    def setUp(self):
        self.category = RawMaterialType.objects.create(name="树脂")
        self.plant_a = Plant.objects.create(code="3011", name="上海")
        self.plant_b = Plant.objects.create(code="3020", name="昆山")
        self.rm_a = RawMaterial.objects.create(
            name="PA66", warehouse_code="A01005000013", category=self.category,
        )
        self.rm_b = RawMaterial.objects.create(
            name="PA6", warehouse_code="A01005000014", category=self.category,
        )

    def _snap(
        self, rm, plant, *, batch=None, loc="0001", charg="B1",
        clabs="10.000", eisbe="1.000", synced_at=None,
    ):
        snap = RawMaterialStockSnapshot.objects.create(
            sync_batch_id=batch or uuid.uuid4(),
            raw_material=rm,
            plant=plant,
            storage_location=loc,
            batch=charg,
            unrestricted_stock=Decimal(clabs),
            safety_stock=Decimal(eisbe),
        )
        if synced_at is not None:
            RawMaterialStockSnapshot.objects.filter(pk=snap.pk).update(synced_at=synced_at)
            snap.refresh_from_db()
        return snap

    def _run(self, df, **opts):
        opts.setdefault("no_prune", True)
        out = StringIO()
        with patch(HEALTH_PATCH, return_value=HEALTH), \
                patch.object(Command, "_query_sap", return_value=df) as mock_query:
            call_command("sync_material_stock", stdout=out, **opts)
        return out.getvalue(), mock_query

    def _count(self):
        return RawMaterialStockSnapshot.objects.count()

    def test_matnr_filter_uses_eq_without_wildcard(self):
        self.assertEqual(
            Command.matnr_filter_kwargs("A01005000013"),
            {"mat_range__eq": "A01005000013"},
        )
        self.assertEqual(Command.matnr_filter_kwargs("A01*"), {"mat_range__cp": "A01*"})
        self.assertEqual(Command.matnr_filter_kwargs(None), {})

    def test_keep_days_rejects_negative(self):
        with self.assertRaisesMessage(CommandError, "不能为负数"):
            call_command("sync_material_stock", keep_days=-1)

    def test_prune_only_xor_no_prune(self):
        with self.assertRaisesMessage(CommandError, "不能同时使用"):
            call_command("sync_material_stock", prune_only=True, no_prune=True)

    # ── 取数 / 补零 ──────────────────────────────────────────────

    def test_omitted_material_gets_zero_row(self):
        """全量省略某物料、旧快照有库存 → 历史工厂新零行，合计 0。"""
        old = timezone.now() - timedelta(days=2)
        self._snap(self.rm_a, self.plant_a, clabs="88.000", synced_at=old)
        # 非本地物料：撑住「全量非空」，避免误中止，同时不写入第二颗本地物料
        self._run(sap_df([sap_row("ZZZZZZZZZZZZ", "3011")]))

        self.assertEqual(self.rm_a.stock_total_for_plant(self.plant_a), 0)
        current = list(self.rm_a.stock_for_plant(self.plant_a))
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0].unrestricted_stock, Decimal("0.000"))
        self.assertEqual(current[0].storage_location, "")
        self.assertEqual(current[0].batch, "")
        self.assertEqual(self._count(), 2)

    def test_already_zero_only_bumps(self):
        """全量省略且最新已是零行 → 只 bump，不插行。"""
        old = timezone.now() - timedelta(hours=3)
        snap = self._snap(
            self.rm_a, self.plant_a, loc="", charg="", clabs="0.000", eisbe="0.000",
            synced_at=old,
        )
        self._run(sap_df([sap_row("ZZZZZZZZZZZZ", "3011")]))

        self.assertEqual(self._count(), 1)
        snap.refresh_from_db()
        self.assertGreater(snap.synced_at, old)
        self.assertEqual(self.rm_a.stock_total_for_plant(self.plant_a), 0)

    def test_sentinel_empty_werks_is_dropped(self):
        """SAP 哨兵行（空 WERKS、CLABS=0）被丢弃，不创建空工厂。"""
        old = timezone.now() - timedelta(days=1)
        self._snap(self.rm_a, self.plant_a, synced_at=old)
        self._run(sap_df([
            {
                "MATNR": "", "MAKTX": "", "WERKS": "", "LGORT": "", "CHARG": "",
                "CLABS": 0, "EISBE": 0,
            },
            {
                "MATNR": "A01005000013", "MAKTX": "", "WERKS": "", "LGORT": "",
                "CHARG": "", "CLABS": 0, "EISBE": 0,
            },
        ]), matnr="A01005000013")

        self.assertFalse(Plant.objects.filter(code="").exists())
        self.assertEqual(self.rm_a.stock_total_for_plant(self.plant_a), 0)

    def test_full_empty_aborts_without_write_or_prune(self):
        """全量 0 行 → 不写、不 bump、不清理。"""
        old = timezone.now() - timedelta(days=40)
        current = timezone.now() - timedelta(hours=1)
        stale = self._snap(self.rm_a, self.plant_a, synced_at=old)
        live = self._snap(
            self.rm_a, self.plant_a, batch=uuid.uuid4(), clabs="5.000", synced_at=current,
        )
        with patch(HEALTH_PATCH, return_value=HEALTH), \
                patch.object(Command, "_query_sap", return_value=sap_df()):
            with self.assertRaisesMessage(CommandError, "全量查询返回空结果"):
                call_command("sync_material_stock", keep_days=0)

        self.assertEqual(self._count(), 2)
        stale.refresh_from_db()
        live.refresh_from_db()
        self.assertEqual(stale.synced_at, old)
        self.assertEqual(live.unrestricted_stock, Decimal("5.000"))

    def test_werks_only_empty_aborts(self):
        with patch(HEALTH_PATCH, return_value=HEALTH), \
                patch.object(Command, "_query_sap", return_value=sap_df()):
            with self.assertRaisesMessage(CommandError, "工厂 3011 查询返回空结果"):
                call_command("sync_material_stock", werks="3011", no_prune=True)

    def test_matnr_empty_only_touches_that_material(self):
        """--matnr + 仅哨兵/空表 → 只处理该物料。"""
        old = timezone.now() - timedelta(days=1)
        self._snap(self.rm_a, self.plant_a, clabs="12.000", synced_at=old)
        snap_b = self._snap(self.rm_b, self.plant_a, clabs="33.000", synced_at=old)

        self._run(sap_df(), matnr="A01005000013")

        self.assertEqual(self.rm_a.stock_total_for_plant(self.plant_a), 0)
        snap_b.refresh_from_db()
        self.assertEqual(snap_b.unrestricted_stock, Decimal("33.000"))
        self.assertEqual(snap_b.synced_at, old)
        self.assertEqual(self.rm_b.stock_total_for_plant(self.plant_a), Decimal("33.000"))

    def test_werks_only_touches_that_plant(self):
        old = timezone.now() - timedelta(days=1)
        self._snap(self.rm_a, self.plant_a, clabs="12.000", synced_at=old)
        snap_b = self._snap(self.rm_a, self.plant_b, clabs="44.000", synced_at=old)

        self._run(sap_df([sap_row("ZZZZZZZZZZZZ", "3011")]), werks="3011")

        self.assertEqual(self.rm_a.stock_total_for_plant(self.plant_a), 0)
        snap_b.refresh_from_db()
        self.assertEqual(snap_b.unrestricted_stock, Decimal("44.000"))
        self.assertEqual(self.rm_a.stock_total_for_plant(self.plant_b), Decimal("44.000"))

    def test_limit_skips_zero_fill(self):
        old = timezone.now() - timedelta(days=1)
        snap = self._snap(self.rm_a, self.plant_a, clabs="12.000", synced_at=old)
        self._run(sap_df([sap_row("ZZZZZZZZZZZZ", "3011")]), limit=1)

        snap.refresh_from_db()
        self.assertEqual(snap.unrestricted_stock, Decimal("12.000"))
        self.assertEqual(self.rm_a.stock_total_for_plant(self.plant_a), Decimal("12.000"))
        self.assertEqual(self._count(), 1)

    def test_missing_storage_location_writes_new_batch(self):
        """某库位消失 → 新批次不含该库位。"""
        old = timezone.now() - timedelta(hours=2)
        batch = uuid.uuid4()
        keep = self._snap(
            self.rm_a, self.plant_a, batch=batch, loc="0001", charg="B1",
            clabs="10.000", synced_at=old,
        )
        gone = self._snap(
            self.rm_a, self.plant_a, batch=batch, loc="0002", charg="B2",
            clabs="4.000", synced_at=old,
        )
        self._run(sap_df([sap_row("A01005000013", "3011", loc="0001", charg="B1", clabs=10, eisbe=1)]))

        current = list(self.rm_a.stock_for_plant(self.plant_a))
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0].storage_location, "0001")
        self.assertNotEqual(current[0].sync_batch_id, batch)
        self.assertTrue(RawMaterialStockSnapshot.objects.filter(pk=gone.pk).exists())
        keep.refresh_from_db()
        self.assertEqual(keep.storage_location, "0001")
        self.assertEqual(self._count(), 3)

    # ── 未变化只刷新日期 ────────────────────────────────────────

    def test_same_signature_bumps_synced_at_only(self):
        old = timezone.now() - timedelta(hours=5)
        batch = uuid.uuid4()
        snap = self._snap(
            self.rm_a, self.plant_a, batch=batch, loc="0001", charg="B1",
            clabs="10.000", eisbe="1.000", synced_at=old,
        )
        self._run(sap_df([sap_row("A01005000013", "3011", loc="0001", charg="B1", clabs=10, eisbe=1)]))

        self.assertEqual(self._count(), 1)
        snap.refresh_from_db()
        self.assertEqual(snap.sync_batch_id, batch)
        self.assertGreater(snap.synced_at, old)

    def test_second_identical_sync_does_not_insert(self):
        self._run(sap_df([sap_row("A01005000013", "3011")]))
        self.assertEqual(self._count(), 1)
        self._run(sap_df([sap_row("A01005000013", "3011")]))
        self.assertEqual(self._count(), 1)

    def test_clabs_change_inserts_new_row(self):
        old = timezone.now() - timedelta(hours=2)
        old_snap = self._snap(
            self.rm_a, self.plant_a, loc="0001", charg="B1",
            clabs="10.000", eisbe="1.000", synced_at=old,
        )
        self._run(sap_df([sap_row("A01005000013", "3011", loc="0001", charg="B1", clabs=20, eisbe=1)]))

        self.assertEqual(self._count(), 2)
        self.assertTrue(RawMaterialStockSnapshot.objects.filter(pk=old_snap.pk).exists())
        current = self.rm_a.stock_for_plant(self.plant_a).get()
        self.assertEqual(current.unrestricted_stock, Decimal("20.000"))
        self.assertNotEqual(current.pk, old_snap.pk)

    def test_dry_run_does_not_write(self):
        old = timezone.now() - timedelta(days=1)
        snap = self._snap(self.rm_a, self.plant_a, clabs="12.000", synced_at=old)
        out, _ = self._run(sap_df(), dry_run=True, matnr="A01005000013")

        self.assertEqual(self._count(), 1)
        snap.refresh_from_db()
        self.assertEqual(snap.synced_at, old)
        self.assertIn("补零", out)

    def test_unknown_plant_is_created(self):
        self._run(sap_df([sap_row("A01005000013", "3099")]))
        plant = Plant.objects.get(code="3099")
        self.assertEqual(self.rm_a.stock_total_for_plant(plant), Decimal("10.000"))

    def test_health_failure_aborts(self):
        with patch(HEALTH_PATCH, return_value={"status": "down", "error": "timeout"}):
            with self.assertRaisesMessage(CommandError, "SAP 连接失败"):
                call_command("sync_material_stock", no_prune=True)
        self.assertEqual(self._count(), 0)

    # ── 清理 ────────────────────────────────────────────────────

    def test_prune_deletes_expired_non_current(self):
        old = timezone.now() - timedelta(days=40)
        current = timezone.now() - timedelta(hours=1)
        stale = self._snap(self.rm_a, self.plant_a, synced_at=old)
        live = self._snap(
            self.rm_a, self.plant_a, batch=uuid.uuid4(), clabs="7.000", synced_at=current,
        )
        out = StringIO()
        call_command("sync_material_stock", prune_only=True, keep_days=30, stdout=out)

        self.assertFalse(RawMaterialStockSnapshot.objects.filter(pk=stale.pk).exists())
        self.assertTrue(RawMaterialStockSnapshot.objects.filter(pk=live.pk).exists())
        self.assertIn("清理过期快照: 1 条", out.getvalue())

    def test_prune_keeps_current_even_if_older_than_window(self):
        old = timezone.now() - timedelta(days=40)
        live = self._snap(self.rm_a, self.plant_a, synced_at=old)
        call_command("sync_material_stock", prune_only=True, keep_days=30)

        self.assertTrue(RawMaterialStockSnapshot.objects.filter(pk=live.pk).exists())

    def test_keep_days_zero_drops_all_non_current(self):
        recent_old = timezone.now() - timedelta(days=2)
        current = timezone.now() - timedelta(hours=1)
        stale = self._snap(self.rm_a, self.plant_a, synced_at=recent_old)
        live = self._snap(
            self.rm_a, self.plant_a, batch=uuid.uuid4(), clabs="7.000", synced_at=current,
        )
        call_command("sync_material_stock", prune_only=True, keep_days=0)

        self.assertFalse(RawMaterialStockSnapshot.objects.filter(pk=stale.pk).exists())
        self.assertTrue(RawMaterialStockSnapshot.objects.filter(pk=live.pk).exists())

    def test_no_prune_keeps_expired(self):
        old = timezone.now() - timedelta(days=40)
        current = timezone.now() - timedelta(hours=1)
        stale = self._snap(self.rm_a, self.plant_a, synced_at=old)
        self._snap(
            self.rm_a, self.plant_a, batch=uuid.uuid4(), loc="0001", charg="B1",
            clabs="10.000", eisbe="1.000", synced_at=current,
        )
        self._run(
            sap_df([sap_row("A01005000013", "3011", loc="0001", charg="B1", clabs=10, eisbe=1)]),
            no_prune=True,
        )
        self.assertTrue(RawMaterialStockSnapshot.objects.filter(pk=stale.pk).exists())

    def test_dry_run_prune_only_does_not_delete(self):
        old = timezone.now() - timedelta(days=40)
        current = timezone.now() - timedelta(hours=1)
        stale = self._snap(self.rm_a, self.plant_a, synced_at=old)
        self._snap(
            self.rm_a, self.plant_a, batch=uuid.uuid4(), clabs="7.000", synced_at=current,
        )
        out = StringIO()
        call_command(
            "sync_material_stock", prune_only=True, keep_days=30, dry_run=True, stdout=out,
        )
        self.assertTrue(RawMaterialStockSnapshot.objects.filter(pk=stale.pk).exists())
        self.assertIn("将清理: 1 条", out.getvalue())

    def test_prune_protects_per_plant_not_whole_uuid(self):
        """同一旧 sync_batch_id 跨两厂、仅一厂写了新批次 → 只删该厂过期行。"""
        shared = uuid.uuid4()
        old = timezone.now() - timedelta(days=40)
        snap_a = self._snap(
            self.rm_a, self.plant_a, batch=shared, clabs="10.000", synced_at=old,
        )
        snap_b = self._snap(
            self.rm_a, self.plant_b, batch=shared, clabs="20.000", synced_at=old,
        )
        newer = timezone.now() - timedelta(hours=1)
        live_a = self._snap(
            self.rm_a, self.plant_a, batch=uuid.uuid4(), clabs="3.000", synced_at=newer,
        )
        call_command("sync_material_stock", prune_only=True, keep_days=30)

        self.assertFalse(RawMaterialStockSnapshot.objects.filter(pk=snap_a.pk).exists())
        self.assertTrue(RawMaterialStockSnapshot.objects.filter(pk=snap_b.pk).exists())
        self.assertTrue(RawMaterialStockSnapshot.objects.filter(pk=live_a.pk).exists())
        self.assertEqual(self.rm_a.stock_total_for_plant(self.plant_b), Decimal("20.000"))
