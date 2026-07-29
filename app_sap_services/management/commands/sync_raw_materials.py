"""
Django 管理命令: 从 SAP 同步 A01*/A03* 原材料到 app_raw_material。

用法:
    python manage.py sync_raw_materials                        # 全量同步
    python manage.py sync_raw_materials --dry-run              # 仅预览，不写入
    python manage.py sync_raw_materials --limit 100            # 限制同步条数
    python manage.py sync_raw_materials --order-by MATNR        # 按编号排序同步

定时调度 (Windows Task Scheduler):
    触发器: 每小时 / 每天
    操作:   启动程序 python.exe
    参数:   manage.py sync_raw_materials
    起始于: 项目根目录
"""

import polars as pl

from django.core.management.base import BaseCommand
from django.db import transaction

from app_sap_services import sap, sap_health_check
from app_sap_services.definitions.material import MaterialQuery
from app_raw_material.models import RawMaterial, RawMaterialType


DEFAULT_CATEGORY_NAME = "未分类"
CHUNK_SIZE = 500

# 同步的物料编号匹配模式（SAP 端 A0* 宽拉 + Polars 端按此列表精筛）
SYNC_PATTERNS = ("A01*", "A03*")


class Command(BaseCommand):
    help = "从 SAP 同步 A01*/A03* 原材料到本地 RawMaterial 表"

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
            "--order-by", type=str, default="MATNR",
            help="排序字段，多个用逗号分隔，-前缀降序（默认: MATNR）",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]
        order_by = options["order_by"]

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\n=== 开始 SAP 原材料同步 "
                f"({', '.join(SYNC_PATTERNS)})... ==="
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

        # ── 2. 默认分类 ──
        default_category, _ = RawMaterialType.objects.get_or_create(
            name=DEFAULT_CATEGORY_NAME,
            defaults={
                "code": "UNKNOWN", "order": 999,
                "description": "SAP 同步时自动创建的默认分类",
            },
        )

        # ── 3. SAP 宽拉 + Polars 精筛 ──
        try:
            query = sap.rfc(MaterialQuery).filter(mat_range__cp="A0*")
            if order_by:
                query = query.order_by(
                    *[f.strip() for f in order_by.split(",")]
                )
            if limit and limit > 0:
                query = query.limit(limit)

            df = query.collect()
            before = df.height
            df = df.filter(
                pl.any_horizontal(
                    pl.col("MATNR").str.starts_with(p.rstrip("*"))
                    for p in SYNC_PATTERNS
                )
            )
            after = df.height
            self.stdout.write(
                f"   SAP 宽拉 A0*: {before} 条 "
                f"→ Polars 精筛 ({', '.join(SYNC_PATTERNS)}): "
                f"{after} 条"
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"   [ERR] SAP 查询失败: {e}")
            )
            return

        if df.is_empty():
            self.stdout.write(self.style.WARNING("   没有符合条件的数据，同步结束"))
            return

        # ── 4. 同步 ──
        if dry_run:
            self._dry_run(df)
        else:
            self._live_sync(df, default_category)

    # ------------------------------------------------------------------
    # dry-run
    # ------------------------------------------------------------------

    def _dry_run(self, df: pl.DataFrame):
        will_create = 0
        will_update = 0

        for row in df.iter_rows(named=True):
            matnr = row["MATNR"]
            maktx = row.get("MAKTX", "")
            if not matnr:
                continue

            if RawMaterial.objects.filter(warehouse_code=matnr).exists():
                will_update += 1
                existing = RawMaterial.objects.only("name").get(
                    warehouse_code=matnr
                )
                self.stdout.write(
                    f"   [~] 将更新: {maktx} ({matnr}) "
                    f"(当前: {existing.name})"
                )
            else:
                will_create += 1
                self.stdout.write(
                    f"   [+] 将创建: {maktx} ({matnr})"
                )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"[OK] 预览完成！共 {will_create + will_update} 条 "
                f"(将创建 {will_create}, 将更新 {will_update})"
            )
        )

    # ------------------------------------------------------------------
    # live sync（Polars iter_slices 分批）
    # ------------------------------------------------------------------

    def _live_sync(self, df: pl.DataFrame, default_category):
        total = df.height
        created = 0
        updated = 0
        errors = 0
        processed = 0

        for chunk_df in df.iter_slices(CHUNK_SIZE):
            for row in chunk_df.iter_rows(named=True):
                matnr = row["MATNR"]
                maktx = row.get("MAKTX", "")

                if not matnr:
                    self.stdout.write(
                        self.style.WARNING(
                            f"   [WARN] 物料编号为空，跳过: {maktx}"
                        )
                    )
                    errors += 1
                    continue

                try:
                    with transaction.atomic():
                        obj, is_new = RawMaterial.objects.update_or_create(
                            warehouse_code=matnr,
                            defaults={
                                "name": maktx,
                                "category": default_category,
                            },
                        )
                    if is_new:
                        created += 1
                    else:
                        updated += 1
                except Exception as e:
                    errors += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f"   [ERR] 保存失败: {maktx} ({matnr}) — {e}"
                        )
                    )

            processed += chunk_df.height
            self.stdout.write(
                f"   进度: {processed}/{total} "
                f"(新建 {created}, 更新 {updated})"
            )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"[OK] 同步完成！总计 {processed} 条, "
                f"新建 {created} 个, 更新 {updated} 个, 错误 {errors} 个"
            )
        )

