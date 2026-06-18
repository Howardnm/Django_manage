"""权限控制核心 Mixin 模块。提供基于 L1~L5 五层安全模型的统一访问控制。

导出: IdentityConfig, UnifiedAccessMixin。"""

from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect, get_object_or_404
from django.conf import settings
from .models import User

class IdentityConfig:
    """
    业务逻辑分组 (权限集定义)。
    通过在这里定义分组，实现视图层代码的低耦合。

    Attributes:
        TECH_CORE: 技术核心——研发、工艺、配方全员。
        RND_ONLY: 纯技术研发。
        PROCESS_ONLY: 纯工艺工程。
        SUPPLY_CHAIN: 供应链/采购核心。
        PRODUCTION_CREW: 生产操作人员。
        INTERNAL_STAFF: 内部全员。
    """
    R_ENGINEER = User.UserType.ENGINEER
    R_PROCESS = User.UserType.PROCESS_ENGINEER
    R_SALES = User.UserType.SALES
    R_PURCHASING = User.UserType.PURCHASING
    R_ADMIN = User.UserType.ADMIN
    R_EXTRUSION_OP = User.UserType.EXTRUSION_OPERATOR
    R_COLOR_OP = User.UserType.COLOR_OPERATOR
    R_INJECTION_OP = User.UserType.INJECTION_OPERATOR
    R_TESTING_OP = User.UserType.TESTING_OPERATOR

    # 技术核心：涉及研发、工艺、配方的全员
    TECH_CORE = [R_ENGINEER, R_PROCESS, R_ADMIN]

    # 纯技术研发
    RND_ONLY = [R_ENGINEER, R_ADMIN]

    # 纯工艺工程
    PROCESS_ONLY = [R_PROCESS, R_ADMIN]

    # 供应链/采购核心
    SUPPLY_CHAIN = [R_PURCHASING, R_ADMIN]

    # 生产操作人员
    PRODUCTION_CREW = [R_EXTRUSION_OP, R_COLOR_OP, R_INJECTION_OP, R_TESTING_OP, R_ADMIN]

    # 内部全员 (包含采购 + 生产操作人员)
    INTERNAL_STAFF = [R_ENGINEER, R_PROCESS, R_SALES, R_PURCHASING, R_ADMIN,
                      R_EXTRUSION_OP, R_COLOR_OP, R_INJECTION_OP, R_TESTING_OP]


