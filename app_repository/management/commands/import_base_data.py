import os
from django.core.management.base import BaseCommand
from django.conf import settings
from app_repository.models import MaterialType, ApplicationScenario

class Command(BaseCommand):
    """
    在您的项目终端中运行以下命令，即可开始批量导入或更新 材料类型和应用场景数据
    python manage.py import_base_data
    """
    help = '从 init/ 文件夹批量导入或更新基础数据 (材料类型、应用场景)'

    def _import_material_types(self):
        """导入材料类型"""
        file_path = os.path.join(settings.BASE_DIR, 'init', 'material_types.txt')
        self.stdout.write(self.style.HTTP_INFO('\n--- 正在导入材料类型 ---'))
        
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'文件未找到: {file_path}'))
            return

        created_count, updated_count, skipped_count = 0, 0, 0
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                stripped_line = line.strip()
                if not stripped_line: continue
                
                try:
                    parts = stripped_line.split(';;')
                    if len(parts) != 3:
                        self.stdout.write(self.style.WARNING(f'  [!] 格式错误，跳过: {stripped_line}'))
                        skipped_count += 1
                        continue
                    
                    name, description, classification = [part.strip() for part in parts]
                    
                    obj, created = MaterialType.objects.update_or_create(
                        name=name,
                        defaults={'description': description, 'classification': classification}
                    )
                    
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'处理 "{stripped_line}" 时出错: {e}'))
                    skipped_count += 1
        
        self.stdout.write(f'材料类型导入完成: 新建 {created_count}, 更新 {updated_count}, 跳过 {skipped_count}。')

    def _import_application_scenarios(self):
        """导入应用场景"""
        file_path = os.path.join(settings.BASE_DIR, 'init', 'application_scenarios.txt')
        self.stdout.write(self.style.HTTP_INFO('\n--- 正在导入应用场景 ---'))

        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'文件未找到: {file_path}'))
            return

        created_count, updated_count, skipped_count = 0, 0, 0
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                stripped_line = line.strip()
                if not stripped_line: continue

                try:
                    parts = stripped_line.split(';;')
                    if len(parts) != 2:
                        self.stdout.write(self.style.WARNING(f'  [!] 格式错误，跳过: {stripped_line}'))
                        skipped_count += 1
                        continue
                    
                    name, requirements = [part.strip() for part in parts]

                    obj, created = ApplicationScenario.objects.update_or_create(
                        name=name,
                        defaults={'requirements': requirements}
                    )

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'处理 "{stripped_line}" 时出错: {e}'))
                    skipped_count += 1
        
        self.stdout.write(f'应用场景导入完成: 新建 {created_count}, 更新 {updated_count}, 跳过 {skipped_count}。')

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('🚀 开始导入基础数据...'))
        self._import_material_types()
        self._import_application_scenarios()
        self.stdout.write(self.style.SUCCESS('\n✅ 所有基础数据导入完成！'))
