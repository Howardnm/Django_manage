from django.core.exceptions import PermissionDenied
from django.db.models import Q
from app_user.mixins import UnifiedAccessMixin, IdentityConfig
from app_user.models import User

class ProjectAccessMixin(UnifiedAccessMixin):
    """
    项目模块专用的权限管控类。

    1. 负责人识别：manager。
    2. 协同穿透：支持 ProjectMember 访问（查看）。
    3. 准入规则：支持内部全员 (INTERNAL_STAFF)。
    4. L5 工作组隔离：仅同组可查看项目。
    5. 编辑权限：仅项目负责人可编辑（继承自基类 check_edit_permission）。
    """

    # 明确定义项目模块的负责人字段名
    user_link_fields = ['manager']

    # 使用重构后的分组，确保工艺工程师也能进入项目模块
    identity_required = IdentityConfig.INTERNAL_STAFF

    # ── 开启 L5 工作组隔离 ──
    enforce_group_isolation = True

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


class PerformanceManagementMixin(ProjectAccessMixin):
    """
    绩效管理写操作权限 Mixin（创建/编辑/删除）。

    仅限高职级人员操作评分规则（预设高级经理级别 Lv.15）。
    规则为全局配置，不区分部门。
    """
    min_level_required = 15
    enforce_dept_isolation = False


class PerformanceRuleReadMixin(ProjectAccessMixin):
    """
    绩效规则查看权限 Mixin（列表/详情）。

    开放给研发工程师和业务经理查看评分规则。
    规则为全局配置，不区分部门。
    """
    identity_required = [User.UserType.ENGINEER, User.UserType.SALES, User.UserType.ADMIN]
    enforce_dept_isolation = False


class SharedConfigMixin(ProjectAccessMixin):
    """
    全局配置表权限 Mixin（不合格原因、客户意见类型等）。

    配置表为组织级共享资源，无数据所有者，部门内所有内部员工均可编辑。
    关闭部门/工作组隔离，仅靠 L1（内部全员）+ L3（权限码）准入控制。
    """
    enforce_dept_isolation = False
    enforce_group_isolation = False
