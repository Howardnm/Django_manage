import os
from django.core.management.base import BaseCommand
from django.conf import settings
from app_repository.models import MetricCategory, TestConfig

class Command(BaseCommand):
    """
    在您的项目终端中运行以下命令，即可开始批量导入或更新测试配置库：
    python manage.py import_configs
    """
    help = '从 init/ 文件夹批量导入或更新测试配置库 (指标分类、测试项)'

    def _import_metric_categories(self):
        """导入指标分类，并返回一个名称到对象的映射字典"""
        file_path = os.path.join(settings.BASE_DIR, 'init', 'metric_categories.txt')
        self.stdout.write(self.style.HTTP_INFO('\n--- 正在导入指标分类 ---'))
        
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'文件未找到: {file_path}'))
            return None

        cat_objs = {}
        created_count, updated_count, skipped_count = 0, 0, 0
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                stripped_line = line.strip()
                if not stripped_line: continue
                
                try:
                    name, order_str = stripped_line.split(';;')
                    name, order_str = name.strip(), order_str.strip()
                    order = int(order_str)

                    obj, created = MetricCategory.objects.update_or_create(
                        name=name,
                        defaults={'order': order}
                    )
                    cat_objs[name] = obj
                    
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'处理 "{stripped_line}" 时出错: {e}'))
                    skipped_count += 1
        
        self.stdout.write(f'指标分类导入完成: 新建 {created_count}, 更新 {updated_count}, 跳过 {skipped_count}。')
        return cat_objs

    def _import_test_configs(self, cat_objs):
        """导入测试配置项"""
        if not cat_objs:
            self.stdout.write(self.style.ERROR('由于指标分类导入失败，测试配置项导入已跳过。'))
            return

        file_path = os.path.join(settings.BASE_DIR, 'init', 'test_configs.txt')
        self.stdout.write(self.style.HTTP_INFO('\n--- 正在导入测试配置项 ---'))

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
                    if len(parts) != 8:
                        self.stdout.write(self.style.WARNING(f'  [!] 格式错误，跳过: {stripped_line}'))
                        skipped_count += 1
                        continue
                    
                    name, std, cond, unit, cat_name, order_str, dtype, opts = [p.strip() for p in parts]

                    category_obj = cat_objs.get(cat_name)
                    if not category_obj:
                        self.stdout.write(self.style.WARNING(f'  [!] 未找到分类 "{cat_name}"，跳过: {name}'))
                        skipped_count += 1
                        continue
                    
                    order = int(order_str)

                    # TestConfig 的唯一性由 name, standard, condition 共同决定
                    obj, created = TestConfig.objects.update_or_create(
                        name=name,
                        standard=std,
                        condition=cond,
                        category=category_obj,
                        defaults={
                            'unit': unit,
                            'order': order,
                            'data_type': dtype,
                            'options_config': opts
                        }
                    )

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'处理 "{stripped_line}" 时出错: {e}'))
                    skipped_count += 1
        
        self.stdout.write(f'测试配置项导入完成: 新建 {created_count}, 更新 {updated_count}, 跳过 {skipped_count}。')

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('🚀 开始导入测试配置库...'))
        category_objects = self._import_metric_categories()
        self._import_test_configs(category_objects)
        self.stdout.write(self.style.SUCCESS('\n✅ 所有测试配置导入完成！'))
