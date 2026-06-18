from django.db.models import Q
from django.http import JsonResponse
from django.views.generic import View
from app_trial_production.mixins import TrialProductionAccessMixin


class TrialAutocompleteView(TrialProductionAccessMixin, View):
    """TomSelect 自动补全 API — 按部门/项目归属过滤搜索结果"""

    def get(self, request):
        query = request.GET.get('q', '').strip()
        model_name = request.GET.get('model', '')

        if len(query) < 1:
            return JsonResponse({'results': []})

        results = []
        if model_name == 'formula':
            from app_formula.models import LabFormula
            qs = LabFormula.objects.filter(name__icontains=query)
            # 按可访问的项目过滤配方
            if not request.user.is_superuser and request.user.department:
                qs = qs.filter(project__manager__department=request.user.department)
            qs = qs.values('id', 'name')[:20]
            results = [{'id': obj['id'], 'text': obj['name']} for obj in qs]

        elif model_name == 'project':
            from app_project.models import Project
            qs = Project.objects.filter(name__icontains=query)
            # 按部门或成员身份过滤项目
            if not request.user.is_superuser:
                qs = qs.filter(
                    Q(manager=request.user) | Q(members__user=request.user)
                ).distinct()
            qs = qs.values('id', 'name')[:20]
            results = [{'id': obj['id'], 'text': obj['name']} for obj in qs]

        elif model_name == 'process_profile':
            from app_process.models import ProcessProfile
            qs = ProcessProfile.objects.filter(name__icontains=query)
            # 按部门隔离：非超管且有所属部门的用户只能看到本部门或未指定负责人的工艺方案
            if not request.user.is_superuser:
                if request.user.department:
                    qs = qs.filter(
                        Q(creator__department=request.user.department) |
                        Q(creator__isnull=True)
                    )
                else:
                    qs = qs.filter(
                        Q(creator=request.user) |
                        Q(creator__isnull=True)
                    )
            qs = qs.values('id', 'name')[:20]
            results = [{'id': obj['id'], 'text': obj['name']} for obj in qs]

        elif model_name == 'mold':
            from app_trial_production.models import MoldType
            qs = MoldType.objects.filter(name__icontains=query)
            # 仅展示可用状态的模具
            qs = qs.filter(status='AVAILABLE').values('id', 'mold_code', 'name')[:20]
            results = [{'id': obj['id'], 'text': f"[{obj['mold_code']}] {obj['name']}"} for obj in qs]

        elif model_name == 'test_config':
            from app_material.models import TestConfig
            qs = TestConfig.objects.filter(name__icontains=query).values('id', 'name')[:20]
            results = [{'id': obj['id'], 'text': obj['name']} for obj in qs]

        return JsonResponse({'results': results})
