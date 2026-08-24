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

        Returns: {module_code: {'app_label': ..., 'class_name': ..., 'module_name': ...}} 字典。
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
                module_name = getattr(cls, 'module_name', None) or code
                module_description = getattr(cls, 'module_description', None) or ''
                discovered[code] = {
                    'app_label': app_config.label,
                    'class_name': name,
                    'module_name': module_name,
                    'module_description': module_description,
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
        existing_qs = ModuleAccessConfig.objects.all()
        existing_map = {mac.module_code: mac for mac in existing_qs}

        to_create = {k: v for k, v in discovered.items() if k not in existing_map}
        orphaned = set(existing_map) - set(discovered.keys())

        # 回填：已有记录且 module_name 仍为占位值（等于 module_code）时，更新为 mixin 声明的中文名
        to_backfill = {
            k: v for k, v in discovered.items()
            if k in existing_map and existing_map[k].module_name == k
        }
        # 缺失提示：声明了 module_code 但未声明 module_name 的 mixin
        missing_name = {k: v for k, v in discovered.items() if v['module_name'] == k}

        # 回填描述：DB 记录描述为空、且 mixin 声明了非空描述时更新
        to_backfill_desc = {
            k: v for k, v in discovered.items()
            if k in existing_map
            and v['module_description']
            and not existing_map[k].module_description
        }

        if dry_run:
            self.stdout.write(self.style.WARNING(
                '\n=== DRY RUN 模式 — 以下为预览，未实际写入 ===\n'))

        self.stdout.write(f'发现 {len(discovered)} 个 module_code，'
                          f'DB 已有 {len(existing_map)} 个记录')

        if not to_create and not to_backfill and not to_backfill_desc and not orphaned:
            self.stdout.write(self.style.SUCCESS('全部同步，无需变更。'))
            return

        # ── 创建缺失的记录 ──
        if to_create:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f'\n[新增] {len(to_create)} 个 ModuleAccessConfig:'))
            for code, info in sorted(to_create.items()):
                self.stdout.write(
                    f'  + {code} ({info["module_name"]}, '
                    f'app={info["app_label"]}, mixin={info["class_name"]})')
                if not dry_run:
                    ModuleAccessConfig.objects.create(
                        module_code=code,
                        module_name=info['module_name'],
                        module_description=info['module_description'],
                        min_level=1,
                        enforce_dept_isolation=True,
                        enforce_group_isolation=False,
                    )
            if not dry_run:
                self.stdout.write(self.style.WARNING(
                    f'\n  注意: 以上 {len(to_create)} 个新模块未分配任何角色组（role_groups 留空），'
                    f'当前为 fail-closed：仅超管可访问。'
                    f'请手动在 Admin 中为这些模块配置允许访问的角色组。'))

        # ── 回填已有记录的占位模块名 ──
        if to_backfill:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f'\n[回填] {len(to_backfill)} 个已有记录模块名（原为占位值 module_code）:'))
            for code, info in sorted(to_backfill.items()):
                self.stdout.write(
                    f'  ~ {code} -> {info["module_name"]}')
                if not dry_run:
                    ModuleAccessConfig.objects.filter(module_code=code).update(
                        module_name=info['module_name'])

        # ── 回填已有记录空描述 ──
        if to_backfill_desc:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f'\n[回填描述] {len(to_backfill_desc)} 个已有记录配置说明:'))
            for code, info in sorted(to_backfill_desc.items()):
                self.stdout.write(
                    f'  ~ {code} -> {info["module_description"]}')
                if not dry_run:
                    ModuleAccessConfig.objects.filter(module_code=code).update(
                        module_description=info['module_description'])

        # ── 报告孤立记录 ──
        if orphaned:
            self.stdout.write(self.style.WARNING(
                f'\n[警告] {len(orphaned)} 个 DB 记录无对应 mixin（可能已删除）:'))
            for code in sorted(orphaned):
                self.stdout.write(f'  ! {code}')

        # ── 提示未声明中文名的 mixin ──
        if missing_name:
            self.stdout.write(self.style.WARNING(
                f'\n[提示] {len(missing_name)} 个 mixin 声明了 module_code 但未声明 '
                f'module_name（仍以 code 作为名称），建议补全:'))
            for code, info in sorted(missing_name.items()):
                self.stdout.write(
                    f'  ? {code} (app={info["app_label"]}, mixin={info["class_name"]})')

        if not dry_run and (to_create or to_backfill or to_backfill_desc):
            IdentityService.invalidate_cache()
            self.stdout.write(self.style.SUCCESS(
                f'\n完成: 新增 {len(to_create)} 个，回填名 {len(to_backfill)} 个，'
                f'回填描述 {len(to_backfill_desc)} 个，'
                f'跳过 {len(discovered) - len(to_create)} 个（已存在）。'
            ))
