from django.views.generic import ListView, DetailView, TemplateView
from django.shortcuts import render
from django.http import Http404
from django.core.cache import cache # 引入缓存
from ..models import CatalogProduct, CatalogCategory, VisitorLog
from ..services.material_api import client

class CatalogHomeView(TemplateView):
    """
    一级导航：展示所有应用场景 (主菜单)
    """
    template_name = 'apps/app_catalog/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # 缓存应用场景列表 (1小时)
        scenarios = cache.get('catalog_scenarios')
        if scenarios is None:
            scenarios_data = client.get_scenarios()
            if isinstance(scenarios_data, dict):
                scenarios = scenarios_data.get('results', [])
            else:
                scenarios = scenarios_data if scenarios_data else []
            cache.set('catalog_scenarios', scenarios, 3600)
            
        context['scenarios'] = scenarios
        context['featured_products'] = CatalogProduct.objects.filter(is_published=True, is_featured=True)[:6]
        return context

class ScenarioCategoryView(TemplateView):
    """
    二级导航：指定场景下的材质系列 (子菜单)
    """
    template_name = 'apps/app_catalog/scenario_categories.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        scenario_id = self.kwargs.get('scenario_id')
        
        # 缓存该场景的基础信息
        scenarios = cache.get('catalog_scenarios')
        if not scenarios:
            scenarios = self.get_scenarios_from_api()
            
        current_scenario = next((s for s in scenarios if s['id'] == scenario_id), None)
        if not current_scenario:
            raise Http404("未找到应用场景")
        context['scenario'] = current_scenario

        # 获取该场景下的材质分类
        remote_results = client.get_material_list(scenarios=scenario_id)
        if remote_results and 'results' in remote_results:
            remote_type_ids = set(item['category']['id'] for item in remote_results['results'])
            context['categories'] = CatalogCategory.objects.filter(remote_type_id__in=remote_type_ids, is_active=True)
        else:
            context['categories'] = []
            
        return context

    def get_scenarios_from_api(self):
        data = client.get_scenarios()
        res = data.get('results', []) if isinstance(data, dict) else data
        cache.set('catalog_scenarios', res, 3600)
        return res

class CatalogListView(ListView):
    """
    三级导航：显示具体的牌号列表
    """
    model = CatalogProduct
    template_name = 'apps/app_catalog/product_list.html'
    context_object_name = 'products'
    paginate_by = 15

    def get_queryset(self):
        qs = CatalogProduct.objects.filter(is_published=True)
        scenario_id = self.kwargs.get('scenario_id')
        category_id = self.kwargs.get('category_id')
        
        if scenario_id and category_id:
            qs = qs.filter(category_id=category_id)
            remote_results = client.get_material_list(scenarios=scenario_id)
            if remote_results and 'results' in remote_results:
                remote_ids = [item['id'] for item in remote_results['results']]
                qs = qs.filter(remote_material_id__in=remote_ids)
            else:
                qs = qs.none()
        
        search_query = self.request.GET.get('q')
        if search_query:
            remote_results = client.get_material_list(search=search_query)
            if remote_results and 'results' in remote_results:
                remote_ids = [item['id'] for item in remote_results['results']]
                qs = qs.filter(remote_material_id__in=remote_ids)
            else:
                qs = qs.none()

        return qs.distinct()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        scenario_id = self.kwargs.get('scenario_id')
        if scenario_id:
            scenarios = cache.get('catalog_scenarios') or self.get_scenarios_from_api()
            context['scenario'] = next((s for s in scenarios if s['id'] == scenario_id), None)
        
        category_id = self.kwargs.get('category_id')
        if category_id:
            context['current_category'] = CatalogCategory.objects.filter(pk=category_id).first()
            
        return context

class CatalogDetailView(DetailView):
    """
    详情页：增加 API 数据缓存逻辑，减少主系统压力
    """
    model = CatalogProduct
    template_name = 'apps/app_catalog/product_detail.html'
    context_object_name = 'product'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        remote_id = self.object.remote_material_id
        cache_key = f'material_detail_{remote_id}'
        
        remote_data = cache.get(cache_key)
        if remote_data is None:
            try:
                remote_data = client.get_material_detail(remote_id)
                if remote_data:
                    # 缓存 10 分钟 (详情页数据可能变动，不宜缓存太久)
                    cache.set(cache_key, remote_data, 600)
                else:
                    context['api_error'] = True
            except Exception:
                context['api_error'] = True
        
        context['remote_material'] = remote_data
        return context

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        VisitorLog.objects.create(
            product=self.get_object(),
            visitor_ip=self.request.META.get('REMOTE_ADDR'),
            user_agent=self.request.META.get('HTTP_USER_AGENT', ''),
            action='VIEW'
        )
        return response
