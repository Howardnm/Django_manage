"""
通用 API 视图。

Exports:
    MaterialAutocompleteView — 通用搜索自动补全（TomSelect / search_picker_modal 共用）
    UserTreeAPIView        — 组织架构人员树 API

MaterialAutocompleteView 依赖各 app 在 AppConfig.ready() 中通过
register_autocomplete() 注册模型类型，本模块不导入任何业务模块。
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.urls import reverse
from django.views import View
from common_utils.autocomplete_registry import get_registry


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


class UserTreeAPIView(View):
    """
    组织架构人员树 API。

    返回三级树形 JSON：Department → WorkGroup → User + ReviewGroup + 未分配用户。
    供前端 user_picker_modal.js 调用。

    URL: /common/api/user-tree/?q=<search>
    """

    def get(self, request):
        from app_user.models import Department, WorkGroup, ReviewGroup
        from django.contrib.auth import get_user_model
        from django.db.models import Q
        User = get_user_model()
        search = request.GET.get('q', '').strip()

        nodes = []

        # 1. Department → WorkGroup → User
        depts = Department.objects.prefetch_related('workgroup_set__members').all()
        for dept in depts:
            wg_children = []
            for wg in dept.workgroup_set.filter(is_active=True):
                users = wg.members.filter(is_active=True)
                if search:
                    users = users.filter(
                        Q(username__icontains=search) | Q(first_name__icontains=search))
                if not users.exists():
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

        # 2. ReviewGroup
        for rg in ReviewGroup.objects.filter(is_active=True).prefetch_related('members'):
            users = rg.members.filter(is_active=True)
            if search:
                users = users.filter(
                    Q(username__icontains=search) | Q(first_name__icontains=search))
            if not users.exists():
                continue
            nodes.append({
                'id': f'rg_{rg.pk}',
                'label': f'[{rg.name}]',
                'type': 'reviewgroup',
                'children': [self._format_user(u) for u in users],
                'collapsed': True,
            })

        # 3. Unassigned users
        unassigned = User.objects.filter(
            is_active=True, work_groups__isnull=True, review_groups__isnull=True
        ).distinct()
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

        return JsonResponse({'nodes': nodes})

    @staticmethod
    def _format_user(u):
        return {
            'id': u.pk,
            'label': f'{u.first_name or u.username} ({u.username})',
            'type': 'user',
        }
