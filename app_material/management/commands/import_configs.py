import os
from django.core.management.base import BaseCommand
from django.conf import settings
from app_material.models import MetricCategory, TestConfig


class Command(BaseCommand):
    """
    从 init/ 文件夹批量导入或更新测试配置库 (指标分类、测试项)。

    使用说明：
      1. 常规导入/更新（txt -> 数据库）：
             python manage.py import_configs
         txt 中的配置项以第一列主键 id 识别新增/更新；
         无 id 的新增条目导入后自动回写 id 到源文件。

      2. 补充回写（数据库 -> txt）：
             python manage.py import_configs --writeback
         正常导入完成后，将数据库中存在但 txt 未收录的配置项
         （如后台手动新增的指标）追加回写到 txt 文件末尾，
         保证后续以稳定 id 识别管理。
    """
    help = '从 init/ 文件夹批量导入或更新测试配置库 (指标分类、测试项)：python manage.py import_configs [--writeback]'

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
        """导入测试配置项（以主键 id 识别新增/更新，新增条目自动回写 id 到源文件）"""
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
            lines = f.read().splitlines()

        out_lines = []
        for line in lines:
            stripped_line = line.strip()
            if not stripped_line:
                out_lines.append('')
                continue

            try:
                parts = stripped_line.split(';;')
                # 格式：id;;name;;name_en;;standard;;condition;;unit;;category;;order;;data_type;;options (10 列)
                if len(parts) != 10:
                    self.stdout.write(self.style.WARNING(f'  [!] 格式错误，跳过: {stripped_line}'))
                    skipped_count += 1
                    out_lines.append(stripped_line)
                    continue

                config_id, name, name_en, std, cond, unit, cat_name, order_str, dtype, opts = [p.strip() for p in parts]

                category_obj = cat_objs.get(cat_name)
                if not category_obj:
                    self.stdout.write(self.style.WARNING(f'  [!] 未找到分类 "{cat_name}"，跳过: {name}'))
                    skipped_count += 1
                    out_lines.append(stripped_line)
                    continue

                order = int(order_str)
                defaults = {
                    'name': name,
                    'name_en': name_en,
                    'standard': std,
                    'condition': cond,
                    'category': category_obj,
                    'unit': unit,
                    'order': order,
                    'data_type': dtype,
                    'options_config': opts,
                }

                # 以主键 id 识别：有 id 则更新或按该 id 建，无 id 则新增并回写新 id
                if config_id:
                    obj, created = TestConfig.objects.update_or_create(
                        pk=int(config_id),
                        defaults=defaults,
                    )
                    out_lines.append(stripped_line)  # 已有 id，原样保留
                else:
                    obj = TestConfig.objects.create(**defaults)
                    created = True
                    out_lines.append(f'{obj.pk};;{stripped_line}')  # 新增条目回写新 id

                if created:
                    created_count += 1
                else:
                    updated_count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'处理 "{stripped_line}" 时出错: {e}'))
                skipped_count += 1
                out_lines.append(stripped_line)

        # 将新增条目回写的新 id 写回源文件，保证后续运行以稳定 id 识别
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(out_lines) + '\n')

        self.stdout.write(f'测试配置项导入完成: 新建 {created_count}, 更新 {updated_count}, 跳过 {skipped_count}。')

    def add_arguments(self, parser):
        parser.add_argument(
            '--writeback',
            action='store_true',
            help='导入完成后，将数据库中存在但 test_configs.txt 未收录的配置项回写到文件末尾',
        )

    def _writeback_missing(self):
        """将数据库中存在但 txt 未收录的配置项，按 10 列格式回写到文件末尾。

        触发方式：python manage.py import_configs --writeback
        用途：后台手动新增的指标，运行后会被追加进 txt，之后以稳定 id 被导入命令管理。
        """
        file_path = os.path.join(settings.BASE_DIR, 'init', 'test_configs.txt')
        self.stdout.write(self.style.HTTP_INFO('\n--- 正在回写未收录的配置项 ---'))

        existing_ids = set()
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    parts = stripped.split(';;')
                    if len(parts) == 10 and parts[0].strip().isdigit():
                        existing_ids.add(int(parts[0].strip()))

        missing = TestConfig.objects.select_related('category').exclude(pk__in=existing_ids).order_by('pk')
        if not missing.exists():
            self.stdout.write('  数据库中无未收录的配置项，无需回写。')
            return

        lines_to_append = []
        for cfg in missing:
            line = (f"{cfg.pk};;{cfg.name};;{cfg.name_en};;{cfg.standard};;{cfg.condition};;"
                    f"{cfg.unit};;{cfg.category.name};;{cfg.order};;{cfg.data_type};;{cfg.options_config}")
            lines_to_append.append(line)
            self.stdout.write(f'  [+] 回写: id={cfg.pk} {cfg.name}')

        with open(file_path, 'a', encoding='utf-8') as f:
            f.write('\n'.join(lines_to_append) + '\n')

        self.stdout.write(f'回写完成: 共新增 {len(lines_to_append)} 条配置项。')

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('🚀 开始导入测试配置库...'))
        category_objects = self._import_metric_categories()
        self._import_test_configs(category_objects)
        if kwargs.get('writeback'):
            self._writeback_missing()
        self.stdout.write(self.style.SUCCESS('\n✅ 所有测试配置导入完成！'))
