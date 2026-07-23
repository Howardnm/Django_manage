"""app_formula 上下文处理器。提供配方模块相关的模板变量。"""

from app_formula.mixins import FormulaAccessMixin
from app_user.services.identity_service import IdentityService


def formula_permissions(request):
    """注入配方模块权限变量到模板上下文。

    复用 FormulaAccessMixin.module_code 的动态角色配置，
    避免在模板或别处硬编码角色码。
    """
    if not request.user.is_authenticated:
        return {}
    if request.user.is_superuser:
        return {'can_use_compare_cart': True}
    role_codes = IdentityService.get_module_role_codes(FormulaAccessMixin.module_code)
    return {'can_use_compare_cart': request.user.user_type_id in role_codes}
