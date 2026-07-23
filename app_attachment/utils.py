"""
权限适配器

从 AttachmentConfig 中读取 access_mixin 配置，
实例化并调用对应的 4D 权限检查方法。

支持：
- identity_required 角色身份检查
- user_level 等级检查
- Django 原生权限码检查
- 对象级权限检查（L4 部门隔离 + L5 工作组隔离）
- permission_parent_chain 权限穿透链
"""
from django.core.exceptions import PermissionDenied


class PermissionAdapter:
    """
    权限适配器。

    根据 AttachmentConfig 中声明的 access_mixin，
    对附件的父对象执行完整的 4D 权限校验。

    Usage:
        adapter = PermissionAdapter(config)
        adapter.check(request, parent_obj, action='view')
    """

    def __init__(self, config):
        """
        Args:
            config: AttachmentConfig 实例
        """
        self.config = config

    def check(self, request, parent_obj, action='view'):
        """
        执行完整的 4D 权限校验。

        Args:
            request: Django HttpRequest
            parent_obj: 附件的直接父对象
            action: 'view' | 'add' | 'delete'

        Returns:
            True 如果通过

        Raises:
            PermissionDenied: 权限不足时抛出
        """
        user = request.user
        if not user.is_authenticated:
            raise PermissionDenied("请先登录")
        if user.is_superuser:
            return True

        # ---- Step 1: 沿 permission_parent_chain 解析权限承载对象 ----
        permission_obj = parent_obj
        if self.config.permission_parent_chain:
            for attr in self.config.permission_parent_chain.split('.'):
                permission_obj = getattr(permission_obj, attr, None)
                if permission_obj is None:
                    raise ValueError(
                        f"权限链断裂: '{self.config.permission_parent_chain}' "
                        f"在 '{attr}' 处为 None，父对象类型为 "
                        f"{type(parent_obj).__name__}"
                    )

        # ---- Step 2: 实例化 Mixin 并设置 request ----
        mixin = self.config.access_mixin()
        mixin.request = request

        # ---- Step 3: 身份角色检查 (L1) — 从 _resolve_config() 动态读取 ----
        cfg = mixin._resolve_config()
        if cfg['role_codes'] and user.user_type_id not in cfg['role_codes']:
            raise PermissionDenied("您的角色无权访问此附件")

        # ---- Step 4: 用户等级检查 (L2) ——
        if user.user_level < cfg['min_level']:
            raise PermissionDenied("您的账号等级不足，无法访问此附件")

        # ---- Step 5: Django 原生权限码检查 ----
        perm_map = {
            'view': self.config.view_permission,
            'add': self.config.add_permission,
            'delete': self.config.delete_permission,
        }
        required_perm = perm_map.get(action)
        if required_perm and not user.has_perm(required_perm):
            raise PermissionDenied(
                f"您没有{'查看' if action == 'view' else '上传' if action == 'add' else '删除'}此附件的权限"
            )

        # ---- Step 6: 对象级权限检查 (L4 部门隔离 + L5 工作组隔离) ----
        # 注意：check_object_permission 内部会 raise PermissionDenied
        mixin.check_object_permission(permission_obj)

        return True
