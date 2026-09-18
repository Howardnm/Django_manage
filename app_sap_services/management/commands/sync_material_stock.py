"""
Django 管理命令: 从 SAP 同步原材料库存快照到 app_raw_material。

用法:
    python manage.py sync_material_stock                  # 全量 + 缺席补 0 + 未变化刷新日期 + 清 30 天前非当前
    python manage.py sync_material_stock --dry-run        # 仅预览
    python manage.py sync_material_stock --matnr A01005000013
    python manage.py sync_material_stock --matnr "A01*"   # 按物料通配
    python manage.py sync_material_stock --werks 3011
    python manage.py sync_material_stock --keep-days 90
    python manage.py sync_material_stock --keep-days 0    # 每个物料+工厂只留当前快照
    python manage.py sync_material_stock --no-prune
    python manage.py sync_material_stock --prune-only     # 只清理，不拉 SAP

定时调度 (Windows Task Scheduler):
    触发器: 每日
    操作:   启动程序 python.exe
    参数:   manage.py sync_material_stock
    起始于: 项目根目录

取数:
    日调度走全量 mat_range=*（约 1 秒）。ZRFC_GET_MAT_STOCK 的通配查询不返回
    零库存物料，缺席的本地物料由写入侧按历史工厂补 0。
    --matnr 无通配时用 EQ（能拿到 CLABS=0 的哨兵行，工厂为空，仍按历史工厂补 0）。

写入:
    按 (物料, 工厂) 比对当前快照签名（库位+批号+CLABS+EISBE）。
    相同只刷新 synced_at；变化才插入新批次。未知工厂代码会自动创建 Plant。

清理:
    默认同步成功后删除超过 --keep-days 的非当前快照；每个 (物料, 工厂)
    的最新批次永远保留。
"""

from __future__ import annotations

import fnmatch
import uuid
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

import polars as pl

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F, OuterRef, Subquery
from django.utils import timezone

from app_sap_services import sap, sap_health_check
from app_sap_services.definitions.stock import MaterialStockQuery
from app_raw_material.models import Plant, RawMaterial, RawMaterialStockSnapshot


CHUNK_SIZE = 500
DEFAULT_KEEP_DAYS = 30
QTY = Decimal("0.001")
ZERO_QTY = Decimal("0.000")
ZERO_SIGNATURE = frozenset({("", "", ZERO_QTY, ZERO_QTY)})


def _qty(value) -> Decimal:
    if value is None or value == "":
        return ZERO_QTY
    return Decimal(str(value)).quantize(QTY)


def _signature_from_tuples(rows) -> frozenset:
    return frozenset(
        (
            (row[0] or ""),
            (row[1] or ""),
            _qty(row[2]),
            _qty(row[3]),
        )
        for row in rows
    )