class UnifiedAccessMixin(PermissionRequiredMixin):
    """
    统一权限架构控制 Mixin — 5 维安全模型。

    准入控制（has_permission，按从粗到细依次校验）：
        L1  角色白名单 (identity_required)     — 你是谁？纯内存比较，最先拦截
        L2  用户等级   (min_level_required)    — 你等级够吗？
        L3  权限码     (permission_required)   — 你能做这个操作吗？查数据库，最后校验

    数据隔离（get_queryset / check_object_permission，准入通过后按需生效）：
        L4  部门隔离   (enforce_dept_isolation)   — 只看本部门数据
        L5  工作组隔离 (enforce_group_isolation)   — 只看本工作组数据

    Attributes:
        identity_required: L1 允许访问的角色白名单（空列表 = 仅要求登录）。
        min_level_required: L2 最低用户等级要求（默认 1）。
        permission_required: L3 Django 原生权限码（空列表 = 跳过此检查）。
        enforce_dept_isolation: L4 部门隔离开关（默认开启）。
        enforce_group_isolation: L5 工作组隔离开关（默认关闭）。
        user_link_fields: 用于探测「数据所有者」的字段名列表（按优先级排序）。
    """
    # —— 准入控制 ——
    # L1: 允许访问的角色白名单（空列表 = 仅要求登录）
    identity_required = []

    # L2: 最低用户等级要求（默认 1，即所有注册用户）
    min_level_required = 1

    # L3: Django 原生权限码（空列表 = 跳过此检查）
    permission_required = []

    # —— 数据隔离 ——
    # L4: 部门隔离开关（默认开启）
    enforce_dept_isolation = True

    # L5: 工作组隔离开关（默认关闭，各模块按需开启）
    enforce_group_isolation = False

    # —— 辅助配置 ——
    # 用于探测「数据所有者」的字段名列表（按优先级排序）
    user_link_fields = ['manager', 'creator', 'user', 'owner', 'uploader', 'salesperson']

    def get_object_or_deny(self):
        """
        Detail 视图标准取对象方法：用未过滤的 queryset 获取对象，再走 check_object_permission。
        避免 get_queryset() 的 L4/L5 数据隔离把无权对象过滤掉导致 404（应为 403）。

        Returns: 模型实例，已通过 check_object_permission 校验。
        """
        pk = self.kwargs[self.pk_url_kwarg]
        qs = self.model.objects.all()
        # 继承 get_queryset() 的 select_related / prefetch_related 优化，但不继承其 L4/L5 过滤
        base_qs = self.get_queryset()
        if base_qs.query.select_related:
            qs = qs.select_related(*base_qs.query.select_related)
        if getattr(base_qs, '_prefetch_related_lookups', None):
            qs = qs.prefetch_related(*base_qs._prefetch_related_lookups)
        obj = get_object_or_404(qs, pk=pk)
        self.check_object_permission(obj)
        return obj

    def dispatch(self, request, *args, **kwargs):
        """全局拦截 PermissionDenied，统一转为 handle_no_permission 处理"""
        try:
            return super().dispatch(request, *args, **kwargs)
        except PermissionDenied as e:
            return self.handle_no_permission(message=str(e))

    def has_permission(self):
        """准入判定引擎：L1 角色 → L2 等级 → L3 权限码（由粗到细，尽早拒绝）。

        Returns: bool — 通过 L1→L2→L3 全部准入检查则为 True。
        """
        user = self.request.user

        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True

        # L1: 角色白名单——最粗粒度，纯内存比较，最先拦截非法角色
        if self.identity_required and user.user_type not in self.identity_required:
            return False

        # L2: 用户等级——数值门槛
        if user.user_level < self.min_level_required:
            return False

        # L3: Django 原生权限码——最细粒度，需查数据库，仅在显式配置时执行
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

        # AJAX / HTMX 请求：返回 403 JSON，不设置 Django message
        request = self.request
        is_ajax = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or request.headers.get('HX-Request') == 'true'
            or (request.headers.get('Accept') or '').startswith('application/json')
        )
        if is_ajax:
            detail = message or '权限不足，无法执行此操作。'
            return JsonResponse({'status': 'error', 'message': detail}, status=403)

        # 普通页面请求：设置提示消息并跳转
        perm_denied_url = getattr(settings, 'PERM_DENIED_URL', 'permission_denied')
        from django.contrib import messages
        messages.error(self.request, message or "您的账号权限不足，无法访问该页面。")
        return redirect(perm_denied_url)

    def get_queryset(self):
        """数据隔离引擎：L4 部门 → L5 工作组，在准入通过后对查询集做范围过滤。

        Returns: 经 L4/L5 过滤的 QuerySet；若视图无 model/queryset 则为 None。
        """
        user = self.request.user

        # 自动获取 QuerySet
        if hasattr(self, 'queryset') and self.queryset is not None:
            qs = self.queryset.all()
        elif hasattr(self, 'model') and self.model is not None:
            qs = self.model.objects.all()
        else:
            # 普通 View 子类没有 model/queryset，无法自动隔离
            # 视图需手动调用 check_object_permission() 做对象级校验
            return None

        if user.is_superuser:
            return qs

        # L4: 部门级数据隔离 — 仅查看本部门人员拥有的数据
        if self.enforce_dept_isolation:
            user_field = self._detect_user_link_field(qs.model)
            if user_field:
                if user.department:
                    qs = qs.filter(**{f"{user_field}__department": user.department})
                else:
                    # 无部门用户回退：只能看自己的数据
                    qs = qs.filter(**{user_field: user})

        # L5: 工作组级数据隔离 — 仅查看本工作组人员拥有的数据
        if self.enforce_group_isolation:
            user_field = (self._detect_user_link_field(qs.model)
                          if hasattr(qs, 'model') and qs.model else None)
            if user_field:
                from django.db.models import Q, Exists, OuterRef
                from .models import WorkGroup
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
            if field in model_fields: return field
        return None

    def check_object_permission(self, obj):
        """对象级权限校验：所有者 → L4 部门 → L5 工作组（任一命中即放行）。

        Args: obj: 要检查权限的模型实例。
        Returns: True 若通过。
        Raises: PermissionDenied: 若部门或工作组隔离不匹配。
        """
        user = self.request.user
        if user.is_superuser:
            return True

        # 1. 探测数据所有者（按 user_link_fields 顺序扫描第一个匹配的 FK）
        owner = None
        for attr in self.user_link_fields:
            if hasattr(obj, attr):
                owner = getattr(obj, attr)
                if owner:
                    break
        if not owner:
            return True

        # 2. 所有者本人 → 直接放行
        if owner == user:
            return True

        # 3. L4: 部门级检查 — 同部门可见
        if self.enforce_dept_isolation:
            is_same_dept = (
                user.department
                and getattr(owner, 'department', None) == user.department
            )
            if not is_same_dept:
                raise PermissionDenied("您的账号无权操作其他部门的数据资产")

        # 4. L5: 工作组级检查 — 同工作组可见
        if self.enforce_group_isolation:
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
