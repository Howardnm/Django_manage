from app_user.services.menu_service import MenuService

def sidebar_menu_permissions(request):
    """
    上下文处理器：将计算好的动态菜单数据注入所有模板。
    """
    if not request.user.is_authenticated:
        return {'dynamic_sidebar': []}

    return {
        'dynamic_sidebar': MenuService.get_user_menu(request)
    }
