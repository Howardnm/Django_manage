from django.core.exceptions import PermissionDenied
from django.db.models import Q
from app_user.mixins import UnifiedAccessMixin, IdentityConfig

class RepositoryAccessMixin(UnifiedAccessMixin):
    """
    档案中心权限管控 (双重负责制适配)。
    """
    
    user_link_fields = ['salesperson', 'project__manager']
    identity_required = IdentityConfig.INTERNAL_STAFF
    
    # 默认开启隔离，但在具体视图中（如客户名录）可手动关闭
    enforce_dept_isolation = True

    def get_queryset(self):
        """
        实现"业务部"与"研发部"的双重部门隔离并集。
        自动探测模型是否支持该过滤逻辑。
        """
        user = self.request.user
        
        # 1. 获取模型
        if hasattr(self, 'model') and self.model:
            model = self.model
        elif hasattr(self, 'queryset') and self.queryset is not None:
            model = self.queryset.model
        else:
            return super().get_queryset()

        # 2. 核心探测：如果模型不包含 salesperson 字段，则跳过自定义的复杂隔离逻辑
        # 转而使用基类的默认逻辑或直接返回全集
        fields = [f.name for f in model._meta.get_fields()]
        if 'salesperson' not in fields:
            # 这种情况通常是 Customer 或 OEM 公司名录，属于公共资源
            return model.objects.all()

        if user.is_superuser:
            return model.objects.all()

        # 3. 执行 ProjectRepository 专属的"双重负责"隔离
        if self.enforce_dept_isolation:
            if user.department:
                return model.objects.filter(
                    Q(salesperson__department=user.department) | 
                    Q(project__manager__department=user.department)
                ).distinct()
            else:
                return model.objects.filter(
                    Q(salesperson=user) | 
                    Q(project__manager=user)
                ).distinct()
        
        return model.objects.all()

    def check_object_permission(self, obj):
        """对象级细分控制：同样增加字段探测逻辑"""
        user = self.request.user
        if user.is_superuser: return True

        # 如果是 Customer 或 OEM 对象，不进行"负责人"校验（因为公司级对象没有单一负责人）
        if not hasattr(obj, 'salesperson'):
            return True

        # 针对 ProjectRepository 的校验
        is_sales_dept = user.department and getattr(obj.salesperson, 'department', None) == user.department
        is_sales_owner = (obj.salesperson == user)

        project = getattr(obj, 'project', None)
        if project:
            is_rnd_dept = user.department and getattr(project.manager, 'department', None) == user.department
            is_rnd_owner = (project.manager == user)
        else:
            is_rnd_dept = is_rnd_owner = False

        if not (is_sales_owner or is_sales_dept or is_rnd_owner or is_rnd_dept):
            raise PermissionDenied("您的账号无权操作该档案（跨部门保护中）")
        
        return True
