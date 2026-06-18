"""
初始化权限管理命令 — 部署时预设各角色组的 Django 原生权限码 (L3)。

用法:
    python manage.py init_permissions              # 创建/更新角色组并分配权限
    python manage.py init_permissions --assign-users # 同时将现有用户按 user_type 归入对应组
    python manage.py init_permissions --dry-run     # 仅预览变更，不写入数据库

角色组对应关系（与 IdentityConfig 对齐）:
    RND_ONLY        研发工程师 + 管理员        → 配方、预研、材料
    TECH_CORE       研发 + 工艺 + 管理员       → 上述 + 工艺、排产
    PROCESS_ONLY    工艺工程师 + 管理员        → 工艺参数、设备
    SUPPLY_CHAIN    采购专员 + 管理员          → 原材料、供应商
    PRODUCTION_CREW 操作员(挤/色/注/测) + 管理员 → 车间执行
    SALES           业务员                     → 客户、OEM、商机档案

用户归组规则（user_type → group）:
    ENGINEER          → RND_ONLY + TECH_CORE
    PROCESS_ENGINEER  → PROCESS_ONLY + TECH_CORE
    SALES             → SALES
    PURCHASING        → SUPPLY_CHAIN
    ADMIN             → 全部 6 个组
    四位操作员        → PRODUCTION_CREW

幂等性: 可重复执行，已存在的组、权限、用户归属不会被重复创建。
"""
import re
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    """Django 管理命令：初始化 L3 权限码并分配给预定义角色组。"""
    help = __doc__

    def add_arguments(self, parser):
        """注册 --dry-run 和 --assign-users CLI 参数。Args: parser: argparse.ArgumentParser。"""
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='仅预览将要执行的操作，不写入数据库',
        )
        parser.add_argument(
            '--assign-users',
            action='store_true',
            help='同时将现有用户按 user_type 自动归入对应的权限组',
        )

    # ── user_type → 权限组 映射 ─────────────────────────────────
    # 每个 user_type 对应一个或多个 Group 名称
    USER_TYPE_GROUP_MAP = {
        'ENGINEER':           ['RND_ONLY', 'TECH_CORE'],
        'PROCESS_ENGINEER':   ['PROCESS_ONLY', 'TECH_CORE'],
        'SALES':              ['SALES'],
        'PURCHASING':         ['SUPPLY_CHAIN'],
        'ADMIN':              ['RND_ONLY', 'TECH_CORE', 'PROCESS_ONLY',
                               'SUPPLY_CHAIN', 'PRODUCTION_CREW', 'SALES'],
        'EXTRUSION_OPERATOR': ['PRODUCTION_CREW'],
        'COLOR_OPERATOR':     ['PRODUCTION_CREW'],
        'INJECTION_OPERATOR': ['PRODUCTION_CREW'],
        'TESTING_OPERATOR':   ['PRODUCTION_CREW'],
    }

    # ── 权限分配表 ──────────────────────────────────────────────
    # 格式: { app_label: { 'group_name': [action_list], ... } }
    # action_list: ['view', 'add', 'change', 'delete'] 或 ['all']
    # 特殊值 'all' = ['view', 'add', 'change', 'delete']

    PERMISSION_MAP = {
        # ── R&D 核心 ──
        'app_formula': {
            'RND_ONLY':        'all',
            'TECH_CORE':       'all',
            'PROCESS_ONLY':    ['view'],
            'PRODUCTION_CREW': ['view'],
        },
        'app_basic_research': {
            'RND_ONLY':  'all',
            'TECH_CORE': ['view'],
        },
        'app_material': {
            'RND_ONLY':        'all',
            'TECH_CORE':       'all',
            'PROCESS_ONLY':    ['view'],
            'PRODUCTION_CREW': ['view'],
            'SALES':           ['view'],
        },
        # ── 项目管理 ──
        'app_project': {
            'RND_ONLY':        'all',
            'TECH_CORE':       'all',
            'PROCESS_ONLY':    ['view', 'add', 'change'],
            'PRODUCTION_CREW': ['view'],
            'SALES':           ['view', 'add', 'change'],
        },
        # ── 工艺 / 设备 ──
        'app_process': {
            'RND_ONLY':        ['view'],
            'TECH_CORE':       'all',
            'PROCESS_ONLY':    'all',
            'PRODUCTION_CREW': ['view'],
        },
        # ── 试验排产 ──
        'app_trial_production': {
            'RND_ONLY':        'all',
            'TECH_CORE':       'all',
            'PROCESS_ONLY':    ['view', 'add', 'change'],
            'PRODUCTION_CREW': ['view', 'add', 'change'],
        },
        # ── 表单管理 ──
        'app_form_management': {
            'RND_ONLY':        'all',
            'TECH_CORE':       'all',
            'PROCESS_ONLY':    'all',
            'SUPPLY_CHAIN':    ['view', 'add', 'change'],
            'PRODUCTION_CREW': ['view', 'add', 'change'],
            'SALES':           ['view', 'add', 'change'],
        },
        # ── 工作流 ──
        'app_workflow': {
            'RND_ONLY':        'all',
            'TECH_CORE':       'all',
            'PROCESS_ONLY':    ['view', 'add', 'change'],
            'SUPPLY_CHAIN':    ['view'],
            'PRODUCTION_CREW': ['view'],
            'SALES':           ['view'],
        },
        # ── 原材料库 ──
        'app_raw_material': {
            'RND_ONLY':        ['view'],
            'TECH_CORE':       ['view'],
            'SUPPLY_CHAIN':    'all',
            'PROCESS_ONLY':    ['view'],
        },
        # ── 商机档案 ──
        'app_repository': {
            'RND_ONLY':        ['view'],
            'TECH_CORE':       ['view'],
            'SUPPLY_CHAIN':    ['view'],
            'SALES':           'all',
        },
        # ── 通知 ──
        'app_notification': {
            'RND_ONLY':        ['view'],
            'TECH_CORE':       ['view'],
            'PROCESS_ONLY':    ['view'],
            'SUPPLY_CHAIN':    ['view'],
            'PRODUCTION_CREW': ['view'],
            'SALES':           ['view'],
        },
        # ── 附件 ──
        'app_attachment': {
            'RND_ONLY':        'all',
            'TECH_CORE':       'all',
            'PROCESS_ONLY':    ['view', 'add'],
            'SUPPLY_CHAIN':    ['view', 'add'],
            'PRODUCTION_CREW': ['view'],
            'SALES':           ['view', 'add'],
        },
        # ── 用户管理 ──
        'app_user': {
            'RND_ONLY':        ['view', 'change'],
            'TECH_CORE':       ['view', 'change'],
            'PROCESS_ONLY':    ['view'],
            'SUPPLY_CHAIN':    ['view'],
            'PRODUCTION_CREW': ['view'],
            'SALES':           ['view'],
        },
        # ── 产品目录（外部手册）──
        'app_catalog': {
            'RND_ONLY':        'all',
            'TECH_CORE':       'all',
            'PROCESS_ONLY':    ['view'],
            'SUPPLY_CHAIN':    ['view'],
            'PRODUCTION_CREW': ['view'],
            'SALES':           ['view', 'add', 'change'],
        },
    }

    # 需要 skip 的 Django 内置 app（不参与业务权限分配）
    SKIP_APP_LABELS = {'auth', 'contenttypes', 'sessions', 'admin', 'axes'}

    @staticmethod
    def _resolve_actions(actions):
        """将 'all' 或 action 列表展开为标准四元组。

        Args: actions: 'all' 或 action 字符串列表。
        Returns: ['view', 'add', 'change', 'delete'] 格式的列表。
        """
        if actions == 'all':
            return ['view', 'add', 'change', 'delete']
        return actions

    def handle(self, *args, **options):
        """执行权限初始化主流程。Args: options: 命令行参数字典。"""
        dry_run = options['dry_run']
        verbosity = self.verbosity = options['verbosity']

        # 收集所有可用的业务模型权限
        all_perms = Permission.objects.select_related('content_type').exclude(
            content_type__app_label__in=self.SKIP_APP_LABELS,
        )

        # 建立快捷查找: {(app_label, model, action): permission_obj}
        perm_lookup = {}
        for p in all_perms:
            match = re.match(r'^(view|add|change|delete)_(.+)$', p.codename)
            if match:
                action = match.group(1)
            else:
                # 非标准 codename（如自定义权限），使用完整 codename 作为 action
                action = p.codename
            key = (p.content_type.app_label, p.content_type.model, action)
            perm_lookup[key] = p

        # 预先计算变更日志
        changes = []  # [(group_name, perm_name, action: 'add'|'skip')]

        for app_label, group_map in self.PERMISSION_MAP.items():
            content_types = ContentType.objects.filter(app_label=app_label)
            if not content_types.exists():
                if verbosity >= 1:
                    self.stdout.write(self.style.WARNING(
                        f'[跳过] app "{app_label}" 无对应 ContentType，可能尚未 migrate'
                    ))
                continue

            # 遍历该 app 下的所有模型，为每个模型分配权限
            for ct in content_types:

                for group_name, actions_config in group_map.items():
                    group, _created = Group.objects.get_or_create(name=group_name)
                    action_list = self._resolve_actions(actions_config)

                    for action in action_list:
                        perm_key = (app_label, ct.model, action)
                        perm = perm_lookup.get(perm_key)
                        if perm is None:
                            if verbosity >= 2:
                                self.stdout.write(f'  [WARN] 权限码不存在: {app_label}.{action}_{ct.model}')
                            continue

                        if perm in group.permissions.all():
                            changes.append((group_name, perm.name, 'skip'))
                        else:
                            changes.append((group_name, perm.name, 'add'))
                            if not dry_run:
                                group.permissions.add(perm)

        # ── 输出 ──
        if dry_run:
            self.stdout.write(self.style.WARNING('\n=== DRY RUN 模式 — 以下为预览，未实际写入 ===\n'))

        self.stdout.write(f'角色组数量: {len(self.PERMISSION_MAP)} 个 app 模块')
        self.stdout.write(f'权限变更: {len([c for c in changes if c[2] == "add"])} 条新增  /  '
                          f'{len([c for c in changes if c[2] == "skip"])} 条已存在\n')

        if verbosity >= 1:
            current_group = None
            for group_name, perm_name, action in changes:
                if group_name != current_group:
                    current_group = group_name
                    self.stdout.write(self.style.MIGRATE_HEADING(f'\n-- {group_name}'))
                if action == 'add':
                    self.stdout.write(f'  + {perm_name}')
                elif verbosity >= 2:
                    self.stdout.write(f'  . {perm_name} (已存在)')

        if dry_run:
            self.stdout.write(self.style.WARNING(
                '\n请移除 --dry-run 参数以实际执行权限初始化。'
            ))
        else:
            self.stdout.write(self.style.SUCCESS('\n权限初始化完成。'))

        # ── 用户归组（可选）──
        if options['assign_users']:
            self._assign_users_to_groups(dry_run=dry_run)

    def _assign_users_to_groups(self, dry_run=False):
        """将现有用户按 user_type 归入对应的权限组（跳过超管和已归组的用户）。

        Args: dry_run: 仅预览不写入数据库。
        """
        verbosity = self.verbosity
        group_cache = {}  # {name: Group}

        assign_log = []  # [(username, user_type, group_name)]

        for user in User.objects.select_related('department').iterator():
            if user.is_superuser:
                continue  # 超管绕过所有 L3 检查，无需归组

            target_groups = self.USER_TYPE_GROUP_MAP.get(user.user_type, [])
            if not target_groups:
                if verbosity >= 2:
                    self.stdout.write(f'  [跳过] {user.username} (user_type={user.user_type} 无对应组)')
                continue

            for group_name in target_groups:
                if group_name not in group_cache:
                    try:
                        group_cache[group_name] = Group.objects.get(name=group_name)
                    except Group.DoesNotExist:
                        if verbosity >= 1:
                            self.stdout.write(self.style.WARNING(
                                f'  [WARN] 组 "{group_name}" 不存在，请先运行 init_permissions（不含 --assign-users）'
                            ))
                        continue
                group = group_cache[group_name]

                if group in user.groups.all():
                    if verbosity >= 2:
                        self.stdout.write(f'  . {user.username} 已在组 {group_name} 中')
                    continue

                assign_log.append((user.username, user.user_type, group_name))
                if not dry_run:
                    user.groups.add(group)

        if assign_log:
            self.stdout.write(self.style.MIGRATE_HEADING('\n-- 用户归组'))
            current_user = None
            for username, user_type, group_name in assign_log:
                if username != current_user:
                    current_user = username
                    self.stdout.write(f'  {username} ({user_type})')
                self.stdout.write(f'    -> {group_name}')
            summary = f'\n用户归组: {len(set(u for u, _, _ in assign_log))} 人 / {len(assign_log)} 条分配'
            if dry_run:
                self.stdout.write(self.style.WARNING(summary + ' (预览)'))
            else:
                self.stdout.write(self.style.SUCCESS(summary))
        else:
            self.stdout.write('\n用户归组: 无需变更')
