from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from .models import User

class IdentityConfig:
    """
    业务逻辑分组 (权限集定义)。
    通过在这里定义分组，实现视图层代码的低耦合。
    """
    R_ENGINEER = User.UserType.ENGINEER
    R_PROCESS = User.UserType.PROCESS_ENGINEER
    R_SALES = User.UserType.SALES
    R_PURCHASING = User.UserType.PURCHASING
    R_ADMIN = User.UserType.ADMIN

    # 技术核心：涉及研发、工艺、配方的全员
    TECH_CORE = [R_ENGINEER, R_PROCESS, R_ADMIN]
    
    # 纯技术研发
    RND_ONLY = [R_ENGINEER, R_ADMIN]
    
    # 纯工艺工程
    PROCESS_ONLY = [R_PROCESS, R_ADMIN]

    # 供应链/采购核心
    SUPPLY_CHAIN = [R_PURCHASING, R_ADMIN]

    # 内部全员 (包含采购)
    INTERNAL_STAFF = [R_ENGINEER, R_PROCESS, R_SALES, R_PURCHASING, R_ADMIN]


class UnifiedAccessMixin(PermissionRequiredMixin):
    """
    统一权限架构控制 Mixin (4D-Security-Logic)。
    """
    # 维度1：负责人关联字段名列表
    user_link_fields = ['manager', 'creator', 'user', 'owner', 'uploader', 'salesperson']
    
    # 维度2：最低用户等级要求
    min_level_required = 1
    
    # 维度3：部门隔离开关
    enforce_dept_isolation = True

    # 维度4：允许访问的角色组 (使用 IdentityConfig 中的分组)
    identity_required = []

    def has_permission(self):
        """核心判定引擎"""
        user = self.request.user

        if not user.is_authenticated: return False
        if user.is_superuser: return True

        # Django 原生权限 (Dim: Perms)
        if not super().has_permission(): return False

        # 用户等级 (Dim: Level)
        if user.user_level < self.min_level_required: return False

        # 角色判定 (Dim: Type)
        if self.identity_required and user.user_type not in self.identity_required:
            return False

        return True

    def get_queryset(self):
        """数据范围过滤引擎"""
        user = self.request.user
        
        # 1. 自动获取 QuerySet (容错处理)
        if hasattr(self, 'queryset') and self.queryset is not None:
            qs = self.queryset.all()
        elif hasattr(self, 'model') and self.model is not None:
            qs = self.model.objects.all()
        else:
            # 【修复】对于没有定义 model/queryset 的原生 View，返回 None 是危险的
            # 此处应返回对应的 model.objects.all() 或抛出配置异常提醒开发者
            return None

        if user.is_superuser: return qs

        # 2. 执行部门隔离
        if self.enforce_dept_isolation:
            user_field = self._detect_user_link_field(qs.model)
            if user_field:
                if user.department:
                    return qs.filter(**{f"{user_field}__department": user.department})
                return qs.filter(**{user_field: user})
        return qs

    def _detect_user_link_field(self, model):
        """探测模型实际存在的关联字段"""
        model_fields = [f.name for f in model._meta.get_fields()]
        for field in self.user_link_fields:
            if field in model_fields: return field
        return None

    def check_object_permission(self, obj):
        """对象级细分控制"""
        user = self.request.user
        if user.is_superuser: return True

        owner = None
        for attr in self.user_link_fields:
            if hasattr(obj, attr):
                owner = getattr(obj, attr)
                if owner: break

        if not owner: return True 

        is_owner = (owner == user)
        is_same_dept = user.department and getattr(owner, 'department', None) == user.department

        if not (is_owner or is_same_dept):
            raise PermissionDenied("您的账号无权操作其他部门的数据资产")
        return True
