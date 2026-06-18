from django.core.exceptions import PermissionDenied
from django.db.models import Q
from app_user.mixins import UnifiedAccessMixin, IdentityConfig

class ProjectAccessMixin(UnifiedAccessMixin):
    """
    项目模块专用的权限管控类。

    1. 负责人识别：manager。
    2. 协同穿透：支持 ProjectMember 访问。
    3. 准入规则：支持研发工程师、工艺工程师、业务经理、管理员 (INTERNAL_STAFF)。
    """

    # 明确定义项目模块的负责人字段名
    user_link_fields = ['manager']

    # 使用重构后的分组，确保工艺工程师也能进入项目模块
    identity_required = IdentityConfig.INTERNAL_STAFF

    def get_queryset(self):
        """
        重写查询集：
        逻辑 = (L4/L5 部门/工作组隔离结果) OR (我参与协同的项目)
        """
        user = self.request.user
        qs = super().get_queryset()  # 已处理：超管放行 + L4 部门 + L5 工作组

        if qs is None:
            return None

        # 检查模型是否具有协同成员关联 (members)
        if hasattr(qs.model, 'members'):
            member_q = Q(members__user=user)
            # 基类 L4/L5 结果 ∪ 协同成员穿透
            return (qs | qs.model.objects.filter(member_q)).distinct()

        return qs

    def check_object_permission(self, obj):
        """
        对象级检查：
        逻辑 = (负责人/同部门) OR (我参与协同)
        """
        user = self.request.user
        if user.is_superuser:
            return True

        # 1. 调用基类的标准化检查
        try:
            return super().check_object_permission(obj)
        except PermissionDenied:
            # 2. 备选：检查是否为该项目的协同成员
            if hasattr(obj, 'members'):
                if obj.members.filter(user=user).exists():
                    return True
            raise
