"""
Django 管理命令: 从 SAP 同步物料评估价格到 app_raw_material。

用法:
    python manage.py sync_material_prices                              # 全部本地物料，全历史
    python manage.py sync_material_prices --limit 50                   # 只处理前 50 个物料
    python manage.py sync_material_prices --bwkey 3011                 # 只看某工厂的价格
    python manage.py sync_material_prices --periods 12                 # 只入库近 12 个月
    python manage.py sync_material_prices --fiscal-year 2026           # 只入库该年度
    python manage.py sync_material_prices --fiscal-year 2026 --fiscal-month 9   # 只入库该月
    python manage.py sync_material_prices --dry-run                    # 仅预览，不写库
    python manage.py sync_material_prices --verbose                    # 逐物料打印明细
    python manage.py sync_material_prices --purge --dry-run            # 预览「清空重建」
    python manage.py sync_material_prices --purge                      # 清空本地价格后重建

定时调度 (Windows Task Scheduler):
    触发器: 每月1号
    操作:   启动程序 python.exe
    参数:   manage.py sync_material_prices
    起始于: 项目根目录

取数策略：逐物料遍历
    遍历本地 RawMaterial.warehouse_code，每个物料一次 RFC 调用，取回该物料的
    全部历史价格（含其在所有工厂的记录）。实测 2654 个物料约 25~50 秒、
    约 6.8 万行；而「按工厂全量拉取再筛掉非本地物料」要 50 万行以上，
    「不传工厂」更是 556 万行、近 10 分钟。

    之所以能这样做：ZRFC_GET_MBEWH 支持 IS_QUERY.S_MATNR 服务端筛选，
    而旧接口 ZRFC_GET_MBEW 没有。

接口说明：
    ZRFC_GET_MBEWH **没有期间入参**，一次返回全部历史月份。因此
    --fiscal-year / --fiscal-month / --periods 都是客户端过滤，只决定哪些
    期间会被写入本地；SAP 侧仅 --bwkey 是真正的服务端筛选。
    默认不过滤期间，即全历史入库。

写入语义（幂等 upsert）：
    按 (物料, 工厂, 日期) 覆盖 —— SAP 某天价格更新时会覆盖该物料当天对应
    工厂的价格，确保同一物料+工厂+日期不会同时存在两条记录。
    幂等键是模型的 unique_together('raw_material','plant','date')，
    重复执行安全。

--purge（清空重建）：
    删除 RawMaterialPriceRecord 全表后重新同步。用于丢弃历史遗留的不可信数据
    （旧 RFC 写入的期间错位记录、指向从无数据的工厂的幻影记录等）。
    **不可逆**，执行前会先做一次探针查询确认价格 RFC 真的可用，
    避免「清空后才发现 SAP 不可用」。

注意：
    - 未知工厂代码将在同步时自动创建 Plant 记录。
    - 单价口径: UNIT_PRICE = VERPR / PEINH
      （实测 STPRS/PVPRS 恒为 0，只有 VERPR 有值；PEINH 取值为 1 与 10000）。

数据稀疏性（不是 bug）:
    SAP 的 MBEWH 表只在估值发生变化时记录一行，因此某些物料只有少数几个
    期间的记录，中间会「缺月」；另有一部分物料（实测约 6~10%）在 SAP 里
    完全没有价格数据，命令会跳过它们并保留本地已有记录。
    价格序列在读取时由 app_raw_material/services/price_service.py 按可用点
    计算，缺月不影响正确性。
"""

from collections import Counter
from datetime import date
from decimal import Decimal

import polars as pl
from dateutil.relativedelta import relativedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from app_sap_services import (
    sap,
    sap_health_check,
    SAPError,
    SAPBusinessError,
)
from app_sap_services.definitions.price import MaterialPriceQuery
from app_raw_material.models import Plant, RawMaterial, RawMaterialPriceRecord


CHUNK_SIZE = 500          # 写库分批大小
PROGRESS_EVERY = 200      # 每处理多少个物料打印一次进度

# 价格异常阈值 (CNY/kg)，超过此值发出警告
PRICE_WARN_THRESHOLD = 100000

