from django.urls import reverse, NoReverseMatch
from .menu_modules import MenuModule

class MenuService:
    """
    模块化菜单服务：负责菜单的组装、过滤和状态计算。
    """
    @classmethod
    def get_user_menu(cls, request):
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
            MenuModule.get_workflow(),
            MenuModule.get_form_management(),
            MenuModule.get_admin(),
        ]

        filtered_menu = []
        for mod in raw_modules:
            if not mod: continue # 跳过空的模块定义
            
            # 执行 4D 权限准入检查
            if user.is_superuser or user.user_type in mod['visible_to']:
                processed_mod = cls._process_module(mod, current_url_name)
                if processed_mod:
                    filtered_menu.append(processed_mod)
        
        return filtered_menu

    @classmethod
    def _process_module(cls, mod, current_url_name):
        """处理单个模块的 URL 转换和 Active 状态"""
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
