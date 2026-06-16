from django.http import JsonResponse
from django.urls import reverse
from django.views import View
from django.db.models import Q
from app_material.models.material import MaterialType, ApplicationScenario, MaterialLibrary, TestConfig, MaterialCharacteristic
from app_material.mixins import MaterialAccessMixin
from app_raw_material.models import RawMaterial
from app_process.models import ProcessProfile
from app_basic_research.models import ResearchProject
from app_project.models import Project
from django.contrib.auth.models import User


class MaterialAutocompleteView(MaterialAccessMixin, View):
    permission_required = 'app_material.view_materiallibrary'
    """
    通用搜索接口（分页模式供 search_picker_modal，数组模式兼容 TomSelect remote-search）
    """

    MODEL_BUILDERS = {
        'material': lambda query: MaterialLibrary.objects.filter(
            Q(grade_name__icontains=query) | Q(manufacturer__icontains=query)),
        'raw_material': lambda query: RawMaterial.objects.filter(
            Q(name__icontains=query) | Q(model_name__icontains=query)),
        'process': lambda query: ProcessProfile.objects.filter(name__icontains=query),
        'test_config': lambda query: TestConfig.objects.filter(
            Q(name__icontains=query) | Q(standard__icontains=query)),
        'scenario': lambda query: ApplicationScenario.objects.filter(name__icontains=query),
        'characteristic': lambda query: MaterialCharacteristic.objects.filter(name__icontains=query),
        'research_project': lambda query: ResearchProject.objects.filter(
            Q(code__icontains=query) | Q(name__icontains=query)),
        'user': lambda query: User.objects.filter(is_active=True).filter(
            Q(username__icontains=query) | Q(first_name__icontains=query)),
        'commercial_project': lambda query: Project.objects.filter(name__icontains=query),
    }

    MODEL_FORMATTERS = {
        'material': lambda item: {'value': item.pk, 'text': f"{item.grade_name} ({item.manufacturer})"},
        'raw_material': lambda item: {'value': item.pk, 'text': f"{item.name} {item.model_name or ''} ({item.category.name})"},
        'process': lambda item: {'value': item.pk, 'text': item.name},
        'test_config': lambda item: {'value': item.pk,
            'text': f"[{item.category.name}] {item.name} - {item.standard}{f' ({item.condition})' if item.condition else ''}"},
        'scenario': lambda item: {'value': item.pk, 'text': item.name},
        'characteristic': lambda item: {'value': item.pk, 'text': item.name},
        'research_project': lambda item: {'value': item.pk, 'text': f"{item.code} {item.name}"},
        'user': lambda item: {'value': item.pk, 'text': f"{item.first_name or item.username}"},
        'commercial_project': lambda item: {'value': item.pk, 'text': item.name},
    }

    MODEL_DETAIL_URLS = {
        'material': 'material_detail',
        'raw_material': 'raw_material_detail',
        'process': 'process_profile_detail',
        'commercial_project': 'project_detail',
    }

    def _format_item(self, model_type, item):
        data = self.MODEL_FORMATTERS[model_type](item)
        url_name = self.MODEL_DETAIL_URLS.get(model_type)
        if url_name:
            data['url'] = reverse(url_name, kwargs={'pk': item.pk})
        return data

    def get(self, request):
        model_type = request.GET.get('model')
        query = request.GET.get('q', '')

        if not model_type or model_type not in self.MODEL_BUILDERS:
            return JsonResponse([], safe=False)

        qs = self.MODEL_BUILDERS[model_type](query)

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

        data = [self.MODEL_FORMATTERS[model_type](item) for item in qs[:20]]
        return JsonResponse(data, safe=False)


class UserTreeAPIView(View):
    """组织架构人员树 API——返回 Department → WorkGroup → User + ReviewGroup 树形 JSON"""

    def get(self, request):
        from app_user.models import Department, WorkGroup, ReviewGroup
        from django.contrib.auth import get_user_model
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
