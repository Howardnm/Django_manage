"""
同步菜单 — 从 menu_modules.py 的 MenuModule 定义同步到 SidebarModule / SidebarSubItem DB 表。

用法:
    python manage.py sync_menus            # 同步菜单到 DB
    python manage.py sync_menus --dry-run   # 仅预览变更
    python manage.py sync_menus --prune     # 同步 + 删除代码中已移除的模块/子项

同步策略:
    代码覆盖: code, name, icon, url_name, sub_items 结构, permissions
    保留 DB:  sort_order, is_active, sub_items.role_group, sub_items.min_level
    刷脏数据: 子项自动清理（代码中删除 → DB 也删除）
              模块需 --prune 才会删除（避免误删）
"""

from django.core.management.base import BaseCommand
from app_user.services.menu_modules import MenuModule


MODULE_METHODS = [
    MenuModule.get_dashboard,
    MenuModule.get_project,
    MenuModule.get_repository,
    MenuModule.get_basic_research,
    MenuModule.get_material,
    MenuModule.get_formula,
    MenuModule.get_trial_production,
    MenuModule.get_extrusion_production,
    MenuModule.get_color_center,
    MenuModule.get_mold_injection,
    MenuModule.get_material_testing,
    MenuModule.get_process,
    MenuModule.get_raw_material,
    MenuModule.get_form_management,
    MenuModule.get_workflow,
    MenuModule.get_admin,
]


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='仅预览将要执行的操作，不写入数据库')
        parser.add_argument('--prune', action='store_true',
                            help='删除 DB 中代码已移除的模块（默认仅警告）')

    def _collect_definitions(self):
        return [fn() for fn in MODULE_METHODS]

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        prune = options['prune']
        verbosity = options['verbosity']

        from app_user.models import SidebarModule, SidebarSubItem, ModuleAccessConfig
        from app_user.services.identity_service import IdentityService

        try:
            if not ModuleAccessConfig.objects.exists():
                self.stdout.write(self.style.ERROR(
                    'ModuleAccessConfig 表为空。请先运行:\n'
                    '  python manage.py migrate\n'
                    '  python manage.py sync_rbac_modules'
                ))
                return
        except Exception:
            self.stdout.write(self.style.ERROR(
                '数据库表不存在。请先运行: python manage.py migrate'
            ))
            return

        definitions = self._collect_definitions()
        code_defs = {d['code']: d for d in definitions if d}

        existing_modules = {
            sm.code: sm
            for sm in SidebarModule.objects.prefetch_related('sub_items')
        }
        mac_cache = {
            mac.module_code: mac
            for mac in ModuleAccessConfig.objects.all()
        }

        if dry_run:
            self.stdout.write(self.style.WARNING(
                '\n=== DRY RUN 模式 — 以下为预览，未实际写入 ===\n'))

        created_modules = 0
        updated_modules = 0
        deleted_modules = 0
        created_subs = 0
        updated_subs = 0
        deleted_subs = 0

        # ── 处理每个模块 ──
        for sort_idx, defn in enumerate(definitions):
            if not defn:
                continue
            code = defn['code']
            existing_mod = existing_modules.get(code)
            mac_code = defn.get('module_access_code')
            mac = mac_cache.get(mac_code) if mac_code else None

            if existing_mod:
                changed = False
                if existing_mod.name != defn['name']:
                    existing_mod.name = defn['name']; changed = True
                if existing_mod.icon != defn['icon']:
                    existing_mod.icon = defn['icon']; changed = True
                if existing_mod.url_name != defn['url_name']:
                    existing_mod.url_name = defn['url_name']; changed = True
                if existing_mod.module_access != mac:
                    existing_mod.module_access = mac; changed = True
                if changed:
                    updated_modules += 1
                    if verbosity >= 1:
                        self.stdout.write(f'  ~ {code}: {defn["name"]}')
                    if not dry_run:
                        existing_mod.save()
            else:
                created_modules += 1
                self.stdout.write(
                    self.style.MIGRATE_HEADING(f'  + {code}: {defn["name"]}'))
                if not dry_run:
                    existing_mod = SidebarModule.objects.create(
                        code=code, name=defn['name'], icon=defn['icon'],
                        url_name=defn['url_name'], module_access=mac,
                        sort_order=sort_idx,
                    )
                    existing_modules[code] = existing_mod

            if not existing_mod:
                continue

            # ── 子项同步 ──
            code_sub_names = {s['name'] for s in defn.get('sub_items', [])}
            existing_subs = {
                s.name: s
                for s in SidebarSubItem.objects.filter(module=existing_mod)
            }

            # 新增/更新
            for sub_defn in defn.get('sub_items', []):
                existing_sub = existing_subs.get(sub_defn['name'])
                if existing_sub:
                    sub_changed = False
                    if existing_sub.url_name != sub_defn['url_name']:
                        existing_sub.url_name = sub_defn['url_name']; sub_changed = True
                    code_perms = sub_defn.get('permissions', [])
                    if existing_sub.permissions != code_perms:
                        existing_sub.permissions = code_perms; sub_changed = True
                    if sub_changed:
                        updated_subs += 1
                        if not dry_run:
                            existing_sub.save()
                else:
                    created_subs += 1
                    if not dry_run:
                        SidebarSubItem.objects.create(
                            module=existing_mod, name=sub_defn['name'],
                            url_name=sub_defn['url_name'],
                            permissions=sub_defn.get('permissions', []),
                        )

            # 删除代码中已移除的子项（子项增删只能通过代码，自动清理）
            for orphan_name, orphan_sub in existing_subs.items():
                if orphan_name not in code_sub_names:
                    deleted_subs += 1
                    self.stdout.write(
                        self.style.WARNING(f'  - 子项 "{orphan_name}" ({code}) — 代码中已删除'))
                    if not dry_run:
                        orphan_sub.delete()

        # ── 孤立模块 ──
        orphaned_modules = set(existing_modules.keys()) - set(code_defs.keys())
        if orphaned_modules:
            for orphan_code in sorted(orphaned_modules):
                if prune:
                    deleted_modules += 1
                    self.stdout.write(
                        self.style.WARNING(f'  - 模块 "{orphan_code}" — 代码中已删除，已清理'))
                    if not dry_run:
                        existing_modules[orphan_code].delete()
                else:
                    self.stdout.write(self.style.WARNING(
                        f'  [警告] 模块 "{orphan_code}" — DB 有记录但代码中已删除，'
                        f'使用 --prune 可自动清理'))

        if not dry_run and (created_modules or updated_modules or deleted_modules
                            or deleted_subs):
            IdentityService.invalidate_cache()

        self.stdout.write(self.style.SUCCESS(
            f'\n完成: 模块 +{created_modules} ~{updated_modules} -{deleted_modules}, '
            f'子项 +{created_subs} ~{updated_subs} -{deleted_subs}'
        ))
