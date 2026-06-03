from django.http import JsonResponse
from django.views.generic import View
from app_user.mixins import UnifiedAccessMixin, IdentityConfig


class TrialAutocompleteView(UnifiedAccessMixin, View):
    """TomSelect 自动补全 API"""
    identity_required = IdentityConfig.INTERNAL_STAFF

    def get(self, request):
        query = request.GET.get('q', '').strip()
        model_name = request.GET.get('model', '')

        if len(query) < 1:
            return JsonResponse({'results': []})

        results = []
        if model_name == 'formula':
            from app_formula.models import LabFormula
            qs = LabFormula.objects.filter(name__icontains=query).values('id', 'name')[:20]
            results = [{'id': obj['id'], 'text': obj['name']} for obj in qs]

        elif model_name == 'project':
            from app_project.models import Project
            qs = Project.objects.filter(name__icontains=query).values('id', 'name')[:20]
            results = [{'id': obj['id'], 'text': obj['name']} for obj in qs]

        elif model_name == 'process_profile':
            from app_process.models import ProcessProfile
            qs = ProcessProfile.objects.filter(name__icontains=query).values('id', 'name')[:20]
            results = [{'id': obj['id'], 'text': obj['name']} for obj in qs]

        elif model_name == 'mold':
            from app_trial_production.models import MoldType
            qs = MoldType.objects.filter(name__icontains=query).values('id', 'mold_code', 'name')[:20]
            results = [{'id': obj['id'], 'text': f"[{obj['mold_code']}] {obj['name']}"} for obj in qs]

        elif model_name == 'test_config':
            from app_material.models import TestConfig
            qs = TestConfig.objects.filter(name__icontains=query).values('id', 'name')[:20]
            results = [{'id': obj['id'], 'text': obj['name']} for obj in qs]

        return JsonResponse({'results': results})
