"""
Django 管理命令: 测试 SAP 连接和 RFC 调用。

用法:
    python manage.py sap_test                              # 健康检查 + 物料查询
    python manage.py sap_test --check-only                 # 仅健康检查
    python manage.py sap_test --material A01001*           # 查询指定物料
"""

from django.core.management.base import BaseCommand
from app_sap_services import sap_health_check


class Command(BaseCommand):
    help = "SAP 连接测试和 RFC 调用调试工具"

    def add_arguments(self, parser):
        parser.add_argument(
            "--check-only",
            action="store_true",
            help="仅执行连接健康检查",
        )
        parser.add_argument(
            "--material",
            type=str,
            default=None,
            help="测试物料查询，传入物料编号（支持通配符 *），如 A01001*",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("=== SAP 服务测试 ==="))

        # 1. 健康检查
        self.stdout.write("\n>>> 1. SAP 连接健康检查...")
        health = sap_health_check()
        if health.get("status") == "healthy":
            self.stdout.write(
                self.style.SUCCESS(
                    f"    连接正常: ashost={health.get('ashost')}, "
                    f"client={health.get('client')}"
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    f"    连接失败: {health.get('error', health.get('message', '未知错误'))}"
                )
            )
            return

        if options["check_only"]:
            return

        # 2. 物料查询测试（使用新 API）
        mat_pattern = options["material"] or "A01001*"
        self.stdout.write(
            f"\n>>> 2. 物料查询测试 "
            f"(RFC: ZRFC_MATERIAL_MESN, mat_range__cp={mat_pattern})..."
        )

        from app_sap_services import sap
        from app_sap_services.definitions.material import MaterialQuery

        try:
            result = sap.rfc(MaterialQuery) \
                .filter(mat_range__cp=mat_pattern) \
                .limit(5) \
                .call()

            self.stdout.write(
                self.style.SUCCESS(f"    查询成功，返回 {len(result)} 条记录")
            )

            if result:
                self.stdout.write(
                    f'    {"物料编号":<20} | {"物料描述":<20} | '
                    f'{"类型":<6} | {"物料组":<8} | {"工厂"}'
                )
                self.stdout.write("    " + "-" * 75)
                for m in result:
                    self.stdout.write(
                        f"    {m.MATNR:<20} | "
                        f"{m.MAKTX[:18]:<20} | "
                        f"{m.MTART:<6} | "
                        f"{m.MATKL:<8} | "
                        f"{m.WERKS}"
                    )
            else:
                self.stdout.write(self.style.WARNING("    未查询到符合条件的数据"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"    查询失败: {e}"))

        self.stdout.write(self.style.SUCCESS("\n=== 测试完成 ==="))
