from django.views.generic import ListView, DetailView, View
from django.shortcuts import render, redirect
from django.core.cache import cache
from django.contrib import messages
from ..models import CatalogProduct, CatalogCategory, VisitorLog, MirrorScenario, MirrorCharacteristic
from ..services.material_api import client
from ..services.feedback_service import FeedbackService
import logging

logger = logging.getLogger(__name__)

class CatalogListView(ListView):
    """
    手册产品列表：展示已发布的材料镜像。
    """
    model = CatalogProduct
    template_name = 'apps/app_catalog/product_list.html'
    context_object_name = 'products'
    paginate_by = 10

    def get_queryset(self):
        # 仅显示已发布产品
        qs = CatalogProduct.objects.filter(is_published=True).select_related('category').prefetch_related('scenarios', 'characteristics')
        
        # 基础过滤
        s_id, t_id, c_id = self.request.GET.get('s'), self.request.GET.get('t'), self.request.GET.get('c')
        q = self.request.GET.get('q')
        
        if s_id: qs = qs.filter(scenarios__remote_id=s_id)
        if c_id: qs = qs.filter(characteristics__remote_id=c_id)
        if t_id: qs = qs.filter(category_id=t_id)
        if q: qs = qs.filter(display_name__icontains=q)
        
        return qs.distinct().order_by('-published_at', '-id')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 获取导航树 (带缓存)
        context['nav_tree'] = self._get_cached_nav_tree()
        
        # 当前选中状态
        s_id, t_id, c_id = self.request.GET.get('s'), self.request.GET.get('t'), self.request.GET.get('c')
        context.update({
            'current_s_obj': MirrorScenario.objects.filter(remote_id=s_id).first() if s_id else None,
            'current_t_obj': CatalogCategory.objects.filter(pk=t_id).first() if t_id else None,
            'current_c_obj': MirrorCharacteristic.objects.filter(remote_id=c_id).first() if c_id else None,
            'current_s': s_id, 'current_t': t_id, 'current_c': c_id
        })
        return context

    def _get_cached_nav_tree(self):
        cache_key = 'catalog_nav_tree_v2'
        tree = cache.get(cache_key)
        if not tree:
            tree = self._build_nav_tree()
            cache.set(cache_key, tree, 3600)
        return tree

    def _build_nav_tree(self):
        """构建结构化的分类导航树"""
        all_products = CatalogProduct.objects.filter(is_published=True).select_related('category').prefetch_related('scenarios', 'characteristics')
        tree_map = {}
        for p in all_products:
            t_id, t_name = p.category_id, p.category.name
            for s in p.scenarios.all():
                s_id = s.remote_id
                if s_id not in tree_map: tree_map[s_id] = {'name': s.name, 'count': 0, 'types': {}}
                if t_id not in tree_map[s_id]['types']: tree_map[s_id]['types'][t_id] = {'name': t_name, 'count': 0, 'characteristics': {}}
                tree_map[s_id]['count'] += 1
                tree_map[s_id]['types'][t_id]['count'] += 1
                for c in p.characteristics.all():
                    c_id = c.remote_id
                    if c_id not in tree_map[s_id]['types'][t_id]['characteristics']: tree_map[s_id]['types'][t_id]['characteristics'][c_id] = {'name': c.name, 'count': 0}
                    tree_map[s_id]['types'][t_id]['characteristics'][c_id]['count'] += 1
        
        result = []
        for s_id, s_info in tree_map.items():
            sce_node = {'id': s_id, 'name': s_info['name'], 'count': s_info['count'], 'types': []}
            for t_id, t_info in sorted(s_info['types'].items()):
                type_node = {'id': t_id, 'name': t_info['name'], 'count': t_info['count'], 'characteristics': []}
                for c_id, c_info in sorted(t_info['characteristics'].items()):
                    type_node['characteristics'].append({'id': c_id, 'name': c_info['name'], 'count': c_info['count']})
                sce_node['types'].append(type_node)
            result.append(sce_node)
        return sorted(result, key=lambda x: x['name'])


class CatalogDetailView(DetailView):
    """
    产品详情：
    - 基础信息：从本地镜像获取。
    - 实时性能/文件：从主系统 API 实时抓取。
    """
    model = CatalogProduct
    template_name = 'apps/app_catalog/product_detail.html'
    context_object_name = 'product'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 低代码调用 Service 抓取详情
        remote_data = client.fetch_material_details(self.object.remote_material_id)
        
        if remote_data:
            context['remote_material'] = remote_data
        else:
            context['api_error'] = True
            context['remote_material'] = self._get_fallback_data()
        return context

    def _get_fallback_data(self):
        """离线兜底数据"""
        return {
            'grade_name': self.object.display_name, 'description': self.object.description,
            'category': {'name': self.object.category.name},
            'characteristics': [{'name': c.name} for c in self.object.characteristics.all()],
            'manufacturer': 'SUNWILL (Offline Cache)', 'is_offline': True
        }

    def get(self, request, *args, **kwargs):
        product = self.get_object()
        response = super().get(request, *args, **kwargs)
        member_token = self.request.session.get('member_token')
        
        # 日志与行为回传
        VisitorLog.objects.create(product=product, visitor_ip=self.request.META.get('REMOTE_ADDR'), member_token=member_token, action='VIEW')
        if member_token:
            FeedbackService.push_activity(member_token, 'VIEW', product.display_name)
        return response


class MemberLoginView(View):
    """会员登录：基于主系统 API 鉴权"""
    template_name = 'apps/app_catalog/login.html'
    
    def get(self, request): return render(request, self.template_name)
    
    def post(self, request):
        username, password = request.POST.get('username'), request.POST.get('password')
        # 低代码 Service 调用
        auth_res = client.verify_credentials(username, password)
        
        if auth_res.get('status') == 'success':
            user_data = auth_res['user']
            # 建立 Session (最小化数据原则)
            request.session.update({
                'is_member_authenticated': True,
                'member_token': user_data['token'],
                'member_role': user_data['role'],
                'member_name': user_data['display_name'],
                # 存储 4D 权限因子于内存
                'user_type': user_data.get('user_type'),
                'user_level': user_data.get('user_level'),
                'dept_code': user_data.get('dept_code')
            })
            messages.success(request, f"欢迎回来，{user_data['display_name']}！")
            return redirect('app_catalog:home')
        
        messages.error(request, f"登录失败：{auth_res.get('message', '账号或密码错误')}")
        return render(request, self.template_name)


class MemberLogoutView(View):
    def get(self, request):
        request.session.flush()
        messages.info(request, "您已安全退出")
        return redirect('app_catalog:home')
