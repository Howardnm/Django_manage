from django.http import JsonResponse
from django.urls import reverse
from django.views import View
from django.db.models import Q
from app_formula.models import LabFormula
from app_formula.mixins import FormulaAccessMixin


class FormulaAutocompleteView(FormulaAccessMixin, View):
    """
    配方搜索 API — 受 FormulaAccessMixin 权限管控
    - 角色限制：仅 ENGINEER / ADMIN
    - 数据范围：部门隔离（按 creator 字段过滤）
    """
    model = LabFormula

    def get(self, request):
        query = request.GET.get('q', '')
        qs = self.get_queryset()
        qs = qs.filter(
            Q(code__icontains=query) | Q(name__icontains=query)
        ).select_related('project', 'project_node')

        page = request.GET.get('page')
        if page is not None:
            page = int(page)
            page_size = int(request.GET.get('page_size', 10))
            total = qs.count()
            offset = (page - 1) * page_size
            results = []
            for item in qs[offset:offset + page_size]:
                results.append({
                    'value': item.pk,
                    'text': f"[{item.code}] {item.name} ({item.project.name} | {item.project_node})",
                    'url': reverse('formula_detail', kwargs={'pk': item.pk}),
                })
            return JsonResponse({
                'results': results,
                'total': total,
                'page': page,
                'page_size': page_size,
                'has_next': offset + page_size < total,
                'has_prev': page > 1,
            })

        data = [{
            'value': item.pk,
            'text': f"[{item.code}] {item.name} ({item.project.name} | {item.project_node})",
        } for item in qs[:20]]
        return JsonResponse(data, safe=False)
