"""
RBAC 一键初始化 — 按正确顺序依次执行全部初始化步骤。

用法:
    python manage.py init_rbac          # 执行全部初始化
    python manage.py init_rbac --dry-run # 仅预览，不写入

执行顺序（每步失败则终止）:
    1. sync_rbac_modules — 扫描 mixin → 同步 ModuleAccessConfig
    2. sync_menus        — 读取 menu_modules.py → 同步 SidebarModule
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand


STEPS = [
    ('sync_rbac_modules', '扫描 mixin → 同步 ModuleAccessConfig'),
    ('sync_menus',        '读取 menu_modules.py → 同步 SidebarModule'),
]


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='仅预览，不写入数据库')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        total = len(STEPS)

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'\n=== RBAC 一键初始化 ({total} 步) ===\n'))

        for i, (cmd, desc) in enumerate(STEPS, 1):
            self.stdout.write(f'[{i}/{total}] {desc} ...')
            try:
                kwargs = {}
                if dry_run:
                    kwargs['dry_run'] = True
                call_command(cmd, **kwargs)
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f'\n✗ 第 {i} 步失败: {cmd}\n  错误: {e}\n'
                    f'  请修复后重新运行: python manage.py init_rbac'
                ))
                return

        self.stdout.write(self.style.SUCCESS(
            f'\n=== 全部 {total} 步完成 ==='
        ))
