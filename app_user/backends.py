from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

UserModel = get_user_model()

class EmailBackend(ModelBackend):
    """
    允许使用邮箱登录
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            # 尝试通过邮箱获取用户
            user = UserModel.objects.get(email=username)
        except UserModel.DoesNotExist:
            # 如果找不到，也可以尝试通过用户名查找 (可选，为了兼容性可以保留)
            try:
                user = UserModel.objects.get(username=username)
            except UserModel.DoesNotExist:
                return None
        
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None