# apps/projects/mixins.py
from django.core.exceptions import PermissionDenied
from django.db.models import Q


class ProjectPermissionMixin:
    """
    权限控制混入类：统一管理行级权限
    """

    # --- 功能 1：给列表页用 (过滤 QuerySet) ---
    def get_permitted_queryset(self, queryset):
        """
        传入一个 Project 的 QuerySet，
        返回当前用户有权查看的 QuerySet。
        """
        user = self.request.user

        # 1. 超级管理员：看所有，不做过滤
        if user.is_superuser:
            return queryset

        # 2. 普通用户：只保留自己的 + 同组的
        # 注意：这里使用了 distinct() 去重
        my_groups = user.groups.all()
        return queryset.filter(
            Q(manager=user) |
            Q(manager__groups__in=my_groups)
        ).distinct()

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
