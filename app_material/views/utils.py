from django.http import JsonResponse
from django.views import View
from django.db.models import Q
from ..models.material import MaterialType, ApplicationScenario, MaterialLibrary, TestConfig, MaterialCharacteristic
from app_raw_material.models import RawMaterial
from app_process.models import ProcessProfile
from app_basic_research.models import ResearchProject
from django.contrib.auth.models import User

class MaterialAutocompleteView(View):
    """
    全能基础数据搜索接口 (属于 app_material)
    负责: 材料、原材料、工艺、测试标准、场景、特征属性、用户、预研项目
    """
    def get(self, request):
        model_type = request.GET.get('model')
        query = request.GET.get('q', '')
        
        data = []
        if not model_type:
            return JsonResponse([], safe=False)

        # 1. 核心材料牌号
        if model_type == 'material':
            qs = MaterialLibrary.objects.filter(Q(grade_name__icontains=query) | Q(manufacturer__icontains=query))[:20]
            data = [{'value': item.pk, 'text': f"{item.grade_name} ({item.manufacturer})"} for item in qs]
            
        # 2. 原材料
        elif model_type == 'raw_material':
            qs = RawMaterial.objects.filter(Q(name__icontains=query) | Q(model_name__icontains=query))[:20]
            data = [{'value': item.pk, 'text': f"{item.name} {item.model_name or ''} ({item.category.name})"} for item in qs]
            
        # 3. 生产工艺
        elif model_type == 'process':
            qs = ProcessProfile.objects.filter(name__icontains=query)[:20]
            data = [{'value': item.pk, 'text': item.name} for item in qs]

        # 4. 测试标准配置
        elif model_type == 'test_config':
            qs = TestConfig.objects.filter(Q(name__icontains=query) | Q(standard__icontains=query))[:20]
            data = []
            for item in qs:
                cond = f" ({item.condition})" if item.condition else ""
                data.append({'value': item.pk, 'text': f"[{item.category.name}] {item.name} - {item.standard}{cond}"})

        # 5. 应用场景
        elif model_type == 'scenario':
            qs = ApplicationScenario.objects.filter(name__icontains=query)[:20]
            data = [{'value': item.pk, 'text': item.name} for item in qs]

        # 6. 特征属性 (新增)
        elif model_type == 'characteristic':
            qs = MaterialCharacteristic.objects.filter(name__icontains=query)[:20]
            data = [{'value': item.pk, 'text': item.name} for item in qs]

        # 7. 预研项目
        elif model_type == 'research_project':
            qs = ResearchProject.objects.filter(Q(code__icontains=query) | Q(name__icontains=query))[:20]
            data = [{'value': item.pk, 'text': f"{item.code} {item.name}"} for item in qs]

        # 8. 用户
        elif model_type == 'user':
            qs = User.objects.filter(is_active=True).filter(Q(username__icontains=query) | Q(first_name__icontains=query))[:20]
            data = [{'value': item.pk, 'text': f"{item.first_name or item.username}"} for item in qs]

        return JsonResponse(data, safe=False)