class Command(BaseCommand):
    help = "从 SAP 同步原材料库存快照：未变化刷新日期，缺席补 0，并按保留期清理历史"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="仅查询并预览，不写入数据库",
        )
        parser.add_argument(
            "--limit", type=int, default=0,
            help="限制处理的 SAP 行数（0 = 不限制）。结果不完整，禁止补零和清理",
        )
        parser.add_argument(
            "--chunk-size", type=int, default=CHUNK_SIZE,
            help=f"数据库分批大小（默认: {CHUNK_SIZE}）",
        )
        parser.add_argument(
            "--matnr", type=str, default=None,
            help="按 SAP 物料编号筛选，支持 * 通配符（如 'A01*'）",
        )
        parser.add_argument(
            "--werks", type=str, default=None,
            help="按工厂代码筛选（如 '3011'）",
        )
        parser.add_argument(
            "--keep-days", type=int, default=DEFAULT_KEEP_DAYS,
            help=f"保留最近 N 天的非当前快照（默认 {DEFAULT_KEEP_DAYS}；0 = 只留当前）",
        )
        parser.add_argument(
            "--no-prune", action="store_true",
            help="本次不同步后清理",
        )
        parser.add_argument(
            "--prune-only", action="store_true",
            help="只按 --keep-days 清理历史，不拉 SAP",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]
        chunk_size = max(1, options["chunk_size"])
        matnr = options["matnr"]
        werks = options["werks"]
        keep_days = options["keep_days"]
        no_prune = options["no_prune"]
        prune_only = options["prune_only"]

        if keep_days < 0:
            raise CommandError("--keep-days 不能为负数")
        if prune_only and no_prune:
            raise CommandError("--prune-only 与 --no-prune 不能同时使用")

        scope_parts = []
        if matnr:
            scope_parts.append(f"物料: {matnr}")
        if werks:
            scope_parts.append(f"工厂: {werks}")
        scope_desc = ", ".join(scope_parts) if scope_parts else "全部"

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\n=== 开始 SAP 原材料库存同步 ===\n"
                f"    范围: {scope_desc}"
            )
        )
        if dry_run:
            self.stdout.write(
                self.style.WARNING("   [DRY-RUN] 预览模式，不会写入数据库")
            )

        if prune_only:
            pruned = self._prune_old_snapshots(keep_days, dry_run=dry_run)
            self._report_prune(pruned, keep_days, dry_run=dry_run)
            return

        health = sap_health_check()
        if health.get("status") != "healthy":
            raise CommandError(f"SAP 连接失败: {health.get('error', '未知错误')}")
        self.stdout.write(
            f"   [OK] SAP 连接正常 "
            f"(ashost={health.get('ashost')}, client={health.get('client')})"
        )

        warehouse_map = self._load_warehouse_map(matnr)
        self.stdout.write(f"   本地物料: {len(warehouse_map)} 个")

        is_full = not matnr and not werks
        try:
            df = self._query_sap(matnr, werks)
        except Exception as e:
            raise CommandError(f"SAP 查询失败: {e}") from e

        if is_full and df.is_empty():
            raise CommandError("全量查询返回空结果，已中止（疑似 RFC 故障，未写库、未清理）")
        if werks and not matnr and df.is_empty():
            raise CommandError(
                f"工厂 {werks} 查询返回空结果，已中止（疑似 RFC 故障，未写库、未清理）"
            )

        df = self._transform_stock(df)
        if not df.is_empty() and warehouse_map:
            before_match = df.height
            df = df.filter(pl.col("MATNR").is_in(list(warehouse_map)))
            self.stdout.write(
                f"   物料匹配: {before_match} 条 → {df.height} 条 "
                f"(过滤 {before_match - df.height} 条非本地物料)"
            )

        if limit and limit > 0 and not df.is_empty():
            df = df.sort("MATNR").head(limit)
            self.stdout.write(
                self.style.WARNING(
                    f"   --limit {limit}: 结果不完整，跳过缺席补零"
                    + ("" if no_prune else "和历史清理")
                )
            )

        stats = self._sync(
            df=df,
            warehouse_map=warehouse_map,
            werks=werks,
            zero_fill=not (limit and limit > 0),
            dry_run=dry_run,
            chunk_size=chunk_size,
        )

        do_prune = not no_prune and not (limit and limit > 0)
        pruned = 0
        if do_prune:
            pruned = self._prune_old_snapshots(keep_days, dry_run=dry_run)

        self._report(stats, pruned, keep_days, dry_run=dry_run, pruned_enabled=do_prune)

    # ------------------------------------------------------------------
    # 本地物料范围
    # ------------------------------------------------------------------

    @staticmethod
    def _load_warehouse_map(matnr) -> dict:
        warehouse_map = {
            rm.warehouse_code: rm
            for rm in RawMaterial.objects.all()
            if rm.warehouse_code
        }
        if not matnr:
            return warehouse_map
        if "*" in matnr:
            return {
                code: rm
                for code, rm in warehouse_map.items()
                if fnmatch.fnmatchcase(code, matnr)
            }
        return {code: rm for code, rm in warehouse_map.items() if code == matnr}

    @staticmethod
    def matnr_filter_kwargs(matnr) -> dict:
        """SAP Range：无通配用 EQ（才能拿到零库存哨兵行），有 * 用 CP。"""
        if not matnr:
            return {}
        if "*" in matnr:
            return {"mat_range__cp": matnr}
        return {"mat_range__eq": matnr}

    # ------------------------------------------------------------------
    # SAP 查询
    # ------------------------------------------------------------------

    def _query_sap(self, matnr, werks) -> pl.DataFrame:
        """执行 SAP 查询。ZRFC_GET_MAT_STOCK 要求 mat_range 或 wek_range 至少一个。"""
        query = sap.rfc(MaterialStockQuery)
        matnr_kw = self.matnr_filter_kwargs(matnr)
        if matnr_kw:
            query = query.filter(**matnr_kw)
        if werks:
            query = query.filter(wek_range__eq=werks)
        if not matnr and not werks:
            query = query.filter(mat_range__cp="*")

        df = query.collect()
        self.stdout.write(f"   SAP 返回: {df.height} 条")
        return df

    def _transform_stock(self, df: pl.DataFrame) -> pl.DataFrame:
        """丢掉空物料号、空工厂哨兵行、负库存；清洗字符串。"""
        if df.is_empty():
            return df

        before = df.height
        df = df.with_columns([
            pl.col("MATNR").cast(pl.Utf8).fill_null("").str.strip_chars(),
            pl.col("WERKS").cast(pl.Utf8).fill_null("").str.strip_chars(),
            pl.col("LGORT").cast(pl.Utf8).fill_null("").str.strip_chars(),
            pl.col("CHARG").cast(pl.Utf8).fill_null("").str.strip_chars(),
            pl.col("CLABS").fill_null(0),
            pl.col("EISBE").fill_null(0),
        ])

        empty_plant = df.filter(pl.col("WERKS") == "").height
        df = df.filter(pl.col("MATNR") != "")
        df = df.filter(pl.col("WERKS") != "")
        df = df.filter(pl.col("CLABS") >= 0)

        self.stdout.write(
            f"   数据清洗: {before} 条 → 有效 {df.height} 条 "
            f"(过滤 {before - df.height} 条，其中空工厂哨兵 {empty_plant} 条)"
        )
        return df

    # ------------------------------------------------------------------
    # 比对 + 写入
    # ------------------------------------------------------------------

    def _sync(self, df, warehouse_map, werks, zero_fill, dry_run, chunk_size):
        stats = {
            "refreshed_pairs": 0,
            "created_pairs": 0,
            "zero_pairs": 0,
            "created_rows": 0,
            "bumped_rows": 0,
        }
        if not warehouse_map:
            return stats

        plant_cache = {p.code: p for p in Plant.objects.all()}
        sap_by_pair = self._group_sap_rows(df, warehouse_map, plant_cache, dry_run=dry_run)
        current_by_pair = self._latest_snapshots(warehouse_map, werks)

        if zero_fill:
            for pair in current_by_pair:
                if pair not in sap_by_pair:
                    sap_by_pair[pair] = None

        bump_pks = []
        to_create = []
        batch_id = uuid.uuid4()
        now = timezone.now()

        for pair, sap_rows in sap_by_pair.items():
            existing = current_by_pair.get(pair, [])
            is_zero = sap_rows is None
            if is_zero:
                new_sig = ZERO_SIGNATURE
                new_rows = [("", "", ZERO_QTY, ZERO_QTY)]
            else:
                new_sig = _signature_from_tuples(
                    (r["LGORT"], r["CHARG"], r["CLABS"], r["EISBE"]) for r in sap_rows
                )
                new_rows = [
                    (r["LGORT"] or "", r["CHARG"] or "", _qty(r["CLABS"]), _qty(r["EISBE"]))
                    for r in sap_rows
                ]

            old_sig = None
            if existing:
                old_sig = _signature_from_tuples(
                    (s.storage_location, s.batch, s.unrestricted_stock, s.safety_stock)
                    for s in existing
                )

            if old_sig is not None and old_sig == new_sig:
                bump_pks.extend(s.pk for s in existing)
                stats["refreshed_pairs"] += 1
                stats["bumped_rows"] += len(existing)
                continue

            rm_id, plant_id = pair
            stats["created_pairs"] += 1
            stats["created_rows"] += len(new_rows)
            if is_zero:
                stats["zero_pairs"] += 1
            if dry_run:
                continue
            for loc, charg, clabs, eisbe in new_rows:
                to_create.append(RawMaterialStockSnapshot(
                    sync_batch_id=batch_id,
                    raw_material_id=rm_id,
                    plant_id=plant_id,
                    storage_location=loc,
                    batch=charg,
                    unrestricted_stock=clabs,
                    safety_stock=eisbe,
                ))

        if dry_run:
            return stats

        with transaction.atomic():
            for i in range(0, len(to_create), chunk_size):
                RawMaterialStockSnapshot.objects.bulk_create(to_create[i:i + chunk_size])
            if bump_pks:
                for i in range(0, len(bump_pks), chunk_size):
                    RawMaterialStockSnapshot.objects.filter(
                        pk__in=bump_pks[i:i + chunk_size]
                    ).update(synced_at=now)

        return stats

    def _group_sap_rows(self, df, warehouse_map, plant_cache, dry_run):
        grouped = defaultdict(list)
        if df is None or df.is_empty():
            return grouped

        for row in df.iter_rows(named=True):
            rm = warehouse_map.get(row["MATNR"])
            if rm is None:
                continue
            werks = row["WERKS"]
            if not werks:
                continue
            plant = plant_cache.get(werks)
            if plant is None:
                if dry_run:
                    grouped[(rm.pk, f"new:{werks}")].append(row)
                    continue
                plant, _ = Plant.objects.get_or_create(code=werks, defaults={"name": ""})
                plant_cache[werks] = plant
            grouped[(rm.pk, plant.pk)].append(row)
        return grouped

    def _latest_snapshots(self, warehouse_map, werks) -> dict:
        material_ids = [rm.pk for rm in warehouse_map.values()]
        if not material_ids:
            return {}

        qs = RawMaterialStockSnapshot.objects.filter(raw_material_id__in=material_ids)
        if werks:
            qs = qs.filter(plant__code=werks)

        latest_batch = Subquery(
            RawMaterialStockSnapshot.objects.filter(
                raw_material_id=OuterRef("raw_material_id"),
                plant_id=OuterRef("plant_id"),
            ).order_by("-synced_at").values("sync_batch_id")[:1]
        )
        current = list(
            qs.annotate(latest_batch=latest_batch)
            .filter(sync_batch_id=F("latest_batch"))
            .select_related("plant")
        )
        by_pair = defaultdict(list)
        for snap in current:
            by_pair[(snap.raw_material_id, snap.plant_id)].append(snap)
        return by_pair

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------

    def _prune_old_snapshots(self, keep_days, dry_run) -> int:
        latest_batch = Subquery(
            RawMaterialStockSnapshot.objects.filter(
                raw_material_id=OuterRef("raw_material_id"),
                plant_id=OuterRef("plant_id"),
            ).order_by("-synced_at").values("sync_batch_id")[:1]
        )
        qs = (
            RawMaterialStockSnapshot.objects
            .annotate(latest_batch=latest_batch)
            .exclude(sync_batch_id=F("latest_batch"))
        )
        if keep_days > 0:
            cutoff = timezone.now() - timedelta(days=keep_days)
            qs = qs.filter(synced_at__lt=cutoff)

        if dry_run:
            return qs.count()

        deleted = 0
        while True:
            ids = list(qs.values_list("pk", flat=True)[:CHUNK_SIZE])
            if not ids:
                break
            deleted += RawMaterialStockSnapshot.objects.filter(pk__in=ids).delete()[0]
        return deleted

    def _report(self, stats, pruned, keep_days, dry_run, pruned_enabled):
        prefix = "将" if dry_run else ""
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"[OK] {'预览' if dry_run else '同步'}完成！"
                f"{prefix}刷新 {stats['refreshed_pairs']} 个工厂, "
                f"{prefix}新建 {stats['created_pairs']} 个工厂 "
                f"(其中补零 {stats['zero_pairs']}), "
                f"{prefix}写入 {stats['created_rows']} 行"
            )
        )
        if pruned_enabled:
            self._report_prune(pruned, keep_days, dry_run=dry_run)
        elif not dry_run:
            self.stdout.write("   已跳过历史清理")

    def _report_prune(self, pruned, keep_days, dry_run):
        keep_desc = "只留当前批次" if keep_days == 0 else f"保留 {keep_days} 天"
        verb = "将清理" if dry_run else "清理过期快照"
        self.stdout.write(f"   {verb}: {pruned} 条（{keep_desc} / 最新批次已保护）")
