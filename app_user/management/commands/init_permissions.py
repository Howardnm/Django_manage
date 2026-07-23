"""
初始化权限管理命令 — 从 L3PermissionConfig (DB) 读取权限矩阵并分配给 Django auth.Group。

用法:
    python manage.py init_permissions              # 创建/更新角色组并分配权限
    python manage.py init_permissions --assign-users # 同时将现有用户按 RoleGroup 归入对应组
    python manage.py init_permissions --dry-run     # 仅预览变更，不写入数据库

权限数据源: L3PermissionConfig 模型（通过 data migration 从原 PERMISSION_MAP 填充）。

用户归组规则: 从 UserRole → RoleGroup 的 M2M 关系动态推断，不再硬编码映射表。

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
    """Django 管理命令：从 L3PermissionConfig 读取并分配 Django 权限码。"""
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='仅预览将要执行的操作，不写入数据库')
        parser.add_argument('--assign-users', action='store_true',
                            help='同时将现有用户按 RoleGroup 自动归入对应的权限组')

    SKIP_APP_LABELS = {'auth', 'contenttypes', 'sessions', 'admin', 'axes'}

    @staticmethod
    def _resolve_actions(actions):
        """将 'all' 或 action 列表展开为标准四元组。"""
        if actions == 'all':
            return ['view', 'add', 'change', 'delete']
        return actions

    def _get_permission_map(self):
        """从 L3PermissionConfig (DB) 读取权限矩阵。

        Returns: {app_label: {group_name: [actions]}} 字典。
        """
        try:
            from app_user.models import L3PermissionConfig
            configs = L3PermissionConfig.objects.filter(is_active=True).select_related('role_group')
            perm_map = {}
            for cfg in configs:
                if cfg.app_label not in perm_map:
                    perm_map[cfg.app_label] = {}
                perm_map[cfg.app_label][cfg.role_group.code] = self._resolve_actions(cfg.actions)
            return perm_map
        except Exception:
            return {}

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verbosity = self.verbosity = options['verbosity']

        perm_map = self._get_permission_map()
        if not perm_map:
            self.stdout.write(self.style.WARNING(
                'L3PermissionConfig 表为空或不存在。请先运行 migrate 和 data migration。'
            ))
            return

        # 收集所有可用的业务模型权限
        all_perms = Permission.objects.select_related('content_type').exclude(
            content_type__app_label__in=self.SKIP_APP_LABELS,
        )

        # 快捷查找: {(app_label, model, action): permission_obj}
        perm_lookup = {}
        for p in all_perms:
            match = re.match(r'^(view|add|change|delete)_(.+)$', p.codename)
            action = match.group(1) if match else p.codename
            key = (p.content_type.app_label, p.content_type.model, action)
            perm_lookup[key] = p

        changes = []

        for app_label, group_map in perm_map.items():
            content_types = ContentType.objects.filter(app_label=app_label)
            if not content_types.exists():
                if verbosity >= 1:
                    self.stdout.write(self.style.WARNING(
                        f'[跳过] app "{app_label}" 无对应 ContentType，可能尚未 migrate'
                    ))
                continue

            for ct in content_types:
                for group_name, action_list in group_map.items():
                    group, _created = Group.objects.get_or_create(name=group_name)

                    for action in action_list:
                        perm_key = (app_label, ct.model, action)
                        perm = perm_lookup.get(perm_key)
                        if perm is None:
                            if verbosity >= 2:
                                self.stdout.write(
                                    f'  [WARN] 权限码不存在: {app_label}.{action}_{ct.model}')
                            continue

                        if perm in group.permissions.all():
                            changes.append((group_name, perm.name, 'skip'))
                        else:
                            changes.append((group_name, perm.name, 'add'))
                            if not dry_run:
                                group.permissions.add(perm)

        if dry_run:
            self.stdout.write(self.style.WARNING(
                '\n=== DRY RUN 模式 — 以下为预览，未实际写入 ===\n'))

        self.stdout.write(f'App 模块数: {len(perm_map)}')
        self.stdout.write(
            f'权限变更: {len([c for c in changes if c[2] == "add"])} 条新增  /  '
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
            self.stdout.write(self.style.WARNING('\n请移除 --dry-run 参数以实际执行权限初始化。'))
        else:
            self.stdout.write(self.style.SUCCESS('\n权限初始化完成。'))

        if options['assign_users']:
            self._assign_users_to_groups(dry_run=dry_run)

    def _assign_users_to_groups(self, dry_run=False):
        """将现有用户按 UserRole → RoleGroup 关系归入对应的 Django auth.Group。

        规则: 用户的 UserRole 属于哪些 RoleGroup，就加入对应的 Group。
        """
        verbosity = self.verbosity
        group_cache = {}
        assign_log = []

        for user in User.objects.select_related('user_type').iterator():
            if user.is_superuser:
                continue

            # 从 UserRole → RoleGroup M2M 动态获取目标组名
            try:
                role_groups = user.user_type.groups.filter(is_active=True)
            except Exception:
                continue
            target_groups = list(role_groups.values_list('code', flat=True))
            if not target_groups:
                if verbosity >= 2:
                    self.stdout.write(
                        f'  [跳过] {user.username} (role={user.user_type_id} 无关联 RoleGroup)')
                continue

            for group_name in target_groups:
                if group_name not in group_cache:
                    try:
                        group_cache[group_name] = Group.objects.get(name=group_name)
                    except Group.DoesNotExist:
                        if verbosity >= 1:
                            self.stdout.write(self.style.WARNING(
                                f'  [WARN] 组 "{group_name}" 不存在，'
                                f'请先运行 init_permissions（不含 --assign-users）'
                            ))
                        continue
                group = group_cache[group_name]

                if group in user.groups.all():
                    if verbosity >= 2:
                        self.stdout.write(f'  . {user.username} 已在组 {group_name} 中')
                    continue

                assign_log.append((user.username, user.user_type_id, group_name))
                if not dry_run:
                    user.groups.add(group)

        if assign_log:
            self.stdout.write(self.style.MIGRATE_HEADING('\n-- 用户归组'))
            current_user = None
            for username, role_code, group_name in assign_log:
                if username != current_user:
                    current_user = username
                    self.stdout.write(f'  {username} ({role_code})')
                self.stdout.write(f'    -> {group_name}')
            summary = (f'\n用户归组: {len(set(u for u, _, _ in assign_log))} 人 / '
                       f'{len(assign_log)} 条分配')
            if dry_run:
                self.stdout.write(self.style.WARNING(summary + ' (预览)'))
            else:
                self.stdout.write(self.style.SUCCESS(summary))
        else:
            self.stdout.write('\n用户归组: 无需变更')
