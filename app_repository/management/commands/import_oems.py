import os
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction
from app_repository.models import OEM

class Command(BaseCommand):
    """
    运行命令：python manage.py import_oems
    功能：从 init/oem_data.txt 批量导入或更新主机厂公司档案。
    """
    help = '从 init/oem_data.txt 批量同步主机厂公司档案'

    def handle(self, *args, **options):
        # 1. 路径确认
        file_path = os.path.join(settings.BASE_DIR, 'init', 'oem_data.txt')
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'❌ 找不到数据文件: {file_path}'))
            return

        self.stdout.write(self.style.MIGRATE_HEADING(f'🚀 开始导入 OEM 公司档案: {file_path}'))

        created_count = 0
        updated_count = 0
        error_count = 0

        # 2. 读取文件
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]

        # 3. 循环处理
        for line in lines:
            try:
                # 解析格式: 全称;;简称;;描述
                parts = line.split(';;')
                if len(parts) < 2:
                    continue

                name = parts[0].strip()
                short_name = parts[1].strip()
                description = parts[2].strip() if len(parts) > 2 else ""

                # 4. 执行更新或创建 (仅处理公司级字段)
                with transaction.atomic():
                    obj, created = OEM.objects.update_or_create(
                        name=name,
                        defaults={
                            'short_name': short_name,
                            'description': description
                        }
                    )

                if created:
                    created_count += 1
                    self.stdout.write(self.style.SUCCESS(f'  [+] [新增公司] {obj.name}'))
                else:
                    updated_count += 1
                    self.stdout.write(f'  [*] [更新档案] {obj.name}')

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  [!] 处理失败 "{line[:20]}...": {str(e)}'))
                error_count += 1

        # 5. 结果反馈
        self.stdout.write(self.style.MIGRATE_HEADING('\n--- 导入完成 ---'))
        self.stdout.write(f'✅ 成功: {created_count + updated_count}')
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'❌ 失败: {error_count}'))
        
        self.stdout.write(self.style.WARNING(
            '\n注意：本脚本仅同步“公司档案”。\n具体对接人账号请在“用户管理”模块创建，并关联至上述公司。'
        ))
