from django.contrib.auth.mixins import PermissionRequiredMixin
from django.conf import settings
from django.shortcuts import redirect

class CustomPermissionRequiredMixin(PermissionRequiredMixin):
    """
    自定义权限混入类，当用户没有权限时，重定向到 settings.PERM_DENIED_URL。
    """
    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            # 如果用户已认证但没有权限，重定向到自定义的无权限页面
            return redirect(settings.PERM_DENIED_URL)
        # 如果用户未认证，则重定向到登录页面
        return super().handle_no_permission()
