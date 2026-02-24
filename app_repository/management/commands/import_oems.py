import os
from django.core.management.base import BaseCommand
from django.conf import settings
from app_repository.models import OEM

class Command(BaseCommand):
    """
    # 只需要在您的项目终端中运行以下命令，即可开始批量导入：
    python manage.py import_oems

    """
    help = '从 init/oem_data.txt 文件批量导入或更新主机厂 (OEM) 信息'

    def handle(self, *args, **kwargs):
        # 构建文件路径
        file_path = os.path.join(settings.BASE_DIR, 'init', 'oem_data.txt')

        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'文件未找到: {file_path}'))
            return

        self.stdout.write(f'开始从 {file_path} 导入主机厂 (OEM) 数据...')

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
                    if len(parts) != 3:
                        self.stdout.write(self.style.WARNING(f'  [!] 格式错误，跳过行: {stripped_line}'))
                        skipped_count += 1
                        continue

                    name, short_name, description = [part.strip() for part in parts]

                    if not name:
                        self.stdout.write(self.style.WARNING(f'  [!] 名称为空，跳过行: {stripped_line}'))
                        skipped_count += 1
                        continue

                    # 使用 update_or_create，它会根据 name 查找
                    # 如果找到，则更新其他字段；如果没找到，则创建新记录
                    obj, created = OEM.objects.update_or_create(
                        name=name,
                        defaults={
                            'short_name': short_name,
                            'description': description,
                        }
                    )

                    if created:
                        self.stdout.write(self.style.SUCCESS(f'  [+] 新建: {obj.short_name or obj.name}'))
                        created_count += 1
                    else:
                        self.stdout.write(f'  [*] 更新: {obj.short_name or obj.name}')
                        updated_count += 1

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'处理 "{stripped_line}" 时出错: {e}'))
                    skipped_count += 1
        
        self.stdout.write(self.style.SUCCESS('\n导入完成！'))
        self.stdout.write(f'总计: 新建 {created_count} 个, 更新 {updated_count} 个, 跳过 {skipped_count} 个。')
