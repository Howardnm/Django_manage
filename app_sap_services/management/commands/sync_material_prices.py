"""
Django 管理命令: 从 SAP 同步物料评估价格到 app_raw_material。

用法:
    python manage.py sync_material_prices                              # 同步当前月份
    python manage.py sync_material_prices --dry-run                    # 仅预览
    python manage.py sync_material_prices --limit 50                   # 限制条数
    python manage.py sync_material_prices --fiscal-year 2026 --fiscal-month 06  # 指定期间
    python manage.py sync_material_prices --periods 12                 # 全量: 近12个月
    python manage.py sync_material_prices --periods 24 --dry-run       # 预览全量(近24个月)

定时调度 (Windows Task Scheduler):
    触发器: 每月1号
    操作:   启动程序 python.exe
    参数:   manage.py sync_material_prices --periods 12
    起始于: 项目根目录

注意:
    当前 SAP 账号可能无 ZRFC_GET_MBEW 的 RFC 授权，需联系管理员开通。
"""

from datetime import date
from dateutil.relativedelta import relativedelta

import polars as pl

from django.core.management.base import BaseCommand
from django.db import transaction

from app_sap_services import sap, sap_health_check
from app_sap_services.definitions.price import MaterialPriceQuery
from app_raw_material.models import RawMaterial, RawMaterialPriceRecord


