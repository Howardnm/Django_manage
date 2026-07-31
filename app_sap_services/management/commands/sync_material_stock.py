"""
Django 管理命令: 从 SAP 同步原材料库存快照到 app_raw_material。

用法:
    python manage.py sync_material_stock                              # 全量同步
    python manage.py sync_material_stock --dry-run                    # 仅预览
    python manage.py sync_material_stock --limit 100                  # 限制条数
    python manage.py sync_material_stock --matnr "A01*"               # 按物料筛选
    python manage.py sync_material_stock --werks 3011                 # 按工厂筛选

定时调度 (Windows Task Scheduler):
    触发器: 每日
    操作:   启动程序 python.exe
    参数:   manage.py sync_material_stock
    起始于: 项目根目录

注意：
    每次同步全量拉取 SAP 当前库存，生成新批次（sync_batch_id）写入。
    历史批次保留不删除，便于追踪库存变化趋势。
    未知工厂代码将在同步时自动创建 Plant 记录。
"""

import uuid

import polars as pl

from django.core.management.base import BaseCommand
from django.db import transaction

from app_sap_services import sap, sap_health_check
from app_sap_services.definitions.stock import MaterialStockQuery
from app_raw_material.models import Plant, RawMaterial, RawMaterialStockSnapshot


CHUNK_SIZE = 500


