"""权限控制核心 Mixin 模块。提供基于 L1~L5 五层安全模型的统一访问控制。

权限配置通过 module_code 从 ModuleAccessConfig (DB) 动态读取，
不再依赖硬编码的 IdentityConfig 静态常量。

导出: UnifiedAccessMixin。"""

import logging
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect, get_object_or_404
from django.conf import settings
from django.db.models import Q, Exists, OuterRef
from .models import WorkGroup
from .services.identity_service import IdentityService

logger = logging.getLogger(__name__)


class UnifiedAccessMixin(PermissionRequiredMixin):
    """
    统一权限架构控制 Mixin — 5 维安全模型。

    准入控制（has_permission，按从粗到细依次校验）：
        L1  角色白名单 (identity_required)     — 你是谁？从 ModuleAccessConfig 动态读取
        L2  用户等级   (min_level_required)    — 你等级够吗？
        L3  权限码     (permission_required)   — 你能做这个操作吗？查数据库，最后校验

    数据隔离（get_queryset / check_object_permission，准入通过后按需生效）：
        L4  部门隔离   (enforce_dept_isolation)   — 只看本部门数据
        L5  工作组隔离 (enforce_group_isolation)   — 只看本工作组数据

    Attributes:
        module_code: 模块标识符，对应 ModuleAccessConfig.module_code。
                     子类声明此属性后，L1/L2/L4/L5 自动从 DB 读取。
        identity_required: 直接声明 L1 角色白名单（不使用 module_code 时）。
        min_level_required: L2 最低用户等级（默认 1）。
        permission_required: L3 Django 原生权限码（空列表 = 跳过）。
        enforce_dept_isolation: L4 部门隔离开关（module_code 模式下从 DB 读取）。
        enforce_group_isolation: L5 工作组隔离开关（module_code 模式下从 DB 读取）。
        user_link_fields: 用于探测「数据所有者」的字段名列表（按优先级排序）。
    """
    # —— 模块标识（声明后 L1/L2/L4/L5 从 ModuleAccessConfig 动态读取）——
    module_code = None

    # —— 准入控制（module_code 模式下从 DB 读取，否则从以下 class attribute 读取）——
    identity_required = []
    min_level_required = 1
    permission_required = []

    # —— 数据隔离（module_code 模式下从 DB 读取）——
    enforce_dept_isolation = True
    enforce_group_isolation = False

    # —— 辅助配置 ——
    user_link_fields = ['manager', 'creator', 'user', 'owner', 'uploader', 'salesperson']

    # ══════════════════════════════════════════════════════════
    #  类方法：供模板/View 做 UI 权限判断
    # ══════════════════════════════════════════════════════════

    @classmethod
    def user_has_access(cls, user) -> bool:
        """检查 user 是否有权访问本模块（处理 superuser 绕过 + DB 动态读取）。

        类方法，无需实例化 request，供 View.get_context_data()、模板、context processor 使用。
        """
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        if not cls.module_code:
            return True
        role_codes = IdentityService.get_module_role_codes(cls.module_code)
        # 空 role_codes = 未配置 → 拒绝访问（与 has_permission() 保持一致）
        if not role_codes:
            return False
        return user.user_type_id in role_codes

    # ══════════════════════════════════════════════════════════
    #  统一配置解析入口（单请求内缓存）
    # ══════════════════════════════════════════════════════════

    def _resolve_config(self):
        """返回模块权限配置 dict，首次调用后缓存在实例上。

        Returns:
            {'role_codes': [...], 'min_level': int,
             'enforce_dept_isolation': bool, 'enforce_group_isolation': bool}
        """
        if not hasattr(self, '_cached_config'):
            if self.module_code:
                self._cached_config = IdentityService.get_module_config(self.module_code)
            else:
                self._cached_config = {
                    'role_codes': self.identity_required,
                    'min_level': self.min_level_required,
                    'enforce_dept_isolation': self.enforce_dept_isolation,
                    'enforce_group_isolation': self.enforce_group_isolation,
                }
        return self._cached_config

    # ══════════════════════════════════════════════════════════
    #  准入控制
    # ══════════════════════════════════════════════════════════

    def dispatch(self, request, *args, **kwargs):
        """全局拦截 PermissionDenied，统一转为 handle_no_permission 处理"""
        try:
            return super().dispatch(request, *args, **kwargs)
        except PermissionDenied as e:
            return self.handle_no_permission(message=str(e))

    def has_permission(self):
        """准入判定引擎：L1 角色 → L2 等级 → L3 权限码（由粗到细，尽早拒绝）。

        L1/L2 通过 _resolve_config() 从 ModuleAccessConfig (DB) 动态读取。

        Returns: bool — 通过 L1→L2→L3 全部准入检查则为 True。
        """
        user = self.request.user

        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True

        # 防御性检查：用户自身角色是否被停用（修复 #5）
        if user.user_type_id and not getattr(user.user_type, 'is_active', True):
            return False

        cfg = self._resolve_config()
        role_codes = cfg['role_codes']

        # L1: 角色白名单
        if self.module_code:
            # 动态模块（DB 驱动）：role_codes 为空 = 未配置任何角色 → 拒绝所有非超管用户（修复 #3）
            if not role_codes:
                return False
            if user.user_type_id not in role_codes:
                return False
        else:
            # 静态模块（类属性回退）：role_codes 为空 = 无限制（兼容旧行为）
            if role_codes and user.user_type_id not in role_codes:
                return False

        # L2: 用户等级
        if user.user_level < cfg['min_level']:
            return False

        # L3: Django 原生权限码
        perms = self.get_permission_required()
        if perms and not super().has_permission():
            return False

        return True

    def handle_no_permission(self, message=None):
        """
        权限不足时的智能处理逻辑：
        1. 未登录 -> 跳转登录页
        2. AJAX/HTMX 请求 -> 返回 403 JSON
        3. 普通页面请求 -> 设置提示消息 + 跳转 PERM_DENIED_URL
        4. check_object_permission 抛出的 PermissionDenied 也会被 dispatch() 拦截后走进这里

        Args: message: 可选的自定义错误消息字符串。
        Returns: HttpResponseRedirect 或 JsonResponse。
        """
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()

        request = self.request
        is_ajax = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or request.headers.get('HX-Request') == 'true'
            or (request.headers.get('Accept') or '').startswith('application/json')
        )
        if is_ajax:
            detail = message or '权限不足，无法执行此操作。'
            return JsonResponse({'status': 'error', 'message': detail}, status=403)

        perm_denied_url = getattr(settings, 'PERM_DENIED_URL', 'permission_denied')
        from django.contrib import messages
        messages.error(self.request, message or "您的账号权限不足，无法访问该页面。")
        return redirect(perm_denied_url)

    # ══════════════════════════════════════════════════════════
    #  数据隔离
    # ══════════════════════════════════════════════════════════

    def get_queryset(self):
        """数据隔离引擎：L4 部门 → L5 工作组，开关从 _resolve_config() 动态读取。

        Returns: 经 L4/L5 过滤的 QuerySet；若视图无 model/queryset 则为 None。
        """
        user = self.request.user

        if hasattr(self, 'queryset') and self.queryset is not None:
            qs = self.queryset.all()
        elif hasattr(self, 'model') and self.model is not None:
            qs = self.model.objects.all()
        else:
            return None

        if user.is_superuser:
            return qs

        cfg = self._resolve_config()

        # L4: 部门级数据隔离
        if cfg['enforce_dept_isolation']:
            user_field = self._detect_user_link_field(qs.model)
            if user_field:
                if user.department:
                    qs = qs.filter(**{f"{user_field}__department": user.department})
                else:
                    qs = qs.filter(**{user_field: user})
            else:
                # 修复 C1: 无 user_link_field 时记录警告，避免静默跳过数据隔离
                logger.warning(
                    "get_queryset: model %s has no matching user_link_field (%s). "
                    "L4 department isolation skipped. "
                    "Add a matching field or set user_link_fields on the mixin.",
                    qs.model.__name__, self.user_link_fields,
                )

        # L5: 工作组级数据隔离
        if cfg['enforce_group_isolation']:
            user_field = (self._detect_user_link_field(qs.model)
                          if hasattr(qs, 'model') and qs.model else None)
            if user_field:
                user_wg_ids = list(
                    user.work_groups.filter(is_active=True).values_list('id', flat=True)
                )
                if user_wg_ids:
                    qs = qs.filter(
                        Q(**{user_field: user}) |
                        Q(**{
                            f"{user_field}__work_groups__id__in": user_wg_ids,
                            f"{user_field}__work_groups__is_active": True,
                        })
                    ).distinct()
                else:
                    owner_has_wg = WorkGroup.members.through.objects.filter(
                        **{f"{user_field}_id": OuterRef(user_field)}
                    )
                    qs = qs.filter(
                        Q(**{user_field: user}) |
                        ~Q(Exists(owner_has_wg))
                    ).distinct()

        return qs

    def _detect_user_link_field(self, model):
        """探测模型实际存在的关联字段。

        Args: model: 要扫描字段的 Django 模型类。
        Returns: 匹配的 user_link_fields 条目名称，未找到则为 None。
        """
        model_fields = [f.name for f in model._meta.get_fields()]
        for field in self.user_link_fields:
            if field in model_fields:
                return field
        return None

    # ══════════════════════════════════════════════════════════
    #  对象级权限
    # ══════════════════════════════════════════════════════════

    def get_object_or_deny(self):
        """
        Detail 视图标准取对象方法：用未过滤的 queryset 获取对象，再走 check_object_permission。
        避免 get_queryset() 的 L4/L5 数据隔离把无权对象过滤掉导致 404（应为 403）。

        Returns: 模型实例，已通过 check_object_permission 校验。
        """
        pk = self.kwargs[self.pk_url_kwarg]
        qs = self.model.objects.all()
        base_qs = self.get_queryset()
        if base_qs and base_qs.query.select_related:
            qs = qs.select_related(*base_qs.query.select_related)
        if base_qs and getattr(base_qs, '_prefetch_related_lookups', None):
            qs = qs.prefetch_related(*base_qs._prefetch_related_lookups)
        obj = get_object_or_404(qs, pk=pk)
        self.check_object_permission(obj)
        return obj

    def check_object_permission(self, obj):
        """对象级权限校验：所有者 → L4 部门 → L5 工作组（任一命中即放行）。

        L4/L5 开关从 _resolve_config() 动态读取。

        Args: obj: 要检查权限的模型实例。
        Returns: True 若通过。
        Raises: PermissionDenied: 若部门或工作组隔离不匹配。
        """
        user = self.request.user
        if user.is_superuser:
            return True

        # 1. 探测数据所有者
        owner = None
        for attr in self.user_link_fields:
            if hasattr(obj, attr):
                owner = getattr(obj, attr)
                if owner:
                    break
        if not owner:
            # 修复 #8: 无法确定所有者时的处理
            cfg = self._resolve_config()
            if not cfg['enforce_dept_isolation'] and not cfg['enforce_group_isolation']:
                # L4/L5 均未启用 → 无需所有者校验，放行
                return True
            # L4 或 L5 已启用但无法确定所有者 → 拒绝访问（fail-closed）
            logger.warning(
                "check_object_permission: object %s (pk=%s) has no matching "
                "user_link_field (%s), but L4/L5 isolation is enabled. Denying access.",
                type(obj).__name__, obj.pk, self.user_link_fields,
            )
            raise PermissionDenied("无法确定数据所有者，操作被拒绝。")

        # 2. 所有者本人 → 直接放行
        if owner == user:
            return True

        cfg = self._resolve_config()

        # 3. L4: 部门级检查
        if cfg['enforce_dept_isolation']:
            is_same_dept = (
                user.department
                and getattr(owner, 'department', None) == user.department
            )
            if not is_same_dept:
                raise PermissionDenied("您的账号无权操作其他部门的数据资产")

        # 4. L5: 工作组级检查
        if cfg['enforce_group_isolation']:
            user_wg_ids = set(
                user.work_groups.filter(is_active=True).values_list('id', flat=True)
            )
            owner_wg_ids = set(
                owner.work_groups.filter(is_active=True).values_list('id', flat=True)
            )
            if user_wg_ids:
                if not user_wg_ids.intersection(owner_wg_ids):
                    raise PermissionDenied("您的工作组无权操作该数据资产")
            else:
                if owner_wg_ids:
                    raise PermissionDenied("您的工作组无权操作该数据资产")

        return True

    def check_edit_permission(self, obj):
        """
        对象级编辑权限（默认实现）：
        - 超管 / 数据所有者 → 可编辑
        - 其他所有人（含同部门、同组）→ 仅可查看，不可编辑

        子类可重写以添加模块特定的编辑权限逻辑（如审批人、管理员角色等）。
        调用方：所有写操作视图（UpdateView 的 post/form_valid 方法）。

        Raises: PermissionDenied 若非数据所有者。
        """
        user = self.request.user
        if user.is_superuser:
            return

        owner = None
        for attr in self.user_link_fields:
            if hasattr(obj, attr):
                owner = getattr(obj, attr)
                if owner:
                    break

        if owner and owner == user:
            return

        raise PermissionDenied("仅数据所有者可编辑此记录。")
