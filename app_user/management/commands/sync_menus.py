"""
同步菜单 — 从 menu_modules.py 的 MenuModule 定义同步到 SidebarModule / SidebarSubItem DB 表。

用法:
    python manage.py sync_menus          # 同步菜单到 DB
    python manage.py sync_menus --dry-run # 仅预览变更

同步策略:
    代码覆盖: code, name, icon, url_name, sub_items 结构, permissions
    保留 DB:  sort_order, is_active, sub_items.role_group
    孤立处理: DB 有但代码无的记录 → 警告，不自动删除
"""

from django.core.management.base import BaseCommand
from app_user.services.menu_modules import MenuModule


# MenuModule 中所有 get_*() 方法的调用列表（顺序决定菜单排序）
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

    def _collect_definitions(self):
        """收集 MenuModule 中所有菜单定义。

        Returns: list[dict] — 按 MODULE_METHODS 顺序排列的模块定义。
        """
        return [fn() for fn in MODULE_METHODS]

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verbosity = options['verbosity']

        from app_user.models import SidebarModule, SidebarSubItem, ModuleAccessConfig
        from app_user.services.identity_service import IdentityService

        definitions = self._collect_definitions()
        code_defs = {d['code']: d for d in definitions if d}

        # 预加载现有 DB 记录
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
        created_subs = 0
        updated_subs = 0

        # ── 处理每个模块 ──
        for sort_idx, defn in enumerate(definitions):
            if not defn:
                continue
            code = defn['code']
            existing_mod = existing_modules.get(code)

            # 解析 module_access
            mac_code = defn.get('module_access_code')
            mac = mac_cache.get(mac_code) if mac_code else None

            if existing_mod:
                # 更新代码控制的字段
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

            # ── 处理子菜单 ──
            code_sub_defs = {s['name']: s for s in defn.get('sub_items', [])}
            existing_subs = {
                s.name: s
                for s in SidebarSubItem.objects.filter(module=existing_mod)
            }

            # 新增/更新子项
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

            # 警告：DB 有但代码无的子项
            orphaned_subs = set(existing_subs.keys()) - set(code_sub_defs.keys())
            for orphan_name in sorted(orphaned_subs):
                self.stdout.write(self.style.WARNING(
                    f'  [警告] 子项 "{orphan_name}" (模块 {code}) — DB 有记录但代码中已删除'))

        # ── 警告：DB 有但代码无的模块 ──
        orphaned_modules = set(existing_modules.keys()) - set(code_defs.keys())
        for orphan_code in sorted(orphaned_modules):
            self.stdout.write(self.style.WARNING(
                f'  [警告] 模块 "{orphan_code}" — DB 有记录但代码中已删除'))

        if not dry_run and (created_modules or updated_modules):
            IdentityService.invalidate_cache()

        self.stdout.write(self.style.SUCCESS(
            f'\n完成: 模块 +{created_modules} ~{updated_modules}, '
            f'子项 +{created_subs} ~{updated_subs}'
        ))
