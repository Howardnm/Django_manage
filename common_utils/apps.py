"""
通用工具组件 AppConfig。

在 ready() 中注册内置模型类型（django.contrib.auth.User），
各业务 app 在各自的 AppConfig.ready() 中注册自己的模型类型。
"""

from django.apps import AppConfig


class CommonUtilsConfig(AppConfig):
    """通用工具组件 — 提供跨 app 复用的表单、筛选、搜索、状态机等基础设施。"""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'common_utils'
    verbose_name = '通用工具组件'

    def ready(self):
        """注册内置模型类型的自动补全处理器。"""
        from common_utils.autocomplete_registry import register_autocomplete
        from django.contrib.auth import get_user_model
        from django.db.models import Q

        User = get_user_model()

        register_autocomplete('user',
            lambda q: User.objects.only('pk', 'username', 'first_name').filter(
                is_active=True,
            ).filter(Q(username__icontains=q) | Q(first_name__icontains=q)),
            lambda u: {'value': u.pk, 'text': f'{u.first_name or u.username}'},
        )
