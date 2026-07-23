"""菜单服务模块。负责菜单组装、角色过滤和 URL 解析。

菜单数据从 SidebarModule / SidebarSubItem (DB) 动态读取，
替代原 menu_modules.py 的硬编码 MenuModule 静态方法。

导出: MenuService。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 调用链路
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  context_processors/menu_processor.py
      └─ sidebar_menu_permissions(request)
           └─ MenuService.get_user_menu(request)
                ├─ SidebarModule (DB)           ← 菜单模块定义
                ├─ L1 角色白名单过滤             ← 通过 ModuleAccessConfig 动态解析
                └─ _process_module()
                     ├─ _check_sub_item_visibility()  ← 子菜单 L1/L2/L3 过滤
                     ├─ reverse(url_name)              ← URL 解析
                     └─ is_active / is_expanded        ← 状态计算

  最终输出注入模板上下文 dynamic_sidebar，由 sidebar.html 渲染。
"""

from django.urls import reverse, NoReverseMatch


class MenuService:
    """模块化菜单服务：从 DB 读取菜单定义并做运行时权限过滤。

    三层子菜单可见性控制（由 _check_sub_item_visibility 执行）：
        L1  visible_to   — 角色白名单（通过 ModuleAccessConfig 动态解析）
        L2  min_level    — 用户等级门槛（未声明 → 不检查）
        L3  permissions  — Django 原生权限码（未声明 → 不检查）
    """

    @classmethod
    def get_user_menu(cls, request):
        """按用户角色过滤并组装菜单树。

        Args:
            request: HttpRequest — 用于获取 user 和 resolver_match。
        Returns:
            list[dict]: 处理后的菜单模块列表，可直接供模板渲染。
        """
        user = request.user
        if not user.is_authenticated:
            return []

        current_url_name = request.resolver_match.view_name if request.resolver_match else ""

        # 从 DB 读取启用的菜单模块
        try:
            from app_user.models import SidebarModule
            raw_modules = list(
                SidebarModule.objects.filter(is_active=True)
                .select_related('module_access')
                .prefetch_related('sub_items')
                .order_by('sort_order')
            )
        except Exception:
            # DB 表尚未创建（migration 未执行）
            return []

        from app_user.services.identity_service import IdentityService

        filtered_menu = []
        for mod in raw_modules:
            # 解析 L1 角色白名单 — 通过 module_access → ModuleAccessConfig → role_groups
            if mod.module_access:
                role_codes = IdentityService.get_module_role_codes(mod.module_access.module_code)
            else:
                role_codes = []  # 无关联权限配置 → 仅超管可见

            # 超级用户绕过，否则 user_type_id 必须在 role_codes 中
            if user.is_superuser or user.user_type_id in role_codes:
                processed_mod = cls._process_module(mod, role_codes, current_url_name, user)
                if processed_mod:
                    filtered_menu.append(processed_mod)

        return filtered_menu

    @classmethod
    def _check_sub_item_visibility(cls, sub_item, parent_role_codes, user):
        """校验单个子菜单项的可见性。

        L1 → L2 → L3 顺序短路执行。
        """
        if user.is_superuser:
            return True

        # L1: 子项声明了 role_group 则用自身的；否则继承父模块
        if sub_item.role_group_id:
            from app_user.services.identity_service import IdentityService
            role_codes = IdentityService.get_role_codes(sub_item.role_group.code)
            if user.user_type_id not in role_codes:
                return False

        # L2: 用户等级门槛
        if sub_item.min_level is not None and user.user_level < sub_item.min_level:
            return False

        # L3: Django 原生权限码
        if sub_item.permissions and not user.has_perms(sub_item.permissions):
            return False

        return True

    @classmethod
    def _process_module(cls, mod, parent_role_codes, current_url_name, user):
        """处理单个模块：URL 解析 → 子菜单过滤 → 激活状态计算。"""
        try:
            url = reverse(mod.url_name)

            subs = []
            is_any_child_active = False
            for sub in mod.sub_items.filter(is_active=True).order_by('sort_order'):
                if not cls._check_sub_item_visibility(sub, parent_role_codes, user):
                    continue

                try:
                    sub_url = reverse(sub.url_name)
                    is_active = (current_url_name == sub.url_name)
                    if is_active:
                        is_any_child_active = True

                    subs.append({
                        'name': sub.name,
                        'url': sub_url,
                        'is_active': is_active,
                    })
                except NoReverseMatch:
                    continue

            if not subs:
                return None

            is_active = (current_url_name == mod.url_name) or is_any_child_active

            return {
                'name': mod.name,
                'icon': mod.icon,
                'url': url,
                'sub_items': subs,
                'is_active': is_active,
                'is_expanded': is_any_child_active,
            }
        except NoReverseMatch:
            return None
