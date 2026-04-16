import os
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction
from django.contrib.auth import get_user_model
from app_repository.models import OEM

User = get_user_model()

class Command(BaseCommand):
    """
    运行命令：
    python manage.py import_oems
    
    功能：从 init/oem_data.txt 批量同步主机厂信息，并自动生成/更新会员账号。
    格式要求: 名称;;简称;;描述;;联系人;;联系电话;;电子邮箱;;公司地址
    """
    help = '从 init/oem_data.txt 批量同步主机厂信息，并自动生成/更新会员账号'

    def handle(self, *args, **options):
        # 1. 路径检查
        file_path = os.path.join(settings.BASE_DIR, 'init', 'oem_data.txt')
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'❌ 找不到数据文件: {file_path}'))
            return

        self.stdout.write(self.style.MIGRATE_HEADING(f'🚀 开始从 {file_path} 导入并同步 OEM 数据...'))

        created_count = 0
        updated_count = 0
        error_count = 0

        # 2. 读取并处理文件
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]

        for line in lines:
            try:
                # 预期的格式: 名称;;简称;;描述;;联系人;;联系电话;;电子邮箱;;公司地址
                parts = line.split(';;')
                if len(parts) < 2:
                    self.stdout.write(self.style.WARNING(f'  [!] 格式不完整 (至少需要名称和简称)，跳过: {line}'))
                    continue

                name = parts[0].strip()
                short_name = parts[1].strip()
                description = parts[2].strip() if len(parts) > 2 else ""
                contact_name = parts[3].strip() if len(parts) > 3 else ""
                contact_phone = parts[4].strip() if len(parts) > 4 else ""
                contact_email = parts[5].strip() if len(parts) > 5 else ""
                address = parts[6].strip() if len(parts) > 6 else ""

                # 3. 使用事务确保数据一致性
                # update_or_create 会触发 signals.py 中的 auto_create_oem_user 和 Webhook 同步
                with transaction.atomic():
                    obj, created = OEM.objects.update_or_create(
                        name=name,
                        defaults={
                            'short_name': short_name,
                            'description': description,
                            'contact_name': contact_name,
                            'contact_phone': contact_phone,
                            'contact_email': contact_email,
                            'address': address,
                            'is_active': True
                        }
                    )

                if created:
                    status_msg = self.style.SUCCESS(f'  [+] [新建并同步] {obj.name}')
                    created_count += 1
                else:
                    status_msg = f'  [*] [更新并同步] {obj.name}'
                    updated_count += 1

                # 检查关联账号状态
                account_status = " (账号已就绪)" if obj.user else " (等待信号生成账号)"
                self.stdout.write(f"{status_msg}{account_status}")

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  [!] 处理 "{line}" 时出错: {str(e)}'))
                error_count += 1

        # 4. 结果统计
        self.stdout.write(self.style.MIGRATE_HEADING('\n--- 导入任务总结 ---'))
        self.stdout.write(f'✅ 成功处理: {created_count + updated_count} 个')
        self.stdout.write(f'   - 新增: {created_count}')
        self.stdout.write(f'   - 更新: {updated_count}')
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'❌ 失败: {error_count} 个'))

        self.stdout.write(self.style.WARNING(
            '\n提示: 导入完成后，OEM 账号已通过 signals.py 自动创建。'
            '\n账号名格式: oem_{id}, 初始密码格式: Oem@{id}'))
