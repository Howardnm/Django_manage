"""
Django 管理命令: 从 SAP 同步物料评估价格到 app_raw_material。

用法:
    python manage.py sync_material_prices                              # 默认: 近12个月
    python manage.py sync_material_prices --periods 6                  # 近6个月
    python manage.py sync_material_prices --all                        # 全量一次性拉取(慢)
    python manage.py sync_material_prices --fiscal-year 2025 --fiscal-month 12  # 指定单月
    python manage.py sync_material_prices --dry-run                    # 仅预览
    python manage.py sync_material_prices --bwkey 3011                 # 按工厂筛选

定时调度 (Windows Task Scheduler):
    触发器: 每月1号
    操作:   启动程序 python.exe
    参数:   manage.py sync_material_prices
    起始于: 项目根目录
"""

from datetime import date

import polars as pl
from dateutil.relativedelta import relativedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from app_sap_services import sap, sap_health_check
from app_sap_services.definitions.price import MaterialPriceQuery
from app_raw_material.models import RawMaterial, RawMaterialPriceRecord


CHUNK_SIZE = 500
DEFAULT_PERIODS = 12  # 默认同步近12个月

# 价格异常阈值 (CNY/kg)，超过此值发出警告
PRICE_WARN_THRESHOLD = 100000


class Command(BaseCommand):
    help = "从 SAP 同步物料评估价格到本地 RawMaterialPriceRecord 表"

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
            "--all", action="store_true", dest="all_periods",
            help="全量模式：不传会计期间参数，SAP一次性返回全部数据（数据量大，较慢）",
        )
        parser.add_argument(
            "--fiscal-year", type=str, default=None,
            help="会计年度，如 '2025'。不传则从当前月往前推",
        )
        parser.add_argument(
            "--fiscal-month", type=str, default=None,
            help="会计期间，如 '01'。需配合 --fiscal-year 使用",
        )
        parser.add_argument(
            "--periods", type=int, default=None,
            help=f"同步最近N个月（默认: {DEFAULT_PERIODS}）。与 --fiscal-year/month 配合时表示以指定月为终点"
        )
        parser.add_argument(
            "--bwkey", type=str, default=None,
            help="评估范围/工厂代码，如 '1010'（可选，不传则查全部工厂）",
        )
        parser.add_argument(
            "--chunk-size", type=int, default=CHUNK_SIZE,
            help=f"数据库分批大小（默认: {CHUNK_SIZE}）",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]
        all_periods = options["all_periods"]
        fiscal_year = options["fiscal_year"]
        fiscal_month = options["fiscal_month"]
        bwkey = options["bwkey"]
        chunk_size = options["chunk_size"]

        # ── 确定查询模式 ──
        if all_periods:
            mode = "all"
            months = None
            scope_desc = "全量（一次性拉取全部期间，较慢）"
        elif fiscal_year and fiscal_month:
            periods = max(1, options["periods"] or 1)
            end_date = date(int(fiscal_year), int(fiscal_month), 1)
            start_date = end_date - relativedelta(months=periods - 1)
            months = self._build_month_list(start_date, end_date)
            if periods == 1:
                mode = "single"
                scope_desc = f"会计年度: {fiscal_year} / 会计期间: {fiscal_month}"
            else:
                mode = "multi"
                scope_desc = (
                    f"{start_date.strftime('%Y-%m')} → {end_date.strftime('%Y-%m')}"
                    f" ({periods} 个月, 终点: {fiscal_year}-{fiscal_month})"
                )
        elif fiscal_year:
            # 只传年度 → 同步该年全部 12 个月
            end_date = date(int(fiscal_year), 12, 1)
            start_date = date(int(fiscal_year), 1, 1)
            months = self._build_month_list(start_date, end_date)
            mode = "multi"
            scope_desc = f"{fiscal_year} 全年 (01-12)"
        elif fiscal_month:
            # 只传月份不传年度 → 报错
            self.stdout.write(
                self.style.ERROR(
                    "   [ERR] --fiscal-month 需配合 --fiscal-year 使用"
                )
            )
            return
        else:
            periods = max(1, options["periods"] or DEFAULT_PERIODS)
            today = date.today()
            end_date = date(today.year, today.month, 1)
            start_date = end_date - relativedelta(months=periods - 1)
            months = self._build_month_list(start_date, end_date)
            mode = "multi"
            scope_desc = (
                f"近 {periods} 个月: "
                f"{start_date.strftime('%Y-%m')} → {end_date.strftime('%Y-%m')}"
            )

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\n=== 开始 SAP 物料价格同步 ===\n"
                f"    范围: {scope_desc}\n"
                f"    工厂: {bwkey or '全部'}"
                + (f"\n    模式: {'逐月查询' if mode == 'multi' else '单次查询'}"
                   if mode != 'single' else "")
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

        # ── 2. 预加载本地物料映射（只做一次）──
        warehouse_map = {
            rm.warehouse_code: rm
            for rm in RawMaterial.objects.all()
        }
        valid_codes = {k for k in warehouse_map.keys() if k}
        self.stdout.write(f"   本地物料总数: {len(valid_codes)}")

        # ── 3. SAP 查询 ──
        try:
            if mode == "all":
                df = self._query_sap(bwkey, None, None)
            elif mode in ("single", "multi"):
                all_dfs = []
                errors = 0
                for fy, fm in months:
                    try:
                        df_month = self._query_sap(bwkey, fy, fm)
                        if not df_month.is_empty():
                            all_dfs.append(df_month)
                    except Exception as e:
                        errors += 1
                        self.stdout.write(
                            self.style.ERROR(
                                f"   [{fy}-{fm}] SAP 查询失败: {e}"
                            )
                        )
                if errors == len(months):
                    self.stdout.write(
                        self.style.ERROR("   所有月份的 SAP 查询均失败，同步终止")
                    )
                    return
                if not all_dfs:
                    self.stdout.write(
                        self.style.WARNING("   没有符合条件的数据，同步结束")
                    )
                    return
                df = pl.concat(all_dfs)
                self.stdout.write(
                    f"   合并 {len(all_dfs)} 个月: {df.height} 条原始记录"
                )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"   [ERR] SAP 查询失败: {e}")
            )
            return

        if df.is_empty():
            self.stdout.write(self.style.WARNING("   没有符合条件的数据，同步结束"))
            return

        # ── 4. Polars 端数据处理 ──
        df = self._transform_prices(df)

        if df.is_empty():
            self.stdout.write(self.style.WARNING("   有效价格数据为空，同步结束"))
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
    # SAP 单月查询
    # ------------------------------------------------------------------

    def _query_sap(self, bwkey, fiscal_year, fiscal_month) -> pl.DataFrame:
        """执行单次 SAP 查询，返回 Polars DataFrame"""
        filters = {}
        if fiscal_year:
            filters["p_lfgja"] = fiscal_year
        if fiscal_month:
            filters["p_lfmon"] = str(fiscal_month).zfill(2)
        if bwkey:
            filters["s_bwkey__eq"] = bwkey

        query = sap.rfc(MaterialPriceQuery)
        if filters:
            query = query.filter(**filters)

        df = query.collect()
        label = f"{fiscal_year}-{fiscal_month}" if fiscal_year else "全量"
        self.stdout.write(f"   [{label}] SAP 返回: {df.height} 条")
        return df

    # ------------------------------------------------------------------
    # 月份列表生成
    # ------------------------------------------------------------------

    @staticmethod
    def _build_month_list(start_date: date, end_date: date):
        """生成 [(fiscal_year, fiscal_month), ...] 从 start → end"""
        months = []
        current = start_date
        while current <= end_date:
            months.append((str(current.year), f"{current.month:02d}"))
            current += relativedelta(months=1)
        return months

    # ------------------------------------------------------------------
    # Polars 价格转换
    # ------------------------------------------------------------------

    def _transform_prices(self, df: pl.DataFrame) -> pl.DataFrame:
        """Polars 端：价格单位换算 + 多工厂聚合 + 异常值过滤"""
        before = df.height

        # 过滤 PEINH <= 0（除零保护）
        df = df.filter(pl.col("PEINH") > 0)

        # 计算单价: VERPR / PEINH
        df = df.with_columns(
            (pl.col("VERPR") / pl.col("PEINH")).round(2).alias("UNIT_PRICE")
        )

        # 过滤无效价格
        df = df.filter(pl.col("UNIT_PRICE") > 0)

        # 多工厂/多期间聚合：同一物料+期间取平均价
        df = df.group_by(["MATNR", "LFGJA", "LFMON"]).agg(
            pl.col("UNIT_PRICE").mean().round(2).alias("UNIT_PRICE"),
            pl.col("BWKEY").count().alias("PLANT_COUNT"),
        )

        after = df.height
        self.stdout.write(
            f"   价格换算: {before} 条 → 有效 {after} 条 "
            f"(VERPR/PEINH=单价, 多工厂取均值)"
        )

        return df

    # ------------------------------------------------------------------
    # 每行 source 文本
    # ------------------------------------------------------------------

    @staticmethod
    def _make_source(lfgja: str, lfmon: str) -> str:
        """生成价格来源标识"""
        return f"SAP MBEW {lfgja}-{lfmon}"

    # ------------------------------------------------------------------
    # dry-run
    # ------------------------------------------------------------------

    def _dry_run(self, df: pl.DataFrame, warehouse_map: dict):
        will_create = 0
        will_update = 0
        skipped_invalid = 0
        price_warns = 0

        for row in df.iter_rows(named=True):
            matnr = row["MATNR"]
            unit_price = row["UNIT_PRICE"]

            rm = warehouse_map.get(matnr)
            if rm is None:
                skipped_invalid += 1
                continue

            try:
                price_date = date(int(row["LFGJA"]), int(row["LFMON"]), 1)
            except (ValueError, TypeError):
                skipped_invalid += 1
                continue

            if unit_price > PRICE_WARN_THRESHOLD:
                price_warns += 1

            existing = RawMaterialPriceRecord.objects.filter(
                raw_material=rm, date=price_date
            ).first()

            source = self._make_source(row["LFGJA"], row["LFMON"])
            if existing:
                will_update += 1
                self.stdout.write(
                    f"   [~] 将更新: {rm.name} ({matnr}) "
                    f"{price_date}: {existing.price} -> {unit_price}"
                )
            else:
                will_create += 1
                self.stdout.write(
                    f"   [+] 将创建: {rm.name} ({matnr}) "
                    f"{price_date}: CNY{unit_price} [{source}]"
                )

        total = will_create + will_update
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"[OK] 预览完成！共 {total} 条 "
                f"(将创建 {will_create}, 将更新 {will_update})"
            )
        )
        if price_warns:
            self.stdout.write(
                self.style.WARNING(
                    f"   价格异常 (>CNY{PRICE_WARN_THRESHOLD}/kg): {price_warns} 条"
                )
            )
        if skipped_invalid:
            self.stdout.write(f"   无效数据跳过: {skipped_invalid} 条")

    # ------------------------------------------------------------------
    # live sync（Polars iter_slices 分批 + transaction.atomic）
    # ------------------------------------------------------------------

    def _live_sync(
        self,
        df: pl.DataFrame,
        warehouse_map: dict,
        chunk_size: int,
    ):
        total = df.height
        created = 0
        updated = 0
        skipped_invalid = 0
        processed = 0
        affected_materials = set()
        price_warn_count = 0

        for chunk_df in df.iter_slices(chunk_size):
            with transaction.atomic():
                for row in chunk_df.iter_rows(named=True):
                    matnr = row["MATNR"]
                    unit_price = row["UNIT_PRICE"]

                    rm = warehouse_map.get(matnr)
                    if rm is None:
                        skipped_invalid += 1
                        continue

                    try:
                        price_date = date(
                            int(row["LFGJA"]), int(row["LFMON"]), 1
                        )
                    except (ValueError, TypeError):
                        skipped_invalid += 1
                        continue

                    if unit_price > PRICE_WARN_THRESHOLD:
                        price_warn_count += 1

                    source_text = self._make_source(
                        row["LFGJA"], row["LFMON"]
                    )

                    try:
                        record, is_new = RawMaterialPriceRecord.objects.update_or_create(
                            raw_material=rm,
                            date=price_date,
                            defaults={
                                "price": unit_price,
                                "source": source_text,
                            },
                        )
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(
                                f"   [ERR] 保存失败: {rm.name} ({matnr}) — {e}"
                            )
                        )
                        skipped_invalid += 1
                        continue

                    if is_new:
                        created += 1
                    else:
                        updated += 1

                    affected_materials.add(rm)

            processed += chunk_df.height
            self.stdout.write(
                f"   进度: {min(processed, total)}/{total} "
                f"(新建 {created}, 更新 {updated})"
            )

        # ── 更新 _latest_price 触发 FormulaBOM 级联重算 ──
        if affected_materials:
            self.stdout.write(
                f"\n   更新 {len(affected_materials)} 个物料的缓存价格..."
            )
            price_updated = 0
            for rm in affected_materials:
                new_price = rm.latest_price
                if rm._latest_price != new_price:
                    rm._latest_price = new_price
                    rm.save(update_fields=["_latest_price"])
                    price_updated += 1
            self.stdout.write(
                f"   价格变更: {price_updated} 个物料"
            )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"[OK] 同步完成！总计 {processed} 条, "
                f"新建 {created} 个, 更新 {updated} 个, "
                f"无效 {skipped_invalid} 个"
            )
        )
        if price_warn_count:
            self.stdout.write(
                self.style.WARNING(
                    f"   价格异常 (>CNY{PRICE_WARN_THRESHOLD}/kg): {price_warn_count} 条"
                )
            )
