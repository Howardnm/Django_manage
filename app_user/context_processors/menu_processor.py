"""菜单上下文处理器。将动态侧边栏菜单注入所有模板上下文。

导出: sidebar_menu_permissions。
"""

from app_user.services.menu_service import MenuService

def sidebar_menu_permissions(request):
    """
    上下文处理器：将计算好的动态菜单数据注入所有模板。

    Args: request: HttpRequest。
    Returns: 包含 dynamic_sidebar 键的字典（未登录用户返回空列表）。
    """
    if not request.user.is_authenticated:
        return {'dynamic_sidebar': []}

    return {
        'dynamic_sidebar': MenuService.get_user_menu(request)
    }
