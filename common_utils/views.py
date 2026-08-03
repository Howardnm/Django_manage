"""
通用 API 视图。

Exports:
    MaterialAutocompleteView — 通用搜索自动补全（TomSelect / search_picker_modal 共用）
    UserTreeAPIView        — 组织架构人员树 API

MaterialAutocompleteView 依赖各 app 在 AppConfig.ready() 中通过
register_autocomplete() 注册模型类型，本模块不导入任何业务模块。
"""

import time
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.urls import reverse
from django.views import View
from common_utils.autocomplete_registry import get_registry
from common_utils.mixins import InternalUserRequiredMixin

# 模块级简单 TTL 缓存（组织树变更多发于维护期，60s 缓存大幅减少重复查询）
_user_tree_cache = {'data': None, 'expires_at': 0}
_USER_TREE_TTL = 60


class MaterialAutocompleteView(LoginRequiredMixin, View):
    """
    通用搜索自动补全 API。

    支持两种响应模式：
    - 分页模式（传 page 参数）：供 search_picker_modal 使用
    - 数组模式（不传 page）：供 TomSelect remote-search 使用

    模型类型通过注册表（autocomplete_registry）查找，各 app 在
    AppConfig.ready() 中注册自己的 builder/formatter。

    URL: /common/api/search/?model=<type>&q=<query>&page=<n>
    """

    def _lookup(self, model_type):
        """从注册表查找模型类型的处理器。"""
        registry = get_registry()
        return registry.get(model_type)

    def _format_item(self, model_type, item):
        """对单个结果应用格式化器，并注入详情 URL。"""
        entry = self._lookup(model_type)
        if not entry:
            return {}
        data = entry['formatter'](item)
        url_name = entry.get('detail_url')
        if url_name:
            data['url'] = reverse(url_name, kwargs={'pk': item.pk})
        return data

    def get(self, request):
        model_type = request.GET.get('model')
        query = request.GET.get('q', '')

        entry = self._lookup(model_type) if model_type else None
        if not entry:
            return JsonResponse([], safe=False)

        qs = entry['builder'](query)

        # 应用权限过滤（L1 角色检查 / L4 部门隔离 / L5 工作组隔离）
        access_filter = entry.get('access_filter')
        if access_filter:
            from django.core.exceptions import PermissionDenied
            try:
                qs = access_filter(request.user, qs)
            except PermissionDenied:
                return JsonResponse([], safe=False)

        page = request.GET.get('page')
        if page is not None:
            page = int(page)
            page_size = int(request.GET.get('page_size', 10))
            total = qs.count()
            offset = (page - 1) * page_size
            results = [self._format_item(model_type, item) for item in qs[offset:offset + page_size]]
            return JsonResponse({
                'results': results,
                'total': total,
                'page': page,
                'page_size': page_size,
                'has_next': offset + page_size < total,
                'has_prev': page > 1,
            })

        data = [entry['formatter'](item) for item in qs[:20]]
        return JsonResponse(data, safe=False)


class UserTreeAPIView(InternalUserRequiredMixin, View):
    """
    组织架构人员树 API（仅限内部用户 + 超管访问）。

    返回三级树形 JSON：Department → WorkGroup → User + ReviewGroup + 未分配用户。
    供前端 user_picker_modal.js 调用。

    URL: /common/api/user-tree/?q=<search>

    性能优化：
        - Prefetch 对象确保 is_active 过滤不下发到 Python 层、避免 N+1
        - .only() 限制 User 字段为仅需的 pk / username / first_name
        - 搜索时 Python 侧过滤（利用 prefetch 缓存，无额外 DB 查询）
    """

    def get(self, request):
        from app_user.models import Department, WorkGroup, ReviewGroup
        from django.contrib.auth import get_user_model
        from django.db.models import Q, Prefetch
        User = get_user_model()
        search = request.GET.get('q', '').strip()

        # 无搜索时走缓存（组织树变化频率低，60s TTL）
        if not search:
            now = time.time()
            if _user_tree_cache['data'] is not None and _user_tree_cache['expires_at'] > now:
                return JsonResponse(_user_tree_cache['data'])

        # 基础用户查询集：仅拉取需要的字段
        base_user_qs = User.objects.filter(is_active=True).only('pk', 'username', 'first_name')

        nodes = []

        # 1. Department → WorkGroup → User（单次查询 + Prefetch）
        depts = Department.objects.prefetch_related(
            Prefetch(
                'workgroup_set',
                queryset=WorkGroup.objects.filter(is_active=True).prefetch_related(
                    Prefetch('members', queryset=base_user_qs, to_attr='_active_members')
                ),
                to_attr='_active_workgroups',
            )
        )
        for dept in depts:
            wg_children = []
            for wg in dept._active_workgroups:
                users = wg._active_members
                if search:
                    users = [
                        u for u in users
                        if search.lower() in u.username.lower()
                        or search.lower() in (u.first_name or '').lower()
                    ]
                if not users:
                    continue
                wg_children.append({
                    'id': f'wg_{wg.pk}',
                    'label': wg.name,
                    'type': 'workgroup',
                    'children': [self._format_user(u) for u in users]
                })
            if wg_children:
                nodes.append({
                    'id': f'dept_{dept.pk}',
                    'label': dept.name,
                    'type': 'department',
                    'children': wg_children,
                    'collapsed': True,
                })

        # 2. ReviewGroup → User（单次查询 + Prefetch）
        for rg in ReviewGroup.objects.filter(is_active=True).prefetch_related(
            Prefetch('members', queryset=base_user_qs, to_attr='_active_members')
        ):
            users = rg._active_members
            if search:
                users = [
                    u for u in users
                    if search.lower() in u.username.lower()
                    or search.lower() in (u.first_name or '').lower()
                ]
            if not users:
                continue
            nodes.append({
                'id': f'rg_{rg.pk}',
                'label': f'[{rg.name}]',
                'type': 'reviewgroup',
                'children': [self._format_user(u) for u in users],
                'collapsed': True,
            })

        # 3. Unassigned users（单次查询）
        unassigned = User.objects.filter(
            is_active=True, work_groups__isnull=True, review_groups__isnull=True
        ).only('pk', 'username', 'first_name').distinct()
        if search:
            unassigned = unassigned.filter(
                Q(username__icontains=search) | Q(first_name__icontains=search))
        if unassigned.exists():
            nodes.append({
                'id': 'other',
                'label': '其他用户',
                'type': 'other',
                'children': [self._format_user(u) for u in unassigned],
                'collapsed': False,
            })

        data = {'nodes': nodes}
        if not search:
            _user_tree_cache['data'] = data
            _user_tree_cache['expires_at'] = time.time() + _USER_TREE_TTL
        return JsonResponse(data)

    @staticmethod
    def _format_user(u):
        return {
            'id': u.pk,
            'label': f'{u.first_name or u.username} ({u.username})',
            'type': 'user',
        }
