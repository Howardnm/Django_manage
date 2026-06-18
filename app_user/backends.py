"""自定义认证后端。支持邮箱或用户名登录。

导出: EmailBackend。"""
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

UserModel = get_user_model()

class EmailBackend(ModelBackend):
    """允许用户通过邮箱（优先）或用户名进行认证的后端。"""
    def authenticate(self, request, username=None, password=None, **kwargs):
        """通过邮箱或用户名认证用户。Args: request: HttpRequest 或 None。username: 邮箱或用户名字符串。password: 明文密码。Returns: User 实例（凭证有效）或 None。"""
        try:
            # 尝试通过邮箱获取用户
            user = UserModel.objects.get(email=username)
        except UserModel.DoesNotExist:
            # 如果找不到，也可以尝试通过用户名查找 (可选，为了兼容性可以保留)
            try:
                user = UserModel.objects.get(username=username)
            except UserModel.DoesNotExist:
                return None
        except UserModel.MultipleObjectsReturned:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None