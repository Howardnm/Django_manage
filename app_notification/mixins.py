from app_user.mixins import UnifiedAccessMixin, IdentityConfig

class NotificationAccessMixin(UnifiedAccessMixin):
    """
    通知模块权限管控。
    
    特点：
    1. 负责人识别：明确为 recipient (接收者)。
    2. 严格私有：关闭部门隔离，启用“本人隔离”。
    3. 准入：内部全员。
    """
    # 锁定负责人字段为接收者
    user_link_fields = ['recipient']
    
    # 内部全员准入
    identity_required = IdentityConfig.INTERNAL_STAFF
    
    # 通知是极度私有的，不按部门隔离，而是强制按本人隔离
    # 在 UnifiedAccessMixin 的逻辑中，如果没有部门或特殊设置，会自动退化为 manager=user
    enforce_dept_isolation = False

    def get_queryset(self):
        """确保用户只能看到发送给自己的通知"""
        return super().get_queryset().filter(recipient=self.request.user)
