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
        
        nav_tree = cache.get('catalog_nav_tree_structured_v1')
        if not nav_tree:
            nav_tree = self._build_nav_tree_from_local()
            cache.set('catalog_nav_tree_structured_v1', nav_tree, 3600)
        
        context['nav_tree'] = nav_tree
        
        # 提取当前筛选名称，用于标题展示
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
        all_products = CatalogProduct.objects.filter(is_published=True).select_related('category').prefetch_related('scenarios', 'characteristics')
        raw_tree = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        sce_names = {}
        type_names = {}
        char_names = {}
        for p in all_products:
            t_id = p.category_id
            type_names[t_id] = p.category.name
            for s in p.scenarios.all():
                s_rem_id = s.remote_id
                sce_names[s_rem_id] = s.name
                for c in p.characteristics.all():
                    c_rem_id = c.remote_id
                    char_names[c_rem_id] = c.name
                    raw_tree[s_rem_id][t_id][c_rem_id] += 1
        tree = []
        for s_rem_id, types in raw_tree.items():
            sce_node = {'id': s_rem_id, 'name': sce_names[s_rem_id], 'count': sum(sum(chars.values()) for chars in types.values()), 'types': []}
            for t_id, chars in types.items():
                type_node = {'id': t_id, 'name': type_names[t_id], 'count': sum(chars.values()), 'characteristics': []}
                for c_rem_id, count in chars.items():
                    type_node['characteristics'].append({'id': c_rem_id, 'name': char_names[c_rem_id], 'count': count})
                sce_node['types'].append(type_node)
            tree.append(sce_node)
        return sorted(tree, key=lambda x: x['name'])

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
                # 触发镜像回退逻辑
                context['api_error'] = True
                context['remote_material'] = self._get_fallback_data()
        except Exception:
            context['api_error'] = True
            context['remote_material'] = self._get_fallback_data()
        return context

    def _get_fallback_data(self):
        """当 API 宕机时，返回本地镜像数据进行兜底展示"""
        return {
            'grade_name': self.object.display_name,
            'description': self.object.description, # 本地镜像描述
            'category': {'name': self.object.category.name},
            'characteristics': [{'name': c.name} for c in self.object.characteristics.all()],
            'manufacturer': 'SUNWILL (Offline Cache)',
            'is_offline': True # 标记为离线模式
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
