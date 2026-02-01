from django.http import JsonResponse
from django.db.models import Q
from ..models import MachineModel, ScrewCombination

def process_api_search(request):
    model_name = request.GET.get('model')
    query = request.GET.get('q', '')
    
    results = []
    
    if model_name == 'machinemodel':
        # 搜索 MachineModel
        # 搜索字段包括 brand, model_name, machine_code
        queryset = MachineModel.objects.filter(
            Q(brand__icontains=query) |
            Q(model_name__icontains=query) |
            Q(machine_code__icontains=query)
        ).order_by('brand', 'model_name')[:20] # 限制结果数量
        
        for item in queryset:
            text = str(item) # 使用模型的 __str__ 方法作为显示文本
            results.append({'value': item.pk, 'text': text})
            
    elif model_name == 'screwcombination':
        # 搜索 ScrewCombination
        # 搜索字段包括 name, combination_code
        queryset = ScrewCombination.objects.filter(
            Q(name__icontains=query) |
            Q(combination_code__icontains=query)
        ).order_by('name')[:20] # 限制结果数量
        
        for item in queryset:
            text = str(item) # 使用模型的 __str__ 方法作为显示文本
            results.append({'value': item.pk, 'text': text})
            
    return JsonResponse(results, safe=False)
