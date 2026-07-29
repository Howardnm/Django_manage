"""
Django 管理命令: 测试 SAP 连接和 RFC 调用。

用法:
    python manage.py sap_test                              # 健康检查 + 展示前 10 条
    python manage.py sap_test --check-only                 # 仅健康检查
    python manage.py sap_test --count-only                 # 仅查总数
    python manage.py sap_test --material A01001*           # 按物料编号过滤
    python manage.py sap_test --material "A01*" --limit 3  # 限制行数
    python manage.py sap_test --group-by MTART             # 按类型分组汇总
    python manage.py sap_test --group-by MTART,WERKS       # 多字段分组
    python manage.py sap_test --order-by MATNR             # 排序
"""

from django.core.management.base import BaseCommand

from app_sap_services import sap, sap_health_check
from app_sap_services.definitions.material import MaterialQuery


class Command(BaseCommand):
    help = "SAP 连接测试和 RFC 调用调试工具"

    def add_arguments(self, parser):
        parser.add_argument(
            "--check-only", action="store_true",
            help="仅执行连接健康检查",
        )
        parser.add_argument(
            "--count-only", action="store_true",
            help="仅查询并显示记录总数",
        )
        parser.add_argument(
            "--material", type=str, default=None,
            help="物料编号过滤（支持通配符 *），如 A01001*",
        )
        parser.add_argument(
            "--limit", type=int, default=10,
            help="返回行数限制（默认 10，0 = 不限制）",
        )
        parser.add_argument(
            "--group-by", type=str, default=None,
            help="按字段分组汇总，多个字段用逗号分隔，如 MTART,WERKS",
        )
        parser.add_argument(
            "--order-by", type=str, default=None,
            help="排序字段，多个用逗号分隔，-前缀降序，如 MATNR,-MAKTX",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("=== SAP 服务测试 ==="))

        # ── 1. 健康检查 ──
        self.stdout.write("\n>>> 1. SAP 连接健康检查...")
        health = sap_health_check()
        if health.get("status") != "healthy":
            self.stdout.write(
                self.style.ERROR(
                    f"    连接失败: {health.get('error', '未知错误')}"
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"    连接正常: ashost={health.get('ashost')}, "
                f"client={health.get('client')}"
            )
        )
        if options["check_only"]:
            return

        # ── 2. 构建查询 ──
        mat_pattern = options["material"]
        limit = options["limit"]
        group_by = options["group_by"]
        order_by = options["order_by"]

        query = sap.rfc(MaterialQuery)
        if mat_pattern:
            query = query.filter(mat_range__cp=mat_pattern)
        if order_by:
            query = query.order_by(*[f.strip() for f in order_by.split(",")])
        if limit and limit > 0:
            query = query.limit(limit)

        summary = [f"RFC: ZRFC_MATERIAL_MESN"]
        if mat_pattern:
            summary.append(f"mat_range__cp={mat_pattern}")
        if limit:
            summary.append(f"limit={limit}")
        if order_by:
            summary.append(f"order_by={order_by}")

        self.stdout.write(f"\n>>> 2. 物料查询测试 ({', '.join(summary)})...")

        try:
            # ── count-only 模式（忽略 limit）──
            if options["count_only"]:
                total = query.clone().limit(None).count()
                self.stdout.write(
                    self.style.SUCCESS(f"    记录总数: {total}")
                )
                return

            # ── group-by 模式 ──
            if group_by:
                fields = [f.strip() for f in group_by.split(",")]
                result = query.group_by(*fields).agg(count="count").call()
                self.stdout.write(
                    self.style.SUCCESS(f"    分组汇总（{len(result)} 组）：")
                )
                for row in result:
                    key = ", ".join(f"{f}={row[f]}" for f in fields)
                    self.stdout.write(f"      {key}  |  count={row['count']}")
                return

            # ── 普通查询模式 ──
            total = query.count()
            self.stdout.write(
                self.style.SUCCESS(f"    查询成功，共 {total} 条记录")
            )

            if total == 0:
                self.stdout.write(self.style.WARNING("    未查询到符合条件的数据"))
                return

            # 使用 show() 表格输出
            query.show(limit if limit and limit > 0 else 10,
                       "MATNR", "MAKTX", "MTART", "WERKS", "MATKL")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"    查询失败: {e}"))

        self.stdout.write(self.style.SUCCESS("\n=== 测试完成 ==="))
