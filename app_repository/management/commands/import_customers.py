import os
from datetime import date, datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app_repository.models import Customer


# 表头（去空格后）→ 模型字段。两列都叫「行业」时，只取第二次出现的文本列。
HEADER_TO_FIELD = {
    "客户编码": "customer_code",
    "客户名称1": "company_name",
    "客户名称2": "company_name_2",
    "客户账户组": "account_group",
    "账户组描述": "account_group_name",
    "搜索词 1": "short_name",
    "搜索词 2": "search_term_2",
    "国家": "country_code",
    "国家名称": "country_name",
    "地区": "region_code",
    "地区名称": "region_name",
    "城市": "city",
    "街道/门牌号": "street",
    "门牌号": "house_number",
    "贸易伙伴": "trade_partner",
    "邮政编码": "postal_code",
    "电话号1": "phone",
    "电话号2": "phone_2",
    "电子邮件地址": "email",
    "客户来源": "customer_source",
    "供应商编码": "vendor_code",
    "全部记账冻结": "posting_blocked",
    "销售订单冻结": "sales_order_block",
    "DlvBl": "delivery_block",
    "出具发票冻结": "billing_block",
    "全部销售区域冻结": "sales_area_blocked",
    "集团级删除": "group_deleted",
    "集团级创建者": "sap_created_by",
    "集团级创建日期": "sap_created_on",
    "客户系": "customer_series",
    "区域": "sales_region",
    "销售主管": "sales_manager_name",
    "销售人员": "sales_person_name",
    "内部地址号": "address_number",
}

BOOL_FIELDS = {"posting_blocked", "sales_area_blocked", "group_deleted"}
DATE_FIELDS = {"sap_created_on"}
ADDRESS_PARTS = ("city", "street", "house_number")


def _text(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def _as_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt, size in (("%Y-%m-%d", 10), ("%Y/%m/%d", 10), ("%Y%m%d", 8)):
        try:
            return datetime.strptime(text[:size], fmt).date()
        except ValueError:
            continue
    raise ValueError(f"无法解析日期: {value!r}")


def _clip(field_name, text):
    max_length = Customer._meta.get_field(field_name).max_length
    if max_length and len(text) > max_length:
        return text[:max_length], True
    return text, False


def _header_index(headers):
    index = {}
    industry_seen = 0
    for i, raw in enumerate(headers):
        name = _text(raw)
        if name == "行业":
            industry_seen += 1
            if industry_seen == 2:
                index["industry"] = i
            continue
        field = HEADER_TO_FIELD.get(name)
        if field and field not in index:
            index[field] = i
    return index


class Command(BaseCommand):
    """
    运行命令：python manage.py import_customers
    功能：从 init/客户主数据.XLSX 按客户编码新增或更新客户档案。
    """
    help = "从 init/客户主数据.XLSX 按客户编码批量导入或更新客户主数据"

    def add_arguments(self, parser):
        parser.add_argument("--file", dest="file_path", default="", help="Excel 路径，默认 init/客户主数据.XLSX")
        parser.add_argument("--dry-run", action="store_true", help="只统计，不写数据库")

    def handle(self, *args, **options):
        file_path = options["file_path"] or os.path.join(settings.BASE_DIR, "init", "客户主数据.XLSX")
        if not os.path.exists(file_path):
            raise CommandError(f"找不到数据文件: {file_path}")

        try:
            import openpyxl
        except ImportError as exc:
            raise CommandError("缺少 openpyxl，无法读取 xlsx") from exc

        workbook = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        worksheet = workbook.active
        rows = worksheet.iter_rows(values_only=True)
        try:
            header_row = next(rows)
        except StopIteration:
            raise CommandError("Excel 为空")
        columns = _header_index(header_row)
        missing = [name for name, field in HEADER_TO_FIELD.items() if field not in columns]
        if "industry" not in columns:
            missing.append("行业（第二列）")
        if missing:
            raise CommandError("表头缺少列: " + "、".join(missing))

        dry_run = options["dry_run"]
        self.stdout.write(self.style.MIGRATE_HEADING(f"开始导入客户主数据: {file_path}"))
        if dry_run:
            self.stdout.write(self.style.WARNING("dry-run：不会写数据库"))

        created_count = updated_count = linked_count = skipped_count = failed_count = 0
        consumed_ids = set()

        for offset, row in enumerate(rows, start=2):
            try:
                values, clipped = self._row_values(row, columns)
            except ValueError as exc:
                failed_count += 1
                self.stdout.write(self.style.ERROR(f"  [!] 第 {offset} 行: {exc}"))
                continue

            code = values.get("customer_code", "")
            if not code:
                skipped_count += 1
                continue
            if clipped:
                self.stdout.write(self.style.WARNING(f"  [!] 第 {offset} 行字段超长已截断: {', '.join(clipped)}"))

            try:
                action = self._save_row(code, values, dry_run, consumed_ids)
            except Exception as exc:
                failed_count += 1
                self.stdout.write(self.style.ERROR(f"  [!] 第 {offset} 行 {code}: {exc}"))
                continue

            if action == "create":
                created_count += 1
            elif action == "link":
                linked_count += 1
                updated_count += 1
            else:
                updated_count += 1

        workbook.close()
        self.stdout.write(self.style.MIGRATE_HEADING("\n--- 导入完成 ---"))
        self.stdout.write(f"新建: {created_count}")
        self.stdout.write(f"更新: {updated_count}（其中挂接已有客户 {linked_count}）")
        self.stdout.write(f"跳过: {skipped_count}")
        if failed_count:
            self.stdout.write(self.style.ERROR(f"失败: {failed_count}"))

    def _row_values(self, row, columns):
        values = {}
        clipped = []
        for field, idx in columns.items():
            raw = row[idx] if idx < len(row) else None
            if field in BOOL_FIELDS:
                values[field] = _text(raw).upper() == "X"
            elif field in DATE_FIELDS:
                values[field] = _as_date(raw)
            else:
                text, was_clipped = _clip(field, _text(raw))
                values[field] = text
                if was_clipped:
                    clipped.append(field)
        return values, clipped

    def _save_row(self, code, values, dry_run, consumed_ids):
        obj = Customer.objects.filter(customer_code=code).first()
        action = "update"
        if obj is None:
            name = values.get("company_name", "")
            matches = list(
                Customer.objects.filter(company_name=name, customer_code__isnull=True).exclude(pk__in=consumed_ids)
            ) if name else []
            if len(matches) > 1:
                raise ValueError(f"全称「{name}」对应多条未编码客户，无法挂接")
            if len(matches) == 1:
                obj = matches[0]
                action = "link"
            else:
                obj = Customer(customer_code=code)
                action = "create"

        for field, value in values.items():
            setattr(obj, field, value)
        if not (obj.address or "").strip():
            composed = " ".join(getattr(obj, part) for part in ADDRESS_PARTS if getattr(obj, part))
            obj.address = composed[:200]

        if action == "link":
            consumed_ids.add(obj.pk)
        if not dry_run:
            try:
                with transaction.atomic():
                    obj.save()
            except Exception:
                if action == "link":
                    consumed_ids.discard(obj.pk)
                raise
        return action
