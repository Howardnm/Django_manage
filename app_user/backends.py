"""自定义认证后端。管理系统用工号登录，外部接口仍用邮箱登录。

导出: EmployeeNoBackend, EmailBackend。"""
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

UserModel = get_user_model()


class EmployeeNoBackend(ModelBackend):
    """允许用户通过工号认证的后端。不接受用户名或邮箱。

    查找与 MCP JWT 的 employeeNo 一致：strip 后精确匹配，不转大小写。
    空工号直接失败，避免命中 employee_no 为 NULL 的账号。
    """
    def authenticate(self, request, employee_no=None, password=None, **kwargs):
        """通过工号认证用户。Args: request: HttpRequest 或 None。employee_no: 工号字符串。password: 明文密码。Returns: User 实例（凭证有效）或 None。"""
        employee_no = (employee_no or '').strip()
        if not employee_no:
            return None
        try:
            user = UserModel.objects.get(employee_no=employee_no)
        except UserModel.DoesNotExist:
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None


class EmailBackend(ModelBackend):
    """允许用户通过邮箱（大小写不敏感）进行认证的后端。不再支持用户名登录。

    Django 的 authenticate() 会把调用方传入的 kwargs 原样透传给后端，因此后端
    参数名直接命名为 email，与登录表单统一，避免复用 username 造成混淆。
    """
    def authenticate(self, request, email=None, password=None, **kwargs):
        """通过邮箱认证用户。Args: request: HttpRequest 或 None。email: 邮箱字符串。password: 明文密码。Returns: User 实例（凭证有效）或 None。"""
        email = (email or '').strip().lower()
        if not email:
            return None
        try:
            user = UserModel.objects.get(email=email)
        except UserModel.DoesNotExist:
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None