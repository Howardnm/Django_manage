from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied
from .models import User

class IdentityConfig:
    """
    权限对象模块化配置中心。
    通过定义“角色组”来实现权限逻辑与业务代码的解耦。
    后续增加角色时，只需在此处更新分组定义即可。
    """
    
    # 1. 基础角色定义 (直接映射 Model)
    R_ENGINEER = User.UserType.ENGINEER
    R_SALES = User.UserType.SALES
    R_CUSTOMER = User.UserType.CUSTOMER
    R_OEM = User.UserType.OEM
    R_ADMIN = User.UserType.ADMIN

    # 2. 逻辑分组 (权限集)
    # 内部员工：拥有进入后台管理和查看敏感技术/商务数据的权限
    INTERNAL_STAFF = [R_ENGINEER, R_SALES, R_ADMIN]
    
    # 技术核心：仅限涉及研发、工艺、配方的技术人员
    TECH_CORE = [R_ENGINEER, R_ADMIN]
    
    # 商务核心：仅限涉及客户、报价、档案的商务人员
    BUSINESS_CORE = [R_SALES, R_ADMIN]
    
    # 外部人员：受限访问，通常仅限查看手册和关联项目
    EXTERNAL_USERS = [R_CUSTOMER, R_OEM]


class IdentityMixin(AccessMixin):
    """
    对象模块化设计的权限控制 Mixin。
    用法示例：
    class MyView(IdentityMixin, View):
        # 场景A：仅限内部员工
        identity_required = IdentityConfig.INTERNAL_STAFF
        
        # 场景B：仅限研发
        identity_required = [IdentityConfig.R_ENGINEER]
    """
    
    # 必填属性：设置允许访问的角色组（参考 IdentityConfig 中的定义）
    # 默认为空，表示仅需登录，不限制具体角色
    identity_required = []
    
    # 是否强制校验超级管理员
    must_be_superuser = False

    def dispatch(self, request, *args, **kwargs):
        # 1. 基础鉴权：是否登录
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        # 2. 超级管理员特殊通行证
        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)

        # 3. 强制超管逻辑检查
        if self.must_be_superuser:
            raise PermissionDenied("此操作仅限系统管理员")

        # 4. 角色组校验逻辑
        if self.identity_required:
            if request.user.user_type not in self.identity_required:
                raise PermissionDenied(f"权限不足：该功能仅限 {self._get_role_names()} 访问")

        return super().dispatch(request, *args, **kwargs)

    def _get_role_names(self):
        """内部方法：解析角色代码为人类可读的名称，用于错误提示"""
        all_choices = dict(User.UserType.choices)
        return "、".join([all_choices.get(role, role) for role in self.identity_required])

    # --- 便捷属性扩展 (可在子类逻辑中直接使用) ---

    @property
    def is_internal(self):
        return self.request.user.user_type in IdentityConfig.INTERNAL_STAFF

    @property
    def is_tech(self):
        return self.request.user.user_type in IdentityConfig.TECH_CORE

    @property
    def is_business(self):
        return self.request.user.user_type in IdentityConfig.BUSINESS_CORE

    @property
    def is_external(self):
        return self.request.user.user_type in IdentityConfig.EXTERNAL_USERS
