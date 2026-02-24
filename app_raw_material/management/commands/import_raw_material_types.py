import os
from django.core.management.base import BaseCommand
from django.conf import settings
from app_raw_material.models import RawMaterialType

class Command(BaseCommand):
    """
    从 init/raw_material_types.txt 文件批量导入或更新原材料类型
    python manage.py import_raw_material_types

    """
    help = '从 init/raw_material_types.txt 文件批量导入或更新原材料类型'

    def handle(self, *args, **kwargs):
        # 构建文件路径
        file_path = os.path.join(settings.BASE_DIR, 'init', 'raw_material_types.txt')

        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'文件未找到: {file_path}'))
            return

        self.stdout.write(f'开始从 {file_path} 导入原材料类型数据...')

        created_count = 0
        updated_count = 0
        skipped_count = 0

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                stripped_line = line.strip()
                if not stripped_line:
                    continue

                try:
                    parts = stripped_line.split(';;')
                    if len(parts) != 4:
                        self.stdout.write(self.style.WARNING(f'  [!] 格式错误，跳过行: {stripped_line}'))
                        skipped_count += 1
                        continue

                    name, code, order_str, description = [part.strip() for part in parts]
                    
                    if not name:
                        self.stdout.write(self.style.WARNING(f'  [!] 名称为空，跳过行: {stripped_line}'))
                        skipped_count += 1
                        continue
                    
                    # 将排序权重转换为整数
                    try:
                        order = int(order_str)
                    except ValueError:
                        self.stdout.write(self.style.WARNING(f'  [!] 排序权重格式错误，跳过行: {stripped_line}'))
                        skipped_count += 1
                        continue

                    # 使用 update_or_create，它会根据 name 查找
                    # 如果找到，则更新其他字段；如果没找到，则创建新记录
                    obj, created = RawMaterialType.objects.update_or_create(
                        name=name,
                        defaults={
                            'code': code,
                            'order': order,
                            'description': description,
                        }
                    )

                    if created:
                        self.stdout.write(self.style.SUCCESS(f'  [+] 新建: {obj.name}'))
                        created_count += 1
                    else:
                        self.stdout.write(f'  [*] 更新: {obj.name}')
                        updated_count += 1

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'处理 "{stripped_line}" 时出错: {e}'))
                    skipped_count += 1
        
        self.stdout.write(self.style.SUCCESS('\n导入完成！'))
        self.stdout.write(f'总计: 新建 {created_count} 个, 更新 {updated_count} 个, 跳过 {skipped_count} 个。')