# RawMaterialPriceRecord.price 的语义是「元/kg」，模型没有币种字段，
# 非该币种记录写进去会永久污染均价口径，因此直接跳过
ALLOWED_CURRENCY = "CNY"


class Command(BaseCommand):
    help = "从 SAP 同步物料评估价格到本地 RawMaterialPriceRecord 表（逐物料遍历）"

    # 由 handle() 按 --include-future 覆盖；类属性给默认值，
    # 使 _apply_period_filter 可被单独调用/测试
    include_future = False
    verbose = False

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="仅查询并预览，不写入数据库",
        )
        parser.add_argument(
            "--limit", type=int, default=0,
            help="只处理排序后的前 N 个物料（0 = 全部）。用于小样本试跑",
        )
        parser.add_argument(
            "--bwkey", type=str, default=None,
            help="评估范围/工厂代码，如 '3011'。只看该工厂的价格（服务端筛选）",
        )
        parser.add_argument(
            "--periods", type=int, default=None,
            help="只入库最近 N 个期间（默认不启用 = 全历史）",
        )
        parser.add_argument(
            "--fiscal-year", type=int, default=None,
            help="只入库指定会计年度，如 2025（客户端过滤）",
        )
        parser.add_argument(
            "--fiscal-month", type=int, default=None,
            help="只入库指定会计期间，如 1~12（客户端过滤）。需配合 --fiscal-year",
        )
        parser.add_argument(
            "--include-future", action="store_true", dest="include_future",
            help="保留晚于当前会计期间的记录（默认截断，避免未来期间被当成最新价格）",
        )
        parser.add_argument(
            "--chunk-size", type=int, default=CHUNK_SIZE,
            help=f"写库分批大小（默认: {CHUNK_SIZE}）",
        )
        parser.add_argument(
            "--purge", action="store_true",
            help="清空本地全部价格记录后重新同步（干净重建；不可逆，请先用 --dry-run 预览）",
        )
        parser.add_argument(
            "--verbose", action="store_true",
            help="逐物料打印明细（默认只在每个物料批次打印进度）",
        )

    # ------------------------------------------------------------------
    # 入口
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]
        bwkey = options["bwkey"]
        chunk_size = max(1, options["chunk_size"])
        fiscal_year = options["fiscal_year"]
        fiscal_month = options["fiscal_month"]
        self.include_future = options["include_future"]
        self.verbose = options["verbose"]

        if fiscal_month and not fiscal_year:
            raise CommandError("--fiscal-month 需配合 --fiscal-year 使用")
        if fiscal_month and not 1 <= fiscal_month <= 12:
            raise CommandError("--fiscal-month 取值范围为 1~12")

        # --purge 是「整表清空 + 全量重建」。若同时收窄了重建范围，
        # 清掉的数据不会被补回来（例如 --limit 20 会清空全表却只重建 20 个物料），
        # 因此直接拒绝这种组合，而不是留下一个静默丢数据的坑。
        if options["purge"]:
            narrowing = [
                name for name, given in (
                    ("--limit", limit),
                    ("--bwkey", bwkey),
                    ("--periods", options["periods"]),
                    ("--fiscal-year", fiscal_year),
                    ("--fiscal-month", fiscal_month),
                ) if given
            ]
            if narrowing:
                raise CommandError(
                    f"--purge 是整表清空后全量重建，不能与 {', '.join(narrowing)} 同时使用 —— "
                    f"清掉却不在重建范围内的数据会永久丢失。"
                    f"若要单独试跑请去掉 --purge。"
                )

        scope_desc, ym_range = self._resolve_scope(
            fiscal_year=fiscal_year,
            fiscal_month=fiscal_month,
            periods=max(1, options["periods"] or 0) if options["periods"] else None,
        )

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\n=== 开始 SAP 物料价格同步 ===\n"
                f"    期间: {scope_desc}\n"
                f"    工厂: {bwkey or '全部'}"
            )
        )
        if dry_run:
            self.stdout.write(
                self.style.WARNING("   [DRY-RUN] 预览模式，不会写入数据库")
            )

        # ── 1. 健康检查 ──
        health = sap_health_check()
        if health.get("status") != "healthy":
            raise CommandError(f"SAP 连接失败: {health.get('error', '未知错误')}")
        self.stdout.write(
            f"   [OK] SAP 连接正常 "
            f"(ashost={health.get('ashost')}, client={health.get('client')})"
        )

        # ── 2. 预载本地物料 ──
        warehouse_map = {
            rm.warehouse_code: rm
            for rm in RawMaterial.objects.all()
            if rm.warehouse_code
        }
        codes = sorted(warehouse_map)
        if limit and limit > 0:
            codes = codes[:limit]
        self.stdout.write(f"   本地物料: {len(codes)} 个（共 {len(warehouse_map)} 个有编码）")

        if not codes:
            self.stdout.write(self.style.WARNING("   没有可同步的物料，结束"))
            return

        # ── 3. 清空本地价格记录（可选）──
        if options["purge"]:
            self._purge(dry_run=dry_run, probe_code=codes[0], bwkey=bwkey)

        # ── 4. 逐物料遍历 ──
        stats = self._sync_materials(
            codes=codes,
            warehouse_map=warehouse_map,
            ym_range=ym_range,
            bwkey=bwkey,
            chunk_size=chunk_size,
            dry_run=dry_run,
        )

        # ── 5. 汇总 ──
        self._report(stats, dry_run=dry_run)

        if stats["failed"]:
            raise CommandError(
                f"有 {stats['failed']} 个物料同步失败，详见上方日志"
            )

    # ------------------------------------------------------------------
    # 清空本地价格记录（干净重建）
    # ------------------------------------------------------------------

    def _purge(self, dry_run, probe_code, bwkey):
        """
        清空 RawMaterialPriceRecord 全表。

        不可逆操作，因此先做一次探针查询：确认价格 RFC 真能调通再删。
        否则「清空后才发现 SAP 不可用」会白丢全部数据（健康检查只验连通性，
        验不了这个 RFC 的授权与可用性）。
        """
        existing = RawMaterialPriceRecord.objects.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"   [PURGE] 将清空本地全部 {existing} 条价格记录（预览，未执行）"
                )
            )
            return

        # 探针：空结果（该物料没价格）是合法的，只有真异常才中止
        try:
            self._query_one(probe_code, bwkey)
        except SAPError as e:
            raise CommandError(
                f"清空前探针查询失败，已中止以避免数据丢失: {e}"
            )

        if not existing:
            self.stdout.write("   [PURGE] 本地无价格记录，跳过")
            return

        self.stdout.write(
            self.style.WARNING(f"   [PURGE] 清空本地全部 {existing} 条价格记录……")
        )
        RawMaterialPriceRecord.objects.all().delete()
        self.stdout.write(f"   [PURGE] 已清空（原 {existing} 条），开始重建")

    # ------------------------------------------------------------------
    # 期间范围解析（全部为客户端过滤）
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_scope(fiscal_year, fiscal_month, periods):
        """
        解析期间范围。默认不启用任何过滤（全历史）。

        Returns:
            (范围描述, ym_range)
            ym_range 为 None 表示不过滤；否则为闭区间 (lo, hi)，两端形如 YYYYMM
        """
        if fiscal_year and fiscal_month:
            return (
                f"会计年度 {fiscal_year} / 会计期间 {fiscal_month:02d}",
                (fiscal_year * 100 + fiscal_month, fiscal_year * 100 + fiscal_month),
            )

        if fiscal_year:
            return (
                f"{fiscal_year} 全年 (01-12)",
                (fiscal_year * 100 + 1, fiscal_year * 100 + 12),
            )

        if periods:
            today = date.today()
            end = date(today.year, today.month, 1)
            start = end - relativedelta(months=periods - 1)
            return (
                f"近 {periods} 个月: {start.strftime('%Y-%m')} → {end.strftime('%Y-%m')}",
                (start.year * 100 + start.month, end.year * 100 + end.month),
            )

        return "全历史（SAP 返回的全部期间）", None

    # ------------------------------------------------------------------
    # 核心：逐物料遍历
    # ------------------------------------------------------------------

    def _sync_materials(self, codes, warehouse_map, ym_range, bwkey, chunk_size, dry_run):
        """
        遍历物料逐个取数并累积写库。

        Returns:
            dict: 统计计数（total / empty / failed / skipped / written / rows / price_warn）
                  以及 warnings（Counter：future / currency / dedupe / plants_created）
        """
        stats = {
            "total": len(codes),
            "with_price": 0,   # 实际产出了有效价格记录的物料
            "empty": 0,        # SAP 完全没返回该物料的行
            "no_price": 0,     # SAP 有行，但全部价格无效（VERPR=0 等）被过滤
            "failed": 0,       # 调用异常
            "skipped": 0,      # 单行无法构造（日期非法、无工厂等）
            "written": 0,      # 实际写入（或 dry-run 下将写入）的条数
            "price_warn": 0,   # 价格异常计数
        }
        warnings = Counter()
        errors = []

        plant_map = {p.code: p for p in Plant.objects.all()}
        pending = []

        for idx, code in enumerate(codes, 1):
            try:
                df = self._query_one(code, bwkey)
            except SAPBusinessError as e:
                # 已声明的空结果文本不会走到这里；能到这里的是真业务错误
                stats["failed"] += 1
                errors.append((code, str(e)))
                self.stderr.write(self.style.ERROR(f"   [{code}] SAP 业务错误: {e}"))
                continue
            except SAPError as e:
                stats["failed"] += 1
                errors.append((code, str(e)))
                self.stderr.write(self.style.ERROR(f"   [{code}] SAP 调用失败: {e}"))
                continue

            if df.is_empty():
                stats["empty"] += 1
                continue

            df = self._apply_period_filter(df, ym_range, warnings)
            df = self._transform_prices(df, warnings)

            # 区分「SAP 没这条记录」与「有记录但价格全是 0 被过滤」——
            # 后者实测占相当大的比例（很多物料在 MBEWH 里有行但 VERPR=0），
            # 混在一起统计会让人误以为大量物料同步失败。
            if df.is_empty():
                stats["no_price"] += 1
                continue

            rm = warehouse_map[code]
            before = len(pending)
            for row in df.iter_rows(named=True):
                obj = self._build_record(rm, row, plant_map, warnings, dry_run)
                if obj is None:
                    stats["skipped"] += 1
                    continue
                if row["UNIT_PRICE"] > PRICE_WARN_THRESHOLD:
                    stats["price_warn"] += 1
                pending.append(obj)
            if len(pending) > before:
                stats["with_price"] += 1

            if self.verbose:
                self.stdout.write(
                    f"   [{code}] {df.height} 条"
                    + (f"（累计待写 {len(pending)}）" if pending else "")
                )

            # 累积到批大小就落库，避免 2654 次小事务
            if len(pending) >= chunk_size:
                stats["written"] += self._flush(pending, dry_run=dry_run)
                pending.clear()

            if idx % PROGRESS_EVERY == 0:
                self.stdout.write(
                    f"   进度: {idx}/{stats['total']} "
                    f"（累计待写 {stats['written'] + len(pending)} 条, "
                    f"有价格 {stats['with_price']} 个, "
                    f"SAP 无记录 {stats['empty']} 个, "
                    f"失败 {stats['failed']} 个）"
                )

        # 收尾 flush
        if pending:
            stats["written"] += self._flush(pending, dry_run=dry_run)
            pending.clear()

        stats["warnings"] = warnings
        stats["errors"] = errors
        return stats

    def _query_one(self, code, bwkey=None) -> pl.DataFrame:
        """单物料查询：服务端按物料号（可选再按工厂）筛选。"""
        filters = {"s_matnr__eq": code}
        if bwkey:
            filters["s_bwkey__eq"] = bwkey
        return sap.rfc(MaterialPriceQuery).filter(**filters).collect()

    def _build_record(self, rm, row, plant_map, warnings, dry_run):
        """单行 → RawMaterialPriceRecord；无法构造时返回 None。"""
        bwkey = (row.get("BWKEY") or "").strip()
        if not bwkey:
            return None

        price_date = self._to_date(row["BDATJ"], row["POPER"])
        if price_date is None:
            return None

        plant = plant_map.get(bwkey)
        if plant is None:
            if dry_run:
                # 预览模式不建工厂，只记账
                warnings["plants_created"] += 1
                return None
            plant, _ = Plant.objects.get_or_create(code=bwkey, defaults={"name": ""})
            plant_map[bwkey] = plant
            warnings["plants_created"] += 1
            self.stdout.write(f"   自动创建工厂: {bwkey}")

        return RawMaterialPriceRecord(
            raw_material=rm,
            plant=plant,
            date=price_date,
            price=Decimal(str(row["UNIT_PRICE"])),
            source=self._make_source(row["BDATJ"], row["POPER"], bwkey),
        )

    def _flush(self, objs, dry_run) -> int:
        """
        批量 upsert 一批记录。

        幂等键 unique_together('raw_material','plant','date') 直接映射到 upsert：
        已存在则更新 price/source，不存在则插入（幂等，重复执行安全）。

        Returns:
            本次处理的条数
        """
        if dry_run:
            return len(objs)

        # unique_fields 是否要传取决于后端能力，见 _conflict_kwargs()
        with transaction.atomic():
            RawMaterialPriceRecord.objects.bulk_create(
                objs,
                batch_size=len(objs),
                update_conflicts=True,
                update_fields=["price", "source"],
                **self._conflict_kwargs(),
            )
        return len(objs)

    @staticmethod
    def _conflict_kwargs() -> dict:
        """
        bulk_create(update_conflicts=True) 的 unique_fields 参数，按后端能力给出。

        这是 Django ORM 的 API 约束，不是手写 SQL：Django 的 upsert 能力按后端
        分为两类，MySQL 那一类不支持指定冲突目标，传了 unique_fields 会直接抛
        NotSupportedError。两种情况下 Django 都会自己决定生成什么语句。

        Returns:
            {"unique_fields": [...]} 或 {}
        """
        if connection.features.supports_update_conflicts_with_target:
            return {"unique_fields": ["raw_material", "plant", "date"]}
        return {}

    # ------------------------------------------------------------------
    # 报告
    # ------------------------------------------------------------------

    def _report(self, stats, dry_run):
        w = stats["warnings"]
        verb = "将写入" if dry_run else "已写入"

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"[OK] 同步完成！物料 {stats['total']} 个："
                f"有价格 {stats['with_price']} 个，"
                f"SAP 无记录 {stats['empty']} 个，"
                f"有记录但无有效价格 {stats['no_price']} 个，"
                f"失败 {stats['failed']} 个"
            )
        )
        self.stdout.write(f"     {verb} {stats['written']} 条价格记录")
        self.stdout.write(
            "     （同一物料+工厂+日期已存在的会被覆盖更新，不单独统计数量）"
        )

        if w.get("future"):
            self.stdout.write(
                self.style.WARNING(
                    f"     截断未来期间 {w['future']} 条（如需保留请加 --include-future）"
                )
            )
        if w.get("currency"):
            self.stdout.write(
                self.style.WARNING(
                    f"     跳过非 {ALLOWED_CURRENCY} 记录 {w['currency']} 条"
                )
            )
        if w.get("dedupe"):
            self.stdout.write(
                self.style.WARNING(
                    f"     同一(物料,工厂,期间)多条成本估算，按 KALNR 最大者去重 {w['dedupe']} 条"
                )
            )
        if w.get("plants_created"):
            self.stdout.write(f"     自动创建工厂 {w['plants_created']} 个")
        if stats["skipped"]:
            self.stdout.write(f"     无效数据跳过: {stats['skipped']} 条")
        if stats["price_warn"]:
            self.stdout.write(
                self.style.WARNING(
                    f"     价格异常 (>CNY{PRICE_WARN_THRESHOLD}/kg): {stats['price_warn']} 条"
                )
            )

        if stats["failed"]:
            self.stdout.write(
                self.style.ERROR("     失败示例（最多 10 个）:")
            )
            for code, err in stats["errors"][:10]:
                self.stdout.write(self.style.ERROR(f"       {code}: {err}"))

    # ------------------------------------------------------------------
    # 客户端期间过滤
    # ------------------------------------------------------------------

    def _apply_period_filter(self, df: pl.DataFrame, ym_range, warnings) -> pl.DataFrame:
        """按 BDATJ/POPER 过滤期间。两端均形如 YYYYMM，整数比较最省事。"""
        # BDATJ/POPER 无法解析（NUMC 异常值）→ 丢弃，避免带着 None 往下走
        df = df.drop_nulls(subset=["BDATJ", "POPER"])
        ym = pl.col("BDATJ") * 100 + pl.col("POPER")

        # 未来期间护栏：price_service 取「最大日期」作为最新单价，一条未来期间的
        # 记录会静默变成当前价格并污染配方成本。SAP 会预建整年的空期间（VERPR=0，
        # 通常已被 UNIT_PRICE>0 过滤），但这里不依赖那个巧合。
        if not self.include_future:
            current_ym = self._current_ym()
            future = df.filter(ym > current_ym)
            if future.height:
                warnings["future"] += future.height
                df = df.filter(ym <= current_ym)

        if ym_range is None:
            return df

        lo, hi = ym_range
        return df.filter((ym >= lo) & (ym <= hi))

    @staticmethod
    def _current_ym() -> int:
        """当前会计期间，形如 YYYYMM。"""
        today = date.today()
        return today.year * 100 + today.month

    # ------------------------------------------------------------------
    # Polars 价格转换
    # ------------------------------------------------------------------

    def _transform_prices(self, df: pl.DataFrame, warnings) -> pl.DataFrame:
        """Polars 端：价格单位换算 + 货币守卫 + 去重（保留工厂维度）"""
        # 价格/单位字段为空（NUMC/DEC 解析失败）→ 丢弃
        df = df.drop_nulls(subset=["BDATJ", "POPER", "PEINH", "VERPR"])

        # 币种守卫：price 列语义是「元/kg」，模型没有币种字段
        currency = pl.col("WAERS").fill_null("")
        other = df.filter(currency != ALLOWED_CURRENCY)
        if other.height:
            warnings["currency"] += other.height
            df = df.filter(currency == ALLOWED_CURRENCY)

        # 过滤 PEINH <= 0（除零保护，必须在除法之前）
        df = df.filter(pl.col("PEINH") > 0)

        # 计算单价: VERPR / PEINH（实测只有 VERPR 有值，STPRS/PVPRS 恒为 0）
        df = df.with_columns(
            (pl.col("VERPR") / pl.col("PEINH")).round(2).alias("UNIT_PRICE")
        )

        # 过滤无效价格
        df = df.filter(pl.col("UNIT_PRICE") > 0)

        # ORM 的批量 upsert 不允许同一批内出现重复的幂等键（否则后端会直接报错），
        # 因此必须先去重。实测 (MATNR,BWKEY,BDATJ,POPER) 无重复，这里是防御性处理。
        keys = ["MATNR", "BWKEY", "BDATJ", "POPER"]
        dup_count = df.height - df.select(keys).unique().height
        if dup_count:
            warnings["dedupe"] += dup_count
            df = df.sort(keys + ["KALNR"]).unique(subset=keys, keep="last")

        return df

    # ------------------------------------------------------------------
    # 会计期间 → 日期
    # ------------------------------------------------------------------

    @staticmethod
    def _to_date(bdatj, poper):
        """
        会计年度 + 会计期间 → 该期间首日。

        Args:
            bdatj: 会计年度（int，如 2026）
            poper: 会计期间（int，如 9）

        Returns:
            date(2026, 9, 1)；任一值缺失或非法（如 POPER=13）时返回 None
        """
        if not bdatj or not poper:
            return None
        try:
            return date(int(bdatj), int(poper), 1)
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # 每行 source 文本
    # ------------------------------------------------------------------

    @staticmethod
    def _make_source(bdatj: int, poper: int, bwkey: str = "") -> str:
        """生成价格来源标识，如 'SAP MBEWH 2026-01 [3011]'。

        从 MBEW 改为 MBEWH 是有意为之 —— 新旧两代 RFC 写出的来源必须可区分。
        """
        base = f"SAP MBEWH {bdatj}-{poper:02d}"
        return f"{base} [{bwkey}]" if bwkey else base
