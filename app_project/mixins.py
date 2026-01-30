# apps/projects/mixins.py
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.contrib.auth.models import Permission


class ProjectPermissionMixin:
    """
    权限控制混入类：统一管理行级权限
    
    核心逻辑：
    1. 超级管理员：拥有所有权限。
    2. 个人权限：用户可以访问自己负责的项目。
    3. 组权限：用户可以访问同组其他成员负责的项目，但前提是该组必须拥有 'app_project.view_project' 权限。
       这避免了非项目相关的组（如行政组、研发组）成员之间意外获得项目访问权。
    """

    def _get_valid_groups(self, user):
        """
        获取用户所属的、且拥有 'app_project.view_project' 权限的组。
        """
        # 获取 'app_project.view_project' 权限对象
        try:
            perm = Permission.objects.get(content_type__app_label='app_project', codename='view_project')
        except Permission.DoesNotExist:
            return user.groups.none()

        # 筛选用户所在的组，且该组拥有 view_project 权限
        return user.groups.filter(permissions=perm)

    # --- 功能 1：给列表页用 (过滤 QuerySet) ---
    def get_permitted_queryset(self, queryset, manager_field='manager'):
        """
        传入一个 QuerySet，返回当前用户有权查看的 QuerySet。
        :param queryset: 待过滤的查询集
        :param manager_field: 指向 User 模型的字段名 (例如 'manager' 或 'project__manager')
        """
        user = self.request.user

        # 1. 超级管理员：看所有，不做过滤
        if user.is_superuser:
            return queryset

        # 2. 获取有效的组 (即拥有 view_project 权限的组)
        valid_groups = self._get_valid_groups(user)

        # 3. 构造查询条件
        # A. 自己负责的项目
        q_self = Q(**{manager_field: user})
        
        # B. 同组(有效组)成员负责的项目
        # 逻辑：项目的负责人的组 必须在 我的有效组 之中
        # 注意：这里我们反向思考，只要项目的负责人属于 valid_groups 中的任何一个，我就能看
        if valid_groups.exists():
            q_group = Q(**{f"{manager_field}__groups__in": valid_groups})
            return queryset.filter(q_self | q_group).distinct()
        else:
            # 如果我没有任何有效组，只能看自己的
            return queryset.filter(q_self).distinct()

    # --- 功能 2：给详情/操作页用 (检查单个对象) ---
    def check_project_permission(self, project):
        """
        检查当前用户是否有权操作指定的 project 对象。
        """
        user = self.request.user

        # 1. 超级管理员
        if user.is_superuser:
            return True

        # 2. 自己是负责人
        if project.manager == user:
            return True

        # 3. 检查组权限
        # 获取我的有效组
        valid_groups = self._get_valid_groups(user)
        
        if not valid_groups.exists():
            raise PermissionDenied("您没有权限操作此项目。")

        # 获取项目负责人所属的所有组 ID
        manager_group_ids = project.manager.groups.values_list('id', flat=True)
        
        # 检查是否有交集：我的有效组 ID 是否在项目负责人的组 ID 中
        # filter(id__in=...) 会生成 SQL: WHERE id IN (...)
        if valid_groups.filter(id__in=manager_group_ids).exists():
            return True

        raise PermissionDenied("您没有权限操作此项目。")
