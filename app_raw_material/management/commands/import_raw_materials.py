import os
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import transaction
from app_raw_material.models import RawMaterial, Supplier, RawMaterialType

try:
    import openpyxl
except ImportError:
    raise CommandError("该命令需要 'openpyxl' 库。请运行 'pip install openpyxl' 进行安装。")

class Command(BaseCommand):
    """
    从 init/原材料数据.xlsx 文件批量导入或更新原材料信息
    python manage.py import_raw_materials
    """
    help = '从 init/原材料数据.xlsx 文件批量导入或更新原材料信息'

    def handle(self, *args, **kwargs):
        file_path = os.path.join(settings.BASE_DIR, 'init', '原材料数据.xlsx')

        if not os.path.exists(file_path):
            raise CommandError(f'文件未找到: {file_path}')

        self.stdout.write(f'开始从 {file_path} 导入原材料数据...')

        try:
            workbook = openpyxl.load_workbook(file_path)
            sheet = workbook.active
        except Exception as e:
            raise CommandError(f"打开或读取 Excel 文件时出错: {e}")

        created_count = 0
        updated_count = 0
        skipped_count = 0
        
        # 使用事务确保数据一致性，如果中途出错则回滚
        with transaction.atomic():
            # 迭代行，从第二行开始（跳过表头）
            for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                # 检查行是否为空
                if not any(row):
                    continue

                try:
                    purchase_date, supplier_name, warehouse_code, name, model_name_raw, category_name, _, cost_price = row
                    
                    # --- 数据清洗和验证 ---
                    supplier_name = str(supplier_name).strip() if supplier_name else None
                    warehouse_code = str(warehouse_code).strip() if warehouse_code else None
                    name = str(name).strip() if name else None
                    # 关键修复：将空的型号处理为空字符串 '' 而不是 None
                    model_name = str(model_name_raw).strip() if model_name_raw is not None else ''
                    category_name = str(category_name).strip() if category_name else None

                    if not name or not category_name or not supplier_name:
                        self.stdout.write(self.style.WARNING(f'  [!] 第 {row_idx} 行缺少核心数据 (原材料名称/类型/供应商)，已跳过。'))
                        skipped_count += 1
                        continue

                    # --- 查找关联对象 ---
                    try:
                        supplier = Supplier.objects.get(name=supplier_name)
                    except Supplier.DoesNotExist:
                        self.stdout.write(self.style.WARNING(f'  [!] 第 {row_idx} 行：供应商 "{supplier_name}" 不存在，已跳过。'))
                        skipped_count += 1
                        continue

                    try:
                        category = RawMaterialType.objects.get(name=category_name)
                    except RawMaterialType.DoesNotExist:
                        self.stdout.write(self.style.WARNING(f'  [!] 第 {row_idx} 行：材料类型 "{category_name}" 不存在，已跳过。'))
                        skipped_count += 1
                        continue

                    # --- 准备待更新/创建的数据 ---
                    defaults = {
                        'name': name,
                        'model_name': model_name,
                        'category': category,
                        'supplier': supplier,
                        'cost_price': cost_price if cost_price is not None else 0,
                        'purchase_date': purchase_date,
                    }

                    # --- 执行更新或创建 ---
                    if warehouse_code:
                        # 优先使用物料长代码作为唯一标识
                        obj, created = RawMaterial.objects.update_or_create(
                            warehouse_code=warehouse_code,
                            defaults=defaults
                        )
                    else:
                        # 如果没有物料长代码，则使用名称+型号作为联合唯一标识
                        obj, created = RawMaterial.objects.update_or_create(
                            name=name,
                            model_name=model_name,
                            defaults=defaults
                        )

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
                        
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'  [!] 处理第 {row_idx} 行时出错: {e}'))
                    skipped_count += 1
                    # 在事务中，如果一行出错，可以选择继续或中止
                    # 这里我们选择继续处理下一行，并在最后报告错误

        self.stdout.write(self.style.SUCCESS('\n导入完成！'))
        self.stdout.write(f'总计: 新建 {created_count} 个, 更新 {updated_count} 个, 跳过 {skipped_count} 个。')
