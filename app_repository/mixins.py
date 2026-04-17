from django.core.exceptions import PermissionDenied
from django.db.models import Q
from app_user.mixins import UnifiedAccessMixin, IdentityConfig

class RepositoryAccessMixin(UnifiedAccessMixin):
    """
    档案中心权限管控 (双重负责制适配)。
    
    特点：
    1. 负责人识别：salesperson (业务) 和 project__manager (研发)。
    2. 穿透可见：内部全员 (INTERNAL_STAFF) 准入，但仅限本部门相关档案。
    """
    
    user_link_fields = ['salesperson', 'project__manager']
    
    # 使用对象化分组：支持研发、工艺、销售
    identity_required = IdentityConfig.INTERNAL_STAFF
    
    enforce_dept_isolation = True

    def get_queryset(self):
        """实现“业务部”与“研发部”的双重部门隔离并集"""
        user = self.request.user
        qs = super().get_queryset()

        if user.is_superuser:
            return qs

        if self.enforce_dept_isolation:
            if user.department:
                return qs.model.objects.filter(
                    Q(salesperson__department=user.department) | 
                    Q(project__manager__department=user.department)
                ).distinct()
            else:
                return qs.model.objects.filter(
                    Q(salesperson=user) | 
                    Q(project__manager=user)
                ).distinct()
        
        return qs

    def check_object_permission(self, obj):
        user = self.request.user
        if user.is_superuser:
            return True

        # 1. 业务端检查
        is_sales_dept = user.department and getattr(obj.salesperson, 'department', None) == user.department
        is_sales_owner = (obj.salesperson == user)

        # 2. 研发端检查
        project = getattr(obj, 'project', None)
        if project:
            is_rnd_dept = user.department and getattr(project.manager, 'department', None) == user.department
            is_rnd_owner = (project.manager == user)
        else:
            is_rnd_dept = is_rnd_owner = False

        if not (is_sales_owner or is_sales_dept or is_rnd_owner or is_rnd_dept):
            raise PermissionDenied("您的账号无权操作该档案（跨部门保护中）")
        
        return True
