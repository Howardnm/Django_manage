from app_user.mixins import UnifiedAccessMixin

class NotificationAccessMixin(UnifiedAccessMixin):
    """通知模块权限管控。

    L1/L2/L4/L5 通过 module_code 从 ModuleAccessConfig (DB) 动态读取。
    """

    module_code = 'notification'
    user_link_fields = ['recipient']

    def get_queryset(self):
        """确保用户只能看到发送给自己的通知"""
        qs = super().get_queryset()
        if qs is None:
            return None
        return qs.filter(recipient=self.request.user)
