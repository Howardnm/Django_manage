from django.db.models import Q
from django.http import JsonResponse
from django.views.generic import View

from common_utils.text_search import text_q
from app_trial_production.mixins import TrialProductionAccessMixin


class TrialAutocompleteView(TrialProductionAccessMixin, View):
    """TomSelect 自动补全 API — 按部门/项目归属过滤搜索结果"""
    enforce_dept_isolation = False

    def get(self, request):
        query = request.GET.get('q', '').strip()
        model_name = request.GET.get('model', '')

        # 空查询时返回前 20 条，支持 TomSelect preload: 'focus' 预加载
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

        elif model_name == 'project_pending':
            # 仅返回有待排产工单的项目（挤出排产工作台专用）
            from app_project.models import Project
            from app_trial_production.models import ProductionOrder
            pending_project_ids = ProductionOrder.objects.filter(
                status='ACCEPTED',
                extrusion_scheduled_date__isnull=True,
            ).values_list('project_id', flat=True).distinct()
            qs = Project.objects.filter(
                pk__in=pending_project_ids,
                name__icontains=query,
            )
            if not request.user.is_superuser:
                qs = qs.filter(
                    Q(manager=request.user) | Q(members__user=request.user)
                ).distinct()
            qs = qs.values('id', 'name')[:20]
            results = [{'id': obj['id'], 'text': obj['name']} for obj in qs]

        elif model_name == 'process_profile':
            from app_process.models import ProcessProfile
            name_q = request.GET.get('name', '').strip() or query
            process_type = request.GET.get('process_type', '').strip()
            material_type_id = request.GET.get('material_type', '').strip()
            machine_id = request.GET.get('machine', '').strip()
            qs = ProcessProfile.objects.select_related(
                'machine', 'screw_combination',
            ).prefetch_related('material_types')
            if name_q:
                qs = text_q(qs, name_q, 'name')
            if process_type:
                qs = text_q(qs, process_type, 'process_type_name')
            if material_type_id.isdigit():
                qs = qs.filter(material_types__pk=int(material_type_id)).distinct()
            if machine_id.isdigit():
                qs = qs.filter(machine_id=int(machine_id))
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
            qs = qs.order_by('name')
            try:
                page = max(int(request.GET.get('page') or 1), 1)
                page_size = min(max(int(request.GET.get('page_size') or 8), 1), 50)
            except (TypeError, ValueError):
                page, page_size = 1, 8
            total = qs.count()
            start = (page - 1) * page_size
            results = []
            for profile in qs[start:start + page_size]:
                results.append({
                    'id': profile.pk,
                    'value': profile.pk,
                    'text': profile.name,
                    'process_type': profile.process_type_name,
                    'materials': '、'.join(t.name for t in profile.material_types.all()),
                    'machine': str(profile.machine) if profile.machine_id else '',
                    'screw': str(profile.screw_combination) if profile.screw_combination_id else '',
                })
            return JsonResponse({
                'results': results,
                'total': total,
                'page': page,
                'page_size': page_size,
                'has_next': start + page_size < total,
                'has_prev': page > 1,
            })

        elif model_name == 'mold':
            from app_mold_injection.models import MoldType
            qs = MoldType.objects.filter(
                name__icontains=query, status='AVAILABLE'
            ).values('id', 'mold_code', 'name', 'cavity_count')[:20]
            results = [{'id': obj['id'], 'text': f"[{obj['mold_code']}] {obj['name']}", 'cavity_count': obj['cavity_count']} for obj in qs]

        elif model_name == 'test_config':
            from app_material.models import TestConfig
            qs = TestConfig.objects.filter(
                name__icontains=query
            ).values('id', 'name')[:20]
            results = [{'id': obj['id'], 'text': obj['name']} for obj in qs]

        elif model_name == 'customer':
            from app_repository.models import Customer
            qs = Customer.objects.filter(
                Q(company_name__icontains=query) | Q(short_name__icontains=query)
            ).values('id', 'company_name', 'short_name')[:20]
            results = [{'id': obj['id'], 'text': obj['company_name'] or obj['short_name']} for obj in qs]

        return JsonResponse({'results': results})
