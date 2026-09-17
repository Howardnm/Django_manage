"""
附件模块公共工具

1. PermissionAdapter —— 从 AttachmentConfig 中读取 access_mixin 配置，
   实例化并调用对应的 4D 权限检查方法。

   支持：
   - identity_required 角色身份检查
   - user_level 等级检查
   - Django 原生权限码检查
   - 对象级权限检查（L4 部门隔离 + L5 工作组隔离）
   - permission_parent_chain 权限穿透链

2. prime_attachment_tokens / attachment_tokens_for —— 父对象的
   「分类 → download_token」映射装载。单条按需装载（模板标签 attachment_url 用），
   批量预载（列表页在行循环前调一次），两者共用同一份挂载点。
"""
from collections import defaultdict

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied

from .models import Attachment

# 映射挂在父对象实例上的属性名。仅在一次渲染内有效 —— 各列表/详情视图都是
# 每请求现查。若将来把父对象实例放进跨请求缓存复用，需在那里清掉此属性，
# 否则上传附件后 URL 不会更新。
TOKENS_ATTR = '_attachment_tokens'


def prime_attachment_tokens(objects):
    """为一批父对象预载「分类 → download_token」映射。

    列表页每行都要在文档列渲染 TDS/MSDS/RoHS 三个链接，逐个按需装载就是
    「每行一次查询」。在这里按 ContentType 分组、用一条 object_id__in 查完，
    之后循环里逐个调 attachment_url 都是零查询。

    Args:
        objects: 同一页上的父对象可迭代对象。可混合模型类型 —— 按 ContentType 分组，
                 每类各打一条查询。
    """
    groups = defaultdict(list)
    for obj in objects:
        if getattr(obj, TOKENS_ATTR, None) is not None:
            continue  # 已装载过（同一批对象重复调用），不重复查
        if getattr(obj, 'pk', None) is None:
            setattr(obj, TOKENS_ATTR, {})  # 未保存：不可能有附件，也避免被反复装载
            continue
        groups[ContentType.objects.get_for_model(obj)].append(obj)

    for ct, group in groups.items():
        # 按 -uploaded_at 排序后 setdefault —— 与 Attachment.Meta.ordering 下的
        # .first() 同口径，每个分类取最新那条
        rows = Attachment.objects.filter(
            content_type=ct,
            object_id__in=[obj.pk for obj in group],
            is_deleted=False,
        ).order_by('-uploaded_at').values_list('object_id', 'category', 'download_token')

        by_object = defaultdict(dict)
        for object_id, category, token in rows:
            by_object[object_id].setdefault(category, token)

        for obj in group:
            setattr(obj, TOKENS_ATTR, by_object.get(obj.pk, {}))


def attachment_tokens_for(parent_obj):
    """取父对象的分类→token 映射；没装载过就只装载它一个。"""
    tokens = getattr(parent_obj, TOKENS_ATTR, None)
    if tokens is None:
        prime_attachment_tokens([parent_obj])
        tokens = getattr(parent_obj, TOKENS_ATTR, {})
    return tokens


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
        # 传入当前操作动作，供 check_object_permission 区分查看/写操作（如仅负责人可上传）
        mixin.action = action

        # ---- Step 3: 身份角色检查 (L1) — 从 _resolve_config() 动态读取 ----
        cfg = mixin._resolve_config()
        role_codes = cfg['role_codes']
        if mixin.module_code:
            # 动态模块（DB 驱动）：空 role_codes = 未配置 → 拒绝
            if not role_codes:
                raise PermissionDenied("您的角色无权访问此附件")
            if user.user_type_id not in role_codes:
                raise PermissionDenied("您的角色无权访问此附件")
        else:
            # 静态模块：空 role_codes = 无限制
            if role_codes and user.user_type_id not in role_codes:
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
