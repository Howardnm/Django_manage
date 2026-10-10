import os
from django.core.management.base import BaseCommand
from django.conf import settings
from app_raw_material.models import RawMaterialType

class Command(BaseCommand):
    """
    从 init/raw_material_types.txt 批量导入或更新原材料类型。

    每行 5 段，以 ;; 分隔: id;;name;;code;;order;;description
    按 id 覆盖同一行，因此可以修改已有类型的名称。

    python manage.py import_raw_material_types --generate   # 从数据库导出 txt
    python manage.py import_raw_material_types              # 导入回写
    python manage.py import_raw_material_types --dry-run    # 导入前预览
    """
    help = '从 init/raw_material_types.txt 批量导入或更新原材料类型'

    def add_arguments(self, parser):
        parser.add_argument(
            '--generate', action='store_true',
            help='从数据库导出 init/raw_material_types.txt',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='导入前预览，不写入数据库',
        )

    def handle(self, *args, **options):
        file_path = os.path.join(settings.BASE_DIR, 'init', 'raw_material_types.txt')

        if options['generate'] and options['dry_run']:
            self.stdout.write(self.style.ERROR('不能同时使用 --generate 和 --dry-run'))
            return

        if options['generate']:
            self._generate(file_path)
        else:
            self._import(file_path, dry_run=options['dry_run'])

    def _generate(self, file_path):
        """把当前原材料类型按 id 导出为 txt，覆盖原文件。"""
        self.stdout.write(self.style.MIGRATE_HEADING('\n=== 导出原材料类型 ... ==='))

        lines = []
        for obj in RawMaterialType.objects.order_by('pk'):
            fields = [
                str(obj.pk),
                obj.name,
                obj.code,
                str(obj.order),
                obj.description or '',
            ]
            sanitized = [self._sanitize_field(value) for value in fields]
            lines.append(';;'.join(sanitized))

        # 与现有底稿一致，使用 CRLF，避免整文件被换行符改写
        content = '\r\n'.join(lines)
        if content:
            content += '\r\n'
        with open(file_path, 'w', encoding='utf-8', newline='') as f:
            f.write(content)

        self.stdout.write(self.style.SUCCESS(f'[OK] 已导出 {file_path}'))
        self.stdout.write(f'     共 {len(lines)} 条。')

    @staticmethod
    def _sanitize_field(value):
        """保证一个字段不撑破「一行一条、;; 分隔」的格式。"""
        text = str(value).replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ').strip()
        return text.replace(';;', '；；')

    def _import(self, file_path, dry_run=False):
        if dry_run:
            self.stdout.write(self.style.WARNING('\n=== [DRY-RUN] 预览模式，不会写入数据库 ==='))
        else:
            self.stdout.write(f'开始从 {file_path} 导入原材料类型数据...')

        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'文件未找到: {file_path}'))
            return

        existing = {obj.pk: obj for obj in RawMaterialType.objects.all()}
        name_owner = {obj.name: obj.pk for obj in existing.values()}

        created_count = 0
        updated_count = 0
        unchanged_count = 0
        skipped_count = 0
        seen_ids = set()

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                stripped_line = line.strip()
                if not stripped_line:
                    continue

                parsed = self._parse_line(stripped_line)
                if parsed is None:
                    skipped_count += 1
                    continue
                type_id, name, code, order, description = parsed

                if type_id in seen_ids:
                    self.stdout.write(self.style.WARNING(f'  [!] 重复 id，跳过行: {stripped_line}'))
                    skipped_count += 1
                    continue
                seen_ids.add(type_id)

                owner = name_owner.get(name)
                if owner is not None and owner != type_id:
                    self.stdout.write(self.style.WARNING(
                        f'  [!] 名称已被 id={owner} 占用，跳过: {name} (id={type_id})'
                    ))
                    skipped_count += 1
                    continue

                current = existing.get(type_id)
                if current is None:
                    if not dry_run:
                        try:
                            RawMaterialType.objects.create(
                                pk=type_id,
                                name=name,
                                code=code,
                                order=order,
                                description=description,
                            )
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f'处理 "{stripped_line}" 时出错: {e}'))
                            skipped_count += 1
                            continue
                    self.stdout.write(self.style.SUCCESS(f'  [+] 新建: id={type_id} {name}'))
                    created_count += 1
                    name_owner[name] = type_id
                    continue

                changes = self._diff(current, name, code, order, description)
                if not changes:
                    unchanged_count += 1
                    continue

                old_name = current.name
                if not dry_run:
                    previous = (current.name, current.code, current.order, current.description)
                    current.name = name
                    current.code = code
                    current.order = order
                    current.description = description
                    try:
                        current.save(update_fields=['name', 'code', 'order', 'description'])
                    except Exception as e:
                        current.name, current.code, current.order, current.description = previous
                        self.stdout.write(self.style.ERROR(f'处理 "{stripped_line}" 时出错: {e}'))
                        skipped_count += 1
                        continue
                if old_name != name:
                    name_owner.pop(old_name, None)
                name_owner[name] = type_id
                self.stdout.write(f'  [*] 更新: id={type_id} {name} | ' + '；'.join(changes))
                updated_count += 1

        if not dry_run:
            self._reset_pk_sequence()

        title = '预览完成！' if dry_run else '导入完成！'
        self.stdout.write(self.style.SUCCESS(f'\n{title}'))
        self.stdout.write(
            f'总计: 新建 {created_count} 个, 更新 {updated_count} 个, '
            f'无变化 {unchanged_count} 个, 跳过 {skipped_count} 个。'
        )

    def _parse_line(self, stripped_line):
        """解析一行。失败时打印警告并返回 None。"""
        parts = stripped_line.split(';;')
        if len(parts) != 5:
            self.stdout.write(self.style.WARNING(f'  [!] 格式错误，跳过行: {stripped_line}'))
            return None

        id_str, name, code, order_str, description = [part.strip() for part in parts]
        if not name:
            self.stdout.write(self.style.WARNING(f'  [!] 名称为空，跳过行: {stripped_line}'))
            return None

        try:
            type_id = int(id_str)
            order = int(order_str)
            if type_id <= 0 or order < 0:
                raise ValueError
        except ValueError:
            self.stdout.write(self.style.WARNING(f'  [!] id 或排序权重格式错误，跳过行: {stripped_line}'))
            return None

        return type_id, name, code, order, description

    @staticmethod
    def _diff(current, name, code, order, description):
        changes = []
        if current.name != name:
            changes.append(f'名称 {current.name} -> {name}')
        if current.code != code:
            changes.append(f'代码 {current.code} -> {code}')
        if current.order != order:
            changes.append(f'排序 {current.order} -> {order}')
        if (current.description or '') != description:
            changes.append('描述已变更')
        return changes

    def _reset_pk_sequence(self):
        """显式主键插入不会推进 PostgreSQL 序列，拨到 MAX(id) 以免之后新建撞主键。"""
        from django.db import connection

        if connection.vendor != 'postgresql':
            return

        table = RawMaterialType._meta.db_table
        quoted = connection.ops.quote_name(table)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {quoted}), 1))",
                [table],
            )
