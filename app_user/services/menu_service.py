"""菜单服务模块。负责菜单组装、角色过滤和 URL 解析。

导出: MenuService。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 调用链路
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  context_processors/menu_processor.py
      └─ sidebar_menu_permissions(request)
           └─ MenuService.get_user_menu(request)
                ├─ MenuModule.get_*() × 12    ← 获取原始模块定义
                ├─ L1 角色白名单过滤           ← 模块级 visible_to
                └─ _process_module()
                     ├─ _check_sub_item_visibility()  ← 子菜单 L1/L2/L3 过滤
                     ├─ reverse(url_name)              ← URL 解析
                     └─ is_active / is_expanded        ← 状态计算

  最终输出注入模板上下文 dynamic_sidebar，由 sidebar.html 渲染。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 过滤后输出的模块字典结构
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  {
      "name":        str,        # 模块显示名称
      "icon":        str,        # Tabler Icons 图标类名
      "url":         str,        # reverse() 解析后的实际 URL
      "sub_items":   list[{      # 过滤后的子菜单列表
          "name":      str,
          "url":       str,
          "is_active": bool,     # 当前页面是否匹配此子项
      }],
      "is_active":   bool,       # 模块本身或其子项是否处于激活状态
      "is_expanded": bool,       # 折叠面板是否应展开（仅子项激活时为 True）
  }
"""

from django.urls import reverse, NoReverseMatch
from .menu_modules import MenuModule


class MenuService:
    """模块化菜单服务：负责菜单的组装、过滤和状态计算。

    三层子菜单可见性控制（由 _check_sub_item_visibility 执行）：
        L1  visible_to   — 角色白名单（未声明 → 继承父模块）
        L2  min_level    — 用户等级门槛（未声明 → 不检查）
        L3  permissions  — Django 原生权限码（未声明 → 不检查）

    数据结构约定详见 menu_modules.py 文件头注释。
    """

    @classmethod
    def get_user_menu(cls, request):
        """按用户角色过滤并组装菜单树。

        执行流程:
            1. 未登录 → 返回空列表
            2. 收集 12 个模块定义
            3. 逐模块做 L1 角色白名单过滤（超级用户绕过）
            4. 通过过滤的模块交给 _process_module() 处理子项

        Args:
            request: HttpRequest — 用于获取 user 和 resolver_match。
        Returns:
            list[dict]: 处理后的菜单模块列表，可直接供模板渲染。
        """
        user = request.user
        if not user.is_authenticated:
            return []

        # 使用 view_name 而非 url_name，以支持命名空间 URL（如 color_center:list）
        # url_name 对命名空间 URL 只返回短名（如 "list"），view_name 返回完整限定名
        current_url_name = request.resolver_match.view_name if request.resolver_match else ""

        # 按照业务逻辑顺序组装模块（顺序决定侧边栏显示顺序）
        raw_modules = [
            MenuModule.get_dashboard(),
            MenuModule.get_project(),
            MenuModule.get_repository(),
            MenuModule.get_basic_research(),
            MenuModule.get_material(),
            MenuModule.get_formula(),
            MenuModule.get_trial_production(),
            MenuModule.get_extrusion_production(),
            MenuModule.get_color_center(),
            MenuModule.get_mold_injection(),
            MenuModule.get_material_testing(),
            MenuModule.get_process(),
            MenuModule.get_raw_material(),
            MenuModule.get_form_management(),
            MenuModule.get_workflow(),
            MenuModule.get_admin(),
        ]

        filtered_menu = []
        for mod in raw_modules:
            if not mod:
                continue

            # L1 角色白名单过滤（模块级）：超级用户绕过，否则 user_type 必须在 visible_to 中
            if user.is_superuser or user.user_type in mod['visible_to']:
                processed_mod = cls._process_module(mod, current_url_name, user)
                if processed_mod:
                    filtered_menu.append(processed_mod)

        return filtered_menu

    @classmethod
    def _check_sub_item_visibility(cls, sub_item, parent_visible_to, user):
        """校验单个子菜单项的可见性。

        三层校验按 L1 → L2 → L3 顺序短路执行，任一层不通过即返回 False。

        各字段的缺省行为:
            visible_to  未声明 → 继承 parent_visible_to（父模块的角色白名单）
            min_level   未声明 → 跳过等级检查
            permissions 未声明 → 跳过权限码检查

        Args:
            sub_item: 子菜单定义字典（来自 menu_modules.py）。
            parent_visible_to: 父模块的 visible_to 列表，用于子项继承。
            user: 当前请求的用户对象（需有 user_type / user_level / has_perms）。
        Returns:
            bool: True = 可见，False = 应隐藏。
        """
        # 超级用户绕过所有三层检查
        if user.is_superuser:
            return True

        # ── L1: 角色白名单 ──
        # 子项声明了 visible_to 则使用自身的；否则继承父模块
        visible_to = sub_item.get('visible_to')
        if visible_to is not None:
            if user.user_type not in visible_to:
                return False

        # ── L2: 用户等级门槛 ──
        min_level = sub_item.get('min_level')
        if min_level is not None and user.user_level < min_level:
            return False

        # ── L3: Django 原生权限码 ──
        # has_perms 要求列表中所有权限码均通过才返回 True
        permissions = sub_item.get('permissions')
        if permissions and not user.has_perms(permissions):
            return False

        return True

    @classmethod
    def _process_module(cls, mod, current_url_name, user):
        """处理单个模块：URL 解析 → 子菜单过滤 → 激活状态计算。

        执行流程:
            1. reverse() 解析模块自身的 url_name（失败 → 返回 None）
            2. 遍历子项：
               a. _check_sub_item_visibility() 权限过滤
               b. reverse() 解析子项 URL（失败 → 跳过该子项）
               c. 计算 is_active 状态
            3. 若过滤后无子项 → 返回 None（自动隐藏空模块）
            4. 计算模块自身的 is_active / is_expanded

        Args:
            mod: 原始菜单模块字典（来自 menu_modules.py 的 get_*() 方法）。
            current_url_name: 当前请求的 URL name，用于激活状态判定。
            user: 当前用户对象，传递给 _check_sub_item_visibility()。
        Returns:
            dict | None: 处理后的模块字典（结构见文件头注释），或 None。
        """
        try:
            # 基础 URL
            url = reverse(mod['url_name'])
            parent_visible_to = mod['visible_to']

            subs = []
            is_any_child_active = False
            for sub in mod.get('sub_items', []):
                # 子菜单可见性过滤（L1 → L2 → L3）
                if not cls._check_sub_item_visibility(sub, parent_visible_to, user):
                    continue

                try:
                    sub_url = reverse(sub['url_name'])
                    is_active = (current_url_name == sub['url_name'])
                    if is_active:
                        is_any_child_active = True

                    subs.append({
                        'name': sub['name'],
                        'url': sub_url,
                        'is_active': is_active
                    })
                except NoReverseMatch:
                    continue

            # 若所有子项均被过滤（权限不足或 URL 不存在），隐藏整个模块
            if not subs:
                return None

            # 顶级菜单激活判定：自身 URL 匹配 或 任意子项匹配
            is_active = (current_url_name == mod['url_name']) or is_any_child_active

            return {
                'name': mod['name'],
                'icon': mod['icon'],
                'url': url,
                'sub_items': subs,
                'is_active': is_active,
                'is_expanded': is_any_child_active  # 只有子项激活时才强制展开折叠面板
            }
        except NoReverseMatch:
            return None
