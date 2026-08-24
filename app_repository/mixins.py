from django.core.exceptions import PermissionDenied
from django.db.models import Q
from app_user.mixins import UnifiedAccessMixin
from app_project.mixins import ProjectAccessMixin

class RepositoryAccessMixin(UnifiedAccessMixin):
    """档案中心权限管控 (双重负责制适配)。

    L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取。
    """

    module_code = 'repository'
    module_name = '客户档案中心'
    module_description = '客户档案中心。双重负责制：业务部(salesperson) OR 研发部(project.manager)。'
    user_link_fields = ['salesperson', 'project__manager']

    def get_queryset(self):
        """
        逻辑 = (L4/L5 部门/工作组隔离结果) AND 在此基础上叠加双重负责制过滤。
        自动探测模型是否支持 salesperson 字段，不支持则直接返回基类结果。
        """
        user = self.request.user
        qs = super().get_queryset()  # 先获取基类 L4/L5 隔离后的查询集

        if qs is None:
            return None

        if user.is_superuser:
            return qs

        # 探测模型是否包含 salesperson 字段，以决定是否执行双重负责制过滤
        if not hasattr(qs.model, 'salesperson'):
            return qs

        # 双重负责制：业务部（salesperson 所属部门）OR 研发部（project.manager 所属部门）
        if self._resolve_config()['enforce_dept_isolation']:
            if user.department:
                return qs.filter(
                    Q(salesperson__department=user.department) |
                    Q(project__manager__department=user.department)
                ).distinct()
            else:
                return qs.filter(
                    Q(salesperson=user) |
                    Q(project__manager=user)
                ).distinct()

        return qs

    def check_object_permission(self, obj):
        """
        对象级检查：
        逻辑 = 基类标准化检查 OR 双重负责制穿透
        """
        user = self.request.user
        if user.is_superuser:
            return True

        # 1. 调用基类的标准化检查（owner 等价 + L4/L5 部门/工作组）
        try:
            return super().check_object_permission(obj)
        except PermissionDenied:
            pass  # 基类不通过，尝试双重负责制备选

        # 2. 备选：双重负责制穿透检查
        if not hasattr(obj, 'salesperson'):
            # 没有 salesperson 字段的对象，无法走双重负责制逻辑，直接拒绝
            raise PermissionDenied("您的账号无权操作该档案（无法匹配双重负责制）")

        is_sales_dept = (
            user.department
            and getattr(obj.salesperson, 'department', None) == user.department
        )
        is_sales_owner = (obj.salesperson == user)

        project = getattr(obj, 'project', None)
        if project:
            is_rnd_dept = (
                user.department
                and getattr(project.manager, 'department', None) == user.department
            )
            is_rnd_owner = (project.manager == user)
        else:
            is_rnd_dept = is_rnd_owner = False

        if not (is_sales_owner or is_sales_dept or is_rnd_owner or is_rnd_dept):
            raise PermissionDenied("您的账号无权操作该档案（跨部门保护中）")

        return True


class ProjectRepositoryFileAccessMixin(ProjectAccessMixin):
    """项目仓库附件权限（按项目访问 + 写操作仅限负责人）。

    查看/下载：沿用 ProjectAccessMixin 的项目访问（负责人 + 协同/销售成员）。
    上传/删除：仅项目负责人（obj.manager）可执行。
    依赖 PermissionAdapter 在调用前注入 self.action（'view' | 'add' | 'delete'）。
    """

    def check_object_permission(self, obj):
        user = self.request.user
        if user.is_superuser:
            return True

        action = getattr(self, 'action', 'view')
        if action in ('add', 'delete'):
            if getattr(obj, 'manager', None) != user:
                raise PermissionDenied("仅项目负责人可上传/删除该附件")
            return True

        return super().check_object_permission(obj)
