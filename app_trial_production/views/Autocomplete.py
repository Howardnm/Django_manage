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
            if not request.user.is_superuser and request.user.department:
                qs = qs.filter(project__manager__department=request.user.department)
            qs = qs.values('id', 'name')[:20]
            results = [{'id': obj['id'], 'text': obj['name']} for obj in qs]

        elif model_name == 'project':
            from app_project.models import Project
            qs = Project.objects.filter(name__icontains=query)
            if not request.user.is_superuser:
                qs = qs.filter(
                    Q(manager=request.user) | Q(members__user=request.user)
                ).distinct()
            qs = qs.values('id', 'name')[:20]
            results = [{'id': obj['id'], 'text': obj['name']} for obj in qs]

        elif model_name == 'process_profile':
            from app_process.models import ProcessProfile
            qs = ProcessProfile.objects.filter(name__icontains=query)
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
            from app_mold_injection.models import MoldType
            qs = MoldType.objects.filter(
                name__icontains=query, status='AVAILABLE'
            ).values('id', 'mold_code', 'name')[:20]
            results = [{'id': obj['id'], 'text': f"[{obj['mold_code']}] {obj['name']}"} for obj in qs]

        elif model_name == 'test_config':
            from app_material.models import TestConfig
            qs = TestConfig.objects.filter(
                name__icontains=query
            ).values('id', 'name')[:20]
            results = [{'id': obj['id'], 'text': obj['name']} for obj in qs]

        elif model_name == 'sample_pellet':
            # 待打样颗粒列表（供注塑取料 autocomplete）
            from app_trial_production.models import SampleInventory
            qs = SampleInventory.objects.filter(
                type='PELLET', sub_type='FOR_INJECTION', status='IN_LAB',
            ).filter(
                Q(trial_code__icontains=query) |
                Q(formula__name__icontains=query)
            ).select_related('formula')[:20]
            results = [
                {'id': obj.pk, 'text': f"[{obj.trial_code}] {obj.formula.name if obj.formula else ''} ({obj.quantity}kg)"}
                for obj in qs
            ]

        return JsonResponse({'results': results})