CHUNK_SIZE = 500

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
            "--fiscal-year", type=str, default=None,
            help="会计年度，如 '2026'（默认: 当前年份）",
        )
        parser.add_argument(
            "--fiscal-month", type=str, default=None,
            help="会计期间，如 '07'（默认: 当前月份，补零两位）",
        )
        parser.add_argument(
            "--periods", type=int, default=1,
            help=(
                "同步近N个月的评估价格，1=仅当月(默认)。"
                "例: --periods 12 从11个月前同步到当月（覆盖整年历史），"
                "按月逐一查询 SAP 后合并写入"
            ),
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
        bwkey = options["bwkey"]
        periods = max(1, options["periods"])
        chunk_size = options["chunk_size"]

        # 确定终止月份（--fiscal-year/month 指定的期间，或默认当前月份）
        today = date.today()
        end_year = int(options["fiscal_year"] or today.year)
        end_month = int(options["fiscal_month"] or today.month)
        end_date = date(end_year, end_month, 1)

        # 反推起始月份
        start_date = end_date - relativedelta(months=periods - 1)

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\n=== 开始 SAP 物料价格同步 ===\n"
                f"    同步范围: {start_date.strftime('%Y-%m')} → {end_date.strftime('%Y-%m')}"
                f" ({periods} 个月)\n"
                f"    工厂筛选: {bwkey or '全部'}"
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

        # ── 2. 逐月查询 SAP ──
        months = self._build_month_list(start_date, end_date)
        all_dfs = []
        sap_errors = 0

        for fy, fm in months:
            month_label = f"{fy}-{fm}"
            try:
                filters = {"p_lfgja": fy, "p_lfmon": fm}
                if bwkey:
                    filters["s_bwkey__eq"] = bwkey

                query = sap.rfc(MaterialPriceQuery).filter(**filters)
                if limit and limit > 0:
                    query = query.limit(limit)

                df_month = query.collect()
                self.stdout.write(
                    f"   [{month_label}] SAP 返回: {df_month.height} 条"
                )
                if not df_month.is_empty():
                    all_dfs.append(df_month)
            except Exception as e:
                sap_errors += 1
                self.stdout.write(
                    self.style.ERROR(f"   [{month_label}] SAP 查询失败: {e}")
                )
                continue

        if sap_errors == len(months):
            self.stdout.write(
                self.style.ERROR("   所有月份的 SAP 查询均失败，同步终止")
            )
            return

        if not all_dfs:
            self.stdout.write(self.style.WARNING("   没有符合条件的数据，同步结束"))
            return

        # 合并所有月份
        df = pl.concat(all_dfs)
        before_merge = sum(d.height for d in all_dfs)
        self.stdout.write(
            f"   合并 {len(all_dfs)} 个月数据: {before_merge} 条 → {df.height} 条"
        )

        # ── 3. Polars 端数据处理 ──
        df = self._transform_prices(df)

        if df.is_empty():
            self.stdout.write(self.style.WARNING("   有效价格数据为空，同步结束"))
            return

        # ── 4. 预加载本地物料映射 ──
        matnrs = df["MATNR"].unique().to_list()
        warehouse_map = {
            rm.warehouse_code: rm
            for rm in RawMaterial.objects.filter(warehouse_code__in=matnrs)
        }
        missing_count = len(matnrs) - len(warehouse_map)
        self.stdout.write(
            f"   本地已存在物料: {len(warehouse_map)}/{len(matnrs)}"
            + (f" (缺失 {missing_count})" if missing_count else "")
        )

        # ── 5. 同步 ──
        if dry_run:
            self._dry_run(df, warehouse_map)
        else:
            self._live_sync(df, warehouse_map, chunk_size)

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

        # 多工厂聚合：同一物料+期间取平均价
        df = df.group_by(["MATNR", "LFGJA", "LFMON"]).agg(
            pl.col("UNIT_PRICE").mean().round(2).alias("UNIT_PRICE"),
            pl.col("BWKEY").count().alias("PLANT_COUNT"),
        )

        after = df.height
        self.stdout.write(
            f"   价格换算: SAP {before} 条 → 有效 {after} 条 "
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
        skipped_missing = 0
        skipped_invalid = 0

        for row in df.iter_rows(named=True):
            matnr = row["MATNR"]
            unit_price = row["UNIT_PRICE"]

            if not matnr:
                skipped_invalid += 1
                continue

            # 检查价格异常
            if unit_price > PRICE_WARN_THRESHOLD:
                self.stdout.write(
                    self.style.WARNING(
                        f"   [!] 价格异常: {matnr} = {unit_price} CNY/kg "
                        f"(>{PRICE_WARN_THRESHOLD})"
                    )
                )

            # 匹配本地物料
            rm = warehouse_map.get(matnr)
            if rm is None:
                skipped_missing += 1
                self.stdout.write(
                    f"   [!] 本地无此物料: {matnr} (价格: {unit_price})"
                )
                continue

            # 构造日期
            try:
                price_date = date(int(row["LFGJA"]), int(row["LFMON"]), 1)
            except (ValueError, TypeError):
                skipped_invalid += 1
                continue

            # 检查是否已存在
            existing = RawMaterialPriceRecord.objects.filter(
                raw_material=rm, date=price_date
            ).first()

            source = self._make_source(row["LFGJA"], row["LFMON"])
            if existing:
                will_update += 1
                self.stdout.write(
                    f"   [~] 将更新: {rm.name} ({matnr}) "
                    f"{price_date}: ¥{existing.price} → ¥{unit_price}"
                )
            else:
                will_create += 1
                self.stdout.write(
                    f"   [+] 将创建: {rm.name} ({matnr}) "
                    f"{price_date}: ¥{unit_price} [{source}]"
                )

        total = will_create + will_update
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"[OK] 预览完成！共 {total} 条 "
                f"(将创建 {will_create}, 将更新 {will_update})"
            )
        )
        if skipped_missing:
            self.stdout.write(
                self.style.WARNING(
                    f"   本地缺失物料: {skipped_missing} 条（需先运行 sync_raw_materials）"
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
        skipped_missing = 0
        skipped_invalid = 0
        processed = 0
        affected_materials = set()

        for chunk_df in df.iter_slices(chunk_size):
            with transaction.atomic():
                for row in chunk_df.iter_rows(named=True):
                    matnr = row["MATNR"]
                    unit_price = row["UNIT_PRICE"]

                    if not matnr:
                        skipped_invalid += 1
                        continue

                    # 价格异常警告（但不跳过）
                    if unit_price > PRICE_WARN_THRESHOLD:
                        self.stdout.write(
                            self.style.WARNING(
                                f"   [!] 价格异常: {matnr} = {unit_price} CNY/kg"
                            )
                        )

                    # 匹配本地物料
                    rm = warehouse_map.get(matnr)
                    if rm is None:
                        skipped_missing += 1
                        self.stdout.write(
                            f"   [!] 本地无此物料: {matnr} (跳过)"
                        )
                        continue

                    # 构造日期
                    try:
                        price_date = date(
                            int(row["LFGJA"]), int(row["LFMON"]), 1
                        )
                    except (ValueError, TypeError):
                        skipped_invalid += 1
                        continue

                    source_text = self._make_source(
                        row["LFGJA"], row["LFMON"]
                    )

                    # 写入/更新价格记录
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
                new_price = rm.latest_price  # 属性从 price_records 读取最新
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
                f"缺失物料 {skipped_missing} 个, 无效 {skipped_invalid} 个"
            )
        )
