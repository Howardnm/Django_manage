from django.views.generic import ListView, DetailView
from django.core.cache import cache
from ..models import CatalogProduct, CatalogCategory, VisitorLog, MirrorScenario, MirrorCharacteristic
from ..services.material_api import client
from collections import defaultdict

class CatalogListView(ListView):
    model = CatalogProduct
    template_name = 'apps/app_catalog/product_list.html'
    context_object_name = 'products'
    paginate_by = 10

    def get_queryset(self):
        qs = CatalogProduct.objects.filter(is_published=True).select_related('category').prefetch_related('scenarios', 'characteristics')
        s_id = self.request.GET.get('s')
        t_id = self.request.GET.get('t')
        c_id = self.request.GET.get('c')
        q = self.request.GET.get('q')
        
        if s_id: qs = qs.filter(scenarios__remote_id=s_id)
        if c_id: qs = qs.filter(characteristics__remote_id=c_id)
        if t_id: qs = qs.filter(category_id=t_id)
        if q: qs = qs.filter(display_name__icontains=q)

        return qs.distinct().order_by('-published_at', '-id')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # 增加缓存 key 版本，确保逻辑变动后强制刷新
        cache_key = 'catalog_nav_tree_structured_v2'
        nav_tree = cache.get(cache_key)
        if not nav_tree:
            nav_tree = self._build_nav_tree_from_local()
            cache.set(cache_key, nav_tree, 3600)
        
        context['nav_tree'] = nav_tree
        
        s_id = self.request.GET.get('s')
        t_id = self.request.GET.get('t')
        c_id = self.request.GET.get('c')
        
        context['current_s_obj'] = MirrorScenario.objects.filter(remote_id=s_id).first() if s_id else None
        context['current_t_obj'] = CatalogCategory.objects.filter(pk=t_id).first() if t_id else None
        context['current_c_obj'] = MirrorCharacteristic.objects.filter(remote_id=c_id).first() if c_id else None
        
        context['current_s'] = s_id
        context['current_t'] = t_id
        context['current_c'] = c_id
        
        return context

    def _build_nav_tree_from_local(self):
        """
        全本地 SQL 聚合构建：场景 -> 类型 -> 特征
        【修正】：确保没有特征的物料也能支撑分类节点的显示
        """
        all_products = CatalogProduct.objects.filter(is_published=True).select_related('category').prefetch_related('scenarios', 'characteristics')
        
        # 数据结构设计
        # sce_info: { id -> { name: str, types: { type_id -> { name: str, count: int, chars: { char_id -> { name: str, count: int } } } } } }
        tree_map = {}

        for p in all_products:
            # 材质分类 (本地 ID)
            t_id = p.category_id
            t_name = p.category.name
            
            # 一个产品属于多个场景
            for s in p.scenarios.all():
                s_id = s.remote_id
                s_name = s.name
                
                # 初始化场景层
                if s_id not in tree_map:
                    tree_map[s_id] = {'name': s_name, 'count': 0, 'types': {}}
                
                # 初始化类型层
                if t_id not in tree_map[s_id]['types']:
                    tree_map[s_id]['types'][t_id] = {'name': t_name, 'count': 0, 'characteristics': {}}
                
                # 无论有没有特征，该场景和该类型的总数都 +1
                tree_map[s_id]['count'] += 1
                tree_map[s_id]['types'][t_id]['count'] += 1
                
                # 处理特征层
                for c in p.characteristics.all():
                    c_id = c.remote_id
                    c_name = c.name
                    if c_id not in tree_map[s_id]['types'][t_id]['characteristics']:
                        tree_map[s_id]['types'][t_id]['characteristics'][c_id] = {'name': c_name, 'count': 0}
                    tree_map[s_id]['types'][t_id]['characteristics'][c_id]['count'] += 1

        # 转换为排序后的列表格式，供模板循环
        result_tree = []
        for s_id, s_info in tree_map.items():
            sce_node = {
                'id': s_id,
                'name': s_info['name'],
                'count': s_info['count'],
                'types': []
            }
            # 对类型进行排序 (按名称或 ID)
            for t_id, t_info in sorted(s_info['types'].items()):
                type_node = {
                    'id': t_id,
                    'name': t_info['name'],
                    'count': t_info['count'],
                    'characteristics': []
                }
                # 对特征进行排序
                for c_id, c_info in sorted(t_info['characteristics'].items()):
                    type_node['characteristics'].append({
                        'id': c_id,
                        'name': c_info['name'],
                        'count': c_info['count']
                    })
                sce_node['types'].append(type_node)
            
            result_tree.append(sce_node)
            
        return sorted(result_tree, key=lambda x: x['name'])

class CatalogDetailView(DetailView):
    model = CatalogProduct
    template_name = 'apps/app_catalog/product_detail.html'
    context_object_name = 'product'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        remote_id = self.object.remote_material_id
        try:
            remote_data = client.get_material_detail(remote_id)
            if remote_data:
                context['remote_material'] = remote_data
            else:
                context['api_error'] = True
                context['remote_material'] = self._get_fallback_data()
        except Exception:
            context['api_error'] = True
            context['remote_material'] = self._get_fallback_data()
        return context

    def _get_fallback_data(self):
        return {
            'grade_name': self.object.display_name,
            'description': self.object.description,
            'category': {'name': self.object.category.name},
            'characteristics': [{'name': c.name} for c in self.object.characteristics.all()],
            'manufacturer': 'SUNWILL (Offline Cache)',
            'is_offline': True
        }

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        VisitorLog.objects.create(
            product=self.get_object(),
            visitor_ip=self.request.META.get('REMOTE_ADDR'),
            user_agent=self.request.META.get('HTTP_USER_AGENT', ''),
            action='VIEW'
        )
        return response
