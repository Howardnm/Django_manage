"""
Django 管理命令: 从 SAP 同步原材料数据到 app_raw_material。

用法:
    python manage.py sync_raw_materials                     # 全量同步
    python manage.py sync_raw_materials --dry-run           # 仅预览，不写入
    python manage.py sync_raw_materials --material A01001*  # 按物料编号过滤

定时调度 (Windows Task Scheduler):
    触发器: 每小时 / 每天
    操作:   启动程序 python.exe
    参数:   manage.py sync_raw_materials
    起始于: 项目根目录
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from app_sap_services import sap, sap_health_check
from app_sap_services.definitions.material import MaterialQuery
from app_raw_material.models import RawMaterial, RawMaterialType


DEFAULT_CATEGORY_NAME = "未分类"


class Command(BaseCommand):
    help = "从 SAP 同步原材料（MTART=ROH）到本地 RawMaterial 表"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="仅查询并预览，不写入数据库",
        )
        parser.add_argument(
            "--material",
            type=str,
            default=None,
            help="按物料编号过滤（支持通配符 *），如 A01001*",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        mat_filter = options["material"]

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "\n=== 开始 SAP 原材料同步 (MTART=ROH)..."
            )
        )
        if dry_run:
            self.stdout.write(self.style.WARNING("   [DRY-RUN] 预览模式，不会写入数据库"))

        # 1. 连接健康检查
        health = sap_health_check()
        if health.get("status") != "healthy":
            self.stdout.write(
                self.style.ERROR(
                    f"   [ERR] SAP 连接失败: {health.get('error', '未知错误')}"
                )
            )
            return

        self.stdout.write(
            f"   [OK] SAP 连接正常 (ashost={health.get('ashost')}, client={health.get('client')})"
        )

        # 2. 确保默认分类存在（RawMaterial.category 是必填字段）
        default_category, _ = RawMaterialType.objects.get_or_create(
            name=DEFAULT_CATEGORY_NAME,
            defaults={
                "code": "UNKNOWN",
                "order": 999,
                "description": "SAP 同步时自动创建的默认分类",
            },
        )

        # 3. 从 SAP 拉取原材料数据
        try:
            query = sap.rfc(MaterialQuery).filter(mta_range__eq="ROH")
            if mat_filter:
                query = query.filter(mat_range__cp=mat_filter)
            result = query.call()
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"   [ERR] SAP 查询失败: {e}")
            )
            return

        total = len(result)
        self.stdout.write(
            self.style.SUCCESS(f"   查询成功，共 {total} 条原材料记录")
        )

        if total == 0:
            self.stdout.write(self.style.WARNING("   没有符合条件的数据，同步结束"))
            return

        # 4. 逐条同步
        created_count = 0
        updated_count = 0
        error_count = 0

        for row in result:
            matnr = row.MATNR  # 已通过 clean_leading_zeros 清洗
            maktx = row.MAKTX

            if not matnr:
                self.stdout.write(
                    self.style.WARNING(f"   [WARN] 物料编号为空，跳过: {maktx}")
                )
                error_count += 1
                continue

            if dry_run:
                exists = RawMaterial.objects.filter(warehouse_code=matnr).exists()
                tag = "[~] 将更新" if exists else "[+] 将创建"
                existing_name = ""
                if exists:
                    existing = RawMaterial.objects.get(warehouse_code=matnr)
                    existing_name = f" (当前: {existing.name})"
                self.stdout.write(f"   {tag}: {maktx} ({matnr}){existing_name}")
                continue

            try:
                with transaction.atomic():
                    obj, created = RawMaterial.objects.update_or_create(
                        warehouse_code=matnr,
                        defaults={
                            "name": maktx,
                            "category": default_category,
                        },
                    )

                if created:
                    created_count += 1
                    self.stdout.write(
                        f"   [+] 新创建: {maktx} ({matnr})"
                    )
                else:
                    updated_count += 1
                    self.stdout.write(
                        f"   [~] 已更新: {maktx} ({matnr})"
                    )

            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f"   [ERR] 保存失败: {maktx} ({matnr}) — {e}")
                )

        # 5. 汇总
        self.stdout.write("")
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"[OK] 预览完成！共 {total} 条 (无数据库变更)"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"[OK] 同步完成！新建 {created_count} 个, "
                    f"更新 {updated_count} 个, "
                    f"错误 {error_count} 个"
                )
            )
