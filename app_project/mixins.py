# apps/projects/mixins.py
from django.core.exceptions import PermissionDenied
from django.db.models import Q


class ProjectPermissionMixin:
    """
    权限控制混入类：统一管理行级权限
    """

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

        # 2. 普通用户：只保留自己的 + 同组的
        # 构造动态查询参数
        # Q(manager=user) -> Q(**{manager_field: user})
        # Q(manager__groups__in=my_groups) -> Q(**{f"{manager_field}__groups__in": my_groups})
        
        my_groups = user.groups.all()
        
        q_self = Q(**{manager_field: user})
        q_group = Q(**{f"{manager_field}__groups__in": my_groups})

        return queryset.filter(q_self | q_group).distinct()

    # --- 功能 2：给详情/操作页用 (检查单个对象) ---
    def check_project_permission(self, project):
        """
        检查当前用户是否有权操作指定的 project 对象。
        """
        user = self.request.user

        if user.is_superuser:
            return True

        if project.manager == user:
            return True

        # 这里的逻辑必须和 get_permitted_queryset 保持一致
        manager_groups = project.manager.groups.values_list('id', flat=True)
        if user.groups.filter(id__in=manager_groups).exists():
            return True

        raise PermissionDenied("您没有权限操作此项目。")
