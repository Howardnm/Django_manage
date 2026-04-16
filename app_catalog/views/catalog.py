from django.views.generic import ListView, DetailView, TemplateView, View
from django.shortcuts import render, redirect
from django.http import Http404, JsonResponse
from django.core.cache import cache
from django.contrib import messages
from ..models import CatalogProduct, CatalogCategory, VisitorLog, MirrorScenario, MirrorCharacteristic, CatalogMember
from ..services.material_api import client
from ..api.views import push_member_activity_feedback
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

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
        all_products = CatalogProduct.objects.filter(is_published=True).select_related('category').prefetch_related('scenarios', 'characteristics')
        tree_map = {}
        for p in all_products:
            t_id = p.category_id
            t_name = p.category.name
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
        result_tree = []
        for s_id, s_info in tree_map.items():
            sce_node = {'id': s_id, 'name': s_info['name'], 'count': s_info['count'], 'types': []}
            for t_id, t_info in sorted(s_info['types'].items()):
                type_node = {'id': t_id, 'name': t_info['name'], 'count': t_info['count'], 'characteristics': []}
                for c_id, c_info in sorted(t_info['characteristics'].items()):
                    type_node['characteristics'].append({'id': c_id, 'name': c_info['name'], 'count': c_info['count']})
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
            if remote_data: context['remote_material'] = remote_data
            else:
                context['api_error'] = True
                context['remote_material'] = self._get_fallback_data()
        except Exception:
            context['api_error'] = True
            context['remote_material'] = self._get_fallback_data()
        return context

    def _get_fallback_data(self):
        return {'grade_name': self.object.display_name, 'description': self.object.description, 'category': {'name': self.object.category.name}, 'characteristics': [{'name': c.name} for c in self.object.characteristics.all()], 'manufacturer': 'SUNWILL (Offline Cache)', 'is_offline': True}

    def get(self, request, *args, **kwargs):
        product = self.get_object()
        response = super().get(request, *args, **kwargs)
        member_token = self.request.session.get('member_token')
        VisitorLog.objects.create(product=product, visitor_ip=self.request.META.get('REMOTE_ADDR'), member_token=member_token, action='VIEW')
        if member_token: push_member_activity_feedback(member_token, 'VIEW', product.display_name)
        return response

class MemberLoginView(View):
    template_name = 'apps/app_catalog/login.html'
    def get(self, request): return render(request, self.template_name)
    def post(self, request):
        username = request.POST.get('username')
        password = request.POST.get('password')
        auth_res = client.verify_member_credentials(username, password)
        if auth_res.get('status') == 'success':
            remote_user = auth_res['user']
            request.session['is_member_authenticated'] = True
            request.session['member_token'] = remote_user['token']
            request.session['member_role'] = remote_user['role']
            request.session['member_name'] = remote_user['display_name']
            messages.success(request, f"欢迎回来，{remote_user['display_name']}！")
            return redirect('app_catalog:home')
        else:
            messages.error(request, f"登录失败：{auth_res.get('message', '用户名或密码错误')}")
            return render(request, self.template_name)

class MemberLogoutView(View):
    def get(self, request):
        request.session.flush()
        messages.info(request, "您已安全退出")
        return redirect('app_catalog:home')
