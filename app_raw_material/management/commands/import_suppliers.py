import os
from django.core.management.base import BaseCommand
from django.conf import settings
from app_raw_material.models import Supplier

class Command(BaseCommand):
    """
    # 只需要在您的项目终端中运行以下命令，即可开始批量导入：
    python manage.py import_suppliers

    """
    help = '从 init/原材料供应商.txt 文件批量导入供应商信息'

    def handle(self, *args, **kwargs):
        # 构建文件路径
        file_path = os.path.join(settings.BASE_DIR, 'init', '原材料供应商.txt')

        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'文件未找到: {file_path}'))
            return

        self.stdout.write(f'开始从 {file_path} 导入供应商...')

        # 使用集合来处理文件中的重复行
        unique_lines = set()
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                stripped_line = line.strip()
                if stripped_line:
                    unique_lines.add(stripped_line)

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for line in unique_lines:
            supplier_name = line
            description = ''
            is_inactive = False

            # 检查是否包含停用标记
            if '（停用）' in supplier_name:
                supplier_name = supplier_name.replace('（停用）', '').strip()
                is_inactive = True

            if not supplier_name:
                skipped_count += 1
                continue

            # 使用 get_or_create 来避免重复创建
            # defaults 用于在创建新对象时设置的字段
            defaults = {}
            if is_inactive:
                defaults['description'] = '（停用）'

            try:
                supplier, created = Supplier.objects.get_or_create(
                    name=supplier_name,
                    defaults=defaults
                )

                if created:
                    self.stdout.write(self.style.SUCCESS(f'  [+] 新建: {supplier.name}'))
                    if is_inactive:
                        self.stdout.write(self.style.WARNING(f'      -> 标记为停用'))
                    created_count += 1
                else:
                    # 如果已存在，但文件中标记为停用，我们可能需要更新它
                    if is_inactive and '（停用）' not in (supplier.description or ''):
                        supplier.description = (supplier.description or '') + ' （停用）'
                        supplier.save()
                        self.stdout.write(self.style.NOTICE(f'  [*] 更新: {supplier.name} -> 标记为停用'))
                        updated_count += 1
                    else:
                        # self.stdout.write(f'  [=] 已存在: {supplier.name}')
                        skipped_count += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'处理 "{line}" 时出错: {e}'))
                skipped_count += 1
        
        self.stdout.write(self.style.SUCCESS('\n导入完成！'))
        self.stdout.write(f'总计: 新建 {created_count} 个, 更新 {updated_count} 个, 跳过 {skipped_count} 个。')
