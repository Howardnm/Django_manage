"""菜单服务模块。负责菜单组装、角色过滤和 URL 解析。

导出: MenuService。
"""

from django.urls import reverse, NoReverseMatch
from .menu_modules import MenuModule

class MenuService:
    """
    模块化菜单服务：负责菜单的组装、过滤和状态计算。
    """
    @classmethod
    def get_user_menu(cls, request):
        """按用户角色过滤并组装菜单树。Args: request: HttpRequest。Returns: 菜单模块字典列表。"""
        user = request.user
        if not user.is_authenticated:
            return []

        current_url_name = request.resolver_match.url_name if request.resolver_match else ""

        # 按照业务逻辑顺序组装模块
        # 每个模块现在都是一个独立的顶级菜单项
        raw_modules = [
            MenuModule.get_dashboard(),
            MenuModule.get_project(),
            MenuModule.get_repository(),
            MenuModule.get_basic_research(),
            MenuModule.get_material(),
            MenuModule.get_formula(),
            MenuModule.get_trial_production(),
            MenuModule.get_process(),
            MenuModule.get_raw_material(),
            MenuModule.get_form_management(),
            MenuModule.get_workflow(),
            MenuModule.get_admin(),
        ]

        filtered_menu = []
        for mod in raw_modules:
            if not mod: continue # 跳过空的模块定义
            
            # L1 角色白名单过滤：仅展示当前用户角色可见的菜单模块
            if user.is_superuser or user.user_type in mod['visible_to']:
                processed_mod = cls._process_module(mod, current_url_name)
                if processed_mod:
                    filtered_menu.append(processed_mod)
        
        return filtered_menu

    @classmethod
    def _process_module(cls, mod, current_url_name):
        """处理单个模块的 URL 转换和 Active 状态。

        Args: mod: 原始菜单模块字典。current_url_name: 当前请求的 URL name。
        Returns: 处理后的模块字典或 None。
        """
        try:
            # 基础 URL
            url = reverse(mod['url_name'])
            
            subs = []
            is_any_child_active = False
            for sub in mod.get('sub_items', []):
                try:
                    sub_url = reverse(sub['url_name'])
                    is_active = (current_url_name == sub['url_name'])
                    if is_active: is_any_child_active = True
                    
                    subs.append({
                        'name': sub['name'],
                        'url': sub_url,
                        'is_active': is_active
                    })
                except NoReverseMatch: continue

            # 顶级菜单激活判定：自身匹配 或 任意子项匹配
            is_active = (current_url_name == mod['url_name']) or is_any_child_active

            return {
                'name': mod['name'],
                'icon': mod['icon'],
                'url': url,
                'sub_items': subs,
                'is_active': is_active,
                'is_expanded': is_any_child_active # 只有子项激活时才强制展开
            }
        except NoReverseMatch:
            return None
