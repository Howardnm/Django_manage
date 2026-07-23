"""
通用自动补全注册表 — 解耦 common_utils 与各 app。

各 app 在 AppConfig.ready() 中调用 register_autocomplete() 注册自己的
模型类型、查询构建器和格式化器。common_utils/views.py 的 MaterialAutocompleteView
通过 get_registry() 查找，无需导入任何 app 模块。

用法（在 app 的 apps.py 中）：
    from common_utils.autocomplete_registry import register_autocomplete

    def _build_qs(query):
        from myapp.models import MyModel
        return MyModel.objects.filter(name__icontains=query)

    def _format(item):
        return {'value': item.pk, 'text': str(item)}

    register_autocomplete('my_model', _build_qs, _format, 'my_model_detail')
"""

_registry = {}


def register_autocomplete(model_key, builder_fn, formatter_fn, detail_url_name=None, access_filter=None):
    """
    注册一个模型类型的自动补全处理器。

    Args:
        model_key: 字符串键（如 'material', 'project', 'user'）
        builder_fn: 函数 (query: str) -> QuerySet，用于构建查询
        formatter_fn: 函数 (item) -> {'value': ..., 'text': ...}，格式化单个结果
        detail_url_name: 可选的 Django URL 名称，用于生成详情页链接
        access_filter: 可选的权限过滤函数 (user, queryset) -> queryset，
                       用于在 autocomplete 中应用 L1/L4 权限隔离。
                       如果为 None，不做额外过滤（仅 LoginRequired 保护）。
                       可用 make_autocomplete_access_filter() 工厂创建。
    """
    _registry[model_key] = {
        'builder': builder_fn,
        'formatter': formatter_fn,
        'detail_url': detail_url_name,
        'access_filter': access_filter,
    }


def get_registry():
    """返回当前注册表（供 MaterialAutocompleteView 使用）。"""
    return _registry


def make_autocomplete_access_filter(access_mixin_class):
    """
    创建 autocomplete 权限过滤函数的工厂方法。

    直接接收 AccessMixin 子类，自动读取其 L1/L4/L5 类属性，
    避免手动配置与 AccessMixin 不一致。

    Args:
        access_mixin_class: UnifiedAccessMixin 子类（如 BasicResearchAccessMixin）。
                           传入 None 返回 None（不启用权限过滤）。

    Returns:
        函数 (user, queryset) -> queryset，或 None
        — superuser 直接返回原 queryset
        — L1 不匹配抛出 PermissionDenied（视图捕获后返回空列表）
        — L4 过滤到当前用户部门的拥有者
        — L5 过滤到当前用户同工作组的拥有者（含本人 + 未分配组的孤立用户）

    用法:
        from app_basic_research.mixins import BasicResearchAccessMixin
        access_filter = make_autocomplete_access_filter(BasicResearchAccessMixin)
    """
    if access_mixin_class is None:
        return None

    from django.core.exceptions import PermissionDenied
    from django.db.models import Q, Exists, OuterRef

    # 从 AccessMixin 类属性自动提取权限配置
    # module_code 模式：从 DB 动态读取；否则从 class attribute 读取
    module_code = getattr(access_mixin_class, 'module_code', None)
    user_link_fields = getattr(access_mixin_class, 'user_link_fields', [])
    user_link_field = user_link_fields[0] if user_link_fields else None

    def _filter(user, qs):
        if user.is_superuser:
            return qs

        # L1: 角色白名单 — module_code 模式从 DB 读取，否则从 class attribute
        if module_code:
            from app_user.services.identity_service import IdentityService
            cfg = IdentityService.get_module_config(module_code)
            role_codes = cfg['role_codes']
            do_l4 = cfg['enforce_dept_isolation']
            do_l5 = cfg['enforce_group_isolation']
        else:
            role_codes = getattr(access_mixin_class, 'identity_required', [])
            do_l4 = getattr(access_mixin_class, 'enforce_dept_isolation', False)
            do_l5 = getattr(access_mixin_class, 'enforce_group_isolation', False)

        if role_codes and user.user_type_id not in role_codes:
            raise PermissionDenied()

        # L4: 部门隔离
        if do_l4 and user_link_field:
            if user.department:
                qs = qs.filter(**{f'{user_link_field}__department': user.department})
            else:
                qs = qs.filter(**{user_link_field: user})

        # L5: 工作组隔离
        if do_l5 and user_link_field:
            from app_user.models import WorkGroup
            user_wg_ids = list(
                user.work_groups.filter(is_active=True).values_list('id', flat=True)
            )
            if user_wg_ids:
                qs = qs.filter(
                    Q(**{user_link_field: user}) |
                    Q(**{
                        f'{user_link_field}__work_groups__id__in': user_wg_ids,
                        f'{user_link_field}__work_groups__is_active': True,
                    })
                )
            else:
                owner_has_wg = WorkGroup.members.through.objects.filter(
                    **{f'{user_link_field}_id': OuterRef(user_link_field)}
                )
                qs = qs.filter(
                    Q(**{user_link_field: user}) |
                    ~Q(Exists(owner_has_wg))
                )

        if do_l4 or do_l5:
            qs = qs.distinct()

        return qs

    return _filter
