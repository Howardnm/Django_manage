"""
同步 RBAC 模块配置 — 扫描所有 app 的 mixin 中声明的 module_code，
自动在 ModuleAccessConfig 表中创建缺失的记录。

用法:
    python manage.py sync_rbac_modules          # 扫描并创建缺失的 ModuleAccessConfig
    python manage.py sync_rbac_modules --dry-run # 仅预览变更
"""

import inspect
from importlib import import_module

from django.apps import apps
from django.core.management.base import BaseCommand
from app_user.mixins import UnifiedAccessMixin


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='仅预览将要执行的操作，不写入数据库')

    def _discover_module_codes(self):
        """扫描所有已安装 app 的 mixins 模块，发现所有声明的 module_code。

        Returns: {module_code: {'app_label': ..., 'class_name': ...}} 字典。
        """
        discovered = {}
        for app_config in apps.get_app_configs():
            try:
                mixins_module = import_module(f'{app_config.name}.mixins')
            except ModuleNotFoundError:
                continue

            for name, cls in inspect.getmembers(mixins_module, inspect.isclass):
                # 只收集直接或间接继承 UnifiedAccessMixin 且声明了 module_code 的类
                if not issubclass(cls, UnifiedAccessMixin) or cls is UnifiedAccessMixin:
                    continue
                code = getattr(cls, 'module_code', None)
                if not code:
                    continue
                discovered[code] = {
                    'app_label': app_config.label,
                    'class_name': name,
                }
        return discovered

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verbosity = options['verbosity']

        from app_user.models import ModuleAccessConfig
        from app_user.services.identity_service import IdentityService

        # 前置检查
        try:
            ModuleAccessConfig.objects.exists()
        except Exception:
            self.stdout.write(self.style.ERROR(
                'ModuleAccessConfig 表不存在。请先运行: python manage.py migrate'
            ))
            return

        discovered = self._discover_module_codes()
        existing = set(ModuleAccessConfig.objects.values_list('module_code', flat=True))

        to_create = {k: v for k, v in discovered.items() if k not in existing}
        orphaned = existing - set(discovered.keys())

        if dry_run:
            self.stdout.write(self.style.WARNING(
                '\n=== DRY RUN 模式 — 以下为预览，未实际写入 ===\n'))

        self.stdout.write(f'发现 {len(discovered)} 个 module_code，'
                          f'DB 已有 {len(existing)} 个记录')

        if not to_create and not orphaned:
            self.stdout.write(self.style.SUCCESS('全部同步，无需变更。'))
            return

        # ── 创建缺失的记录 ──
        if to_create:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f'\n[新增] {len(to_create)} 个 ModuleAccessConfig:'))
            for code, info in sorted(to_create.items()):
                self.stdout.write(
                    f'  + {code} (app={info["app_label"]}, mixin={info["class_name"]})')
                if not dry_run:
                    ModuleAccessConfig.objects.create(
                        module_code=code,
                        module_name=code,  # 默认名称为 module_code，管理员可在 Admin 中修改
                        min_level=1,
                        enforce_dept_isolation=True,
                        enforce_group_isolation=False,
                    )

        # ── 报告孤立记录 ──
        if orphaned:
            self.stdout.write(self.style.WARNING(
                f'\n[警告] {len(orphaned)} 个 DB 记录无对应 mixin（可能已删除）:'))
            for code in sorted(orphaned):
                self.stdout.write(f'  ! {code}')

        if not dry_run and to_create:
            IdentityService.invalidate_cache()
            self.stdout.write(self.style.SUCCESS(
                f'\n完成: 新增 {len(to_create)} 个，跳过 '
                f'{len(discovered) - len(to_create)} 个（已存在）。'
            ))