class Command(BaseCommand):
    help = "从 SAP 同步原材料库存快照到本地 RawMaterialStockSnapshot 表"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="仅查询并预览，不写入数据库",
        )
        parser.add_argument(
            "--limit", type=int, default=0,
            help="限制同步条数（0 = 不限制）",
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

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]
        chunk_size = options["chunk_size"]
        matnr = options["matnr"]
        werks = options["werks"]

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

        # ── 1. 健康检查 ──
        health = sap_health_check()
        if health.get("status") != "healthy":
            self.stdout.write(
                self.style.ERROR(
                    f"   [ERR] SAP 连接失败: {health.get('error', '未知错误')}"
                )
            )
            return
        self.stdout.write(
            f"   [OK] SAP 连接正常 "
            f"(ashost={health.get('ashost')}, client={health.get('client')})"
        )

        # ── 2. 预加载本地物料映射 ──
        warehouse_map = {
            rm.warehouse_code: rm
            for rm in RawMaterial.objects.all()
        }
        valid_codes = {k for k in warehouse_map.keys() if k}
        self.stdout.write(f"   本地物料总数: {len(valid_codes)}")

        # ── 3. SAP 查询 ──
        try:
            df = self._query_sap(matnr, werks)
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"   [ERR] SAP 查询失败: {e}")
            )
            return

        if df.is_empty():
            self.stdout.write(self.style.WARNING("   没有符合条件的数据，同步结束"))
            return

        # ── 4. Polars 端数据处理 ──
        df = self._transform_stock(df)

        if df.is_empty():
            self.stdout.write(self.style.WARNING("   有效库存数据为空，同步结束"))
            return

        # 仅保留本地已存在的物料
        before_match = df.height
        df = df.filter(pl.col("MATNR").is_in(valid_codes))
        after_match = df.height
        self.stdout.write(
            f"   物料匹配: {before_match} 条 → {after_match} 条 "
            f"(过滤 {before_match - after_match} 条非本地物料)"
        )

        if df.is_empty():
            self.stdout.write(
                self.style.WARNING("   没有可匹配本地物料的数据，同步结束")
            )
            return

        # limit 在过滤后执行
        if limit and limit > 0:
            df = df.sort("MATNR").head(limit)

        # ── 5. 同步 ──
        if dry_run:
            self._dry_run(df, warehouse_map)
        else:
            self._live_sync(df, warehouse_map, chunk_size)

    # ------------------------------------------------------------------
    # SAP 查询
    # ------------------------------------------------------------------

    def _query_sap(self, matnr, werks) -> pl.DataFrame:
        """执行 SAP 查询，返回 Polars DataFrame。

        注意：ZRFC_GET_MAT_STOCK 要求 mat_range 或 wek_range 至少传一个值，
        否则返回空数据。当两者均未指定时，默认传 mat_range__cp="*" 拉取全量。
        """
        query = sap.rfc(MaterialStockQuery)
        if matnr:
            query = query.filter(mat_range__cp=matnr)
        if werks:
            query = query.filter(wek_range__eq=werks)
        # SAP 要求至少一个 RANGE 条件，无参数时传 * 兜底
        if not matnr and not werks:
            query = query.filter(mat_range__cp="*")

        df = query.collect()
        self.stdout.write(f"   SAP 返回: {df.height} 条")
        return df

    # ------------------------------------------------------------------
    # Polars 数据清洗
    # ------------------------------------------------------------------

    def _transform_stock(self, df: pl.DataFrame) -> pl.DataFrame:
        """Polars 端：过滤无效数据 + 清洗字段"""
        before = df.height

        # 过滤物料编号为空
        df = df.filter(pl.col("MATNR").is_not_null())
        df = df.filter(pl.col("MATNR").str.strip_chars() != "")

        # 过滤工厂为空
        df = df.filter(pl.col("WERKS").is_not_null())
        df = df.filter(pl.col("WERKS").str.strip_chars() != "")

        # 过滤 CLABS 为负数（SAP 有时返回负数表示异常）
        df = df.filter(pl.col("CLABS") >= 0)

        # 清洗字符串字段
        df = df.with_columns([
            pl.col("MATNR").str.strip_chars(),
            pl.col("WERKS").str.strip_chars(),
            pl.col("LGORT").str.strip_chars().fill_null(""),
            pl.col("CHARG").str.strip_chars().fill_null(""),
        ])

        after = df.height
        self.stdout.write(
            f"   数据清洗: {before} 条 → 有效 {after} 条 "
            f"(过滤 {before - after} 条无效记录)"
        )

        return df

    # ------------------------------------------------------------------
    # dry-run
    # ------------------------------------------------------------------

    def _dry_run(self, df: pl.DataFrame, warehouse_map: dict):
        will_create = 0
        skipped_no_plant = 0
        skipped_no_material = 0

        for row in df.iter_rows(named=True):
            matnr = row["MATNR"]
            werks = row["WERKS"]

            rm = warehouse_map.get(matnr)
            if rm is None:
                skipped_no_material += 1
                continue

            if not werks:
                skipped_no_plant += 1
                continue

            will_create += 1
            self.stdout.write(
                f"   [+] 将创建: {rm.name} ({matnr}) "
                f"[{werks}] {row['LGORT']}/{row['CHARG']} "
                f"CLABS={row['CLABS']}, EISBE={row['EISBE']}"
            )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"[OK] 预览完成！共 {will_create} 条将创建"
            )
        )
        if skipped_no_material:
            self.stdout.write(f"   非本地物料跳过: {skipped_no_material} 条")
        if skipped_no_plant:
            self.stdout.write(f"   无工厂代码跳过: {skipped_no_plant} 条")

    # ------------------------------------------------------------------
    # live sync（Polars iter_slices 分批 + bulk_create）
    # ------------------------------------------------------------------

    def _live_sync(
        self,
        df: pl.DataFrame,
        warehouse_map: dict,
        chunk_size: int,
    ):
        total = df.height
        created = 0
        skipped_no_plant = 0
        skipped_no_material = 0
        processed = 0

        # 生成新批次 ID
        batch_id = uuid.uuid4()
        self.stdout.write(f"   同步批次: {batch_id}")

        # 预加载工厂缓存，避免每次 get_or_create 都查库
        plant_cache = {p.code: p for p in Plant.objects.all()}

        for chunk_df in df.iter_slices(chunk_size):
            with transaction.atomic():
                batch_objects = []
                for row in chunk_df.iter_rows(named=True):
                    matnr = row["MATNR"]
                    werks = row["WERKS"]

                    rm = warehouse_map.get(matnr)
                    if rm is None:
                        skipped_no_material += 1
                        continue

                    if not werks:
                        skipped_no_plant += 1
                        continue

                    # 获取或自动创建工厂
                    plant = plant_cache.get(werks)
                    if plant is None:
                        plant, _ = Plant.objects.get_or_create(
                            code=werks, defaults={'name': ''}
                        )
                        plant_cache[werks] = plant

                    batch_objects.append(RawMaterialStockSnapshot(
                        sync_batch_id=batch_id,
                        raw_material=rm,
                        plant=plant,
                        storage_location=row["LGORT"] or "",
                        batch=row["CHARG"] or "",
                        unrestricted_stock=row["CLABS"] or 0,
                        safety_stock=row["EISBE"] or 0,
                    ))

                if batch_objects:
                    RawMaterialStockSnapshot.objects.bulk_create(batch_objects)
                    created += len(batch_objects)

            processed += chunk_df.height
            self.stdout.write(
                f"   进度: {min(processed, total)}/{total} "
                f"(已创建 {created})"
            )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"[OK] 同步完成！总计 {processed} 条, "
                f"创建 {created} 条, "
                f"非本地物料 {skipped_no_material} 条, "
                f"无工厂 {skipped_no_plant} 条"
            )
        )
        self.stdout.write(f"   批次ID: {batch_id}")