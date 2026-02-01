from django.http import JsonResponse
from django.db.models import Q
from ..models import Supplier

def raw_material_api_search(request):
    model_name = request.GET.get('model')
    query = request.GET.get('q', '')
    
    results = []
    
    if model_name == 'supplier':
        # 搜索 Supplier
        queryset = Supplier.objects.filter(
            Q(name__icontains=query)
        ).order_by('name')[:20] # 限制结果数量
        
        for item in queryset:
            text = str(item) # 使用模型的 __str__ 方法作为显示文本
            results.append({'value': item.pk, 'text': text})
            
    return JsonResponse(results, safe=False)
