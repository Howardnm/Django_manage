"""电子手册视图：纯前端展示层，所有数据实时经 CatalogGateway 拉取主系统。"""
import logging

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from .services.gateway import CatalogGateway, UpstreamError, get_gateway

logger = logging.getLogger(__name__)

PER_PAGE = 10


class MemberRequiredMixin:
    """要求会员会话已通过主系统鉴权；未登录跳转登录页。"""

    def dispatch(self, request, *args, **kwargs):
        if not request.session.get('member_token'):
            login_url = reverse('app_catalog:login')
            return redirect(f"{login_url}?next={request.path}")
        return super().dispatch(request, *args, **kwargs)


class CatalogListView(View):
    """目录列表：公开浏览，支持场景/类型/特征/关键词筛选与分页。"""
    template_name = 'app_catalog/product_list.html'

    def get(self, request):
        page = self._parse_page(request.GET.get('page'))
        s_id, t_id, c_id, q = (
            request.GET.get('s'), request.GET.get('t'),
            request.GET.get('c'), request.GET.get('q'),
        )

        params = {'page': page}
        if s_id:
            params['scenarios'] = s_id
        if t_id:
            params['category'] = t_id
        if c_id:
            params['characteristics'] = c_id
        if q:
            params['search'] = q

        gateway = get_gateway()
        try:
            nav_tree = gateway.nav_tree()
            data = gateway.materials(**params)
        except UpstreamError as e:
            messages.error(request, str(e))
            nav_tree, data = [], {'count': 0, 'results': []}

        results = data.get('results', [])
        count = data.get('count', 0)
        page_obj = Paginator([None] * count, PER_PAGE).get_page(page)

        current_s_obj, current_t_obj, current_c_obj = self._resolve_current(
            nav_tree, s_id, t_id, c_id
        )

        return render(request, self.template_name, {
            'products': results,
            'page_obj': page_obj,
            'is_paginated': page_obj.paginator.num_pages > 1,
            'nav_tree': nav_tree,
            'current_s': s_id,
            'current_t': t_id,
            'current_c': c_id,
            'current_s_obj': current_s_obj,
            'current_t_obj': current_t_obj,
            'current_c_obj': current_c_obj,
        })

    @staticmethod
    def _parse_page(raw):
        try:
            return max(int(raw), 1)
        except (TypeError, ValueError):
            return 1

    @staticmethod
    def _resolve_current(nav_tree, s_id, t_id, c_id):
        """从导航树中解析当前选中 id 的名称（供面包屑与标题）。"""
        s_map, t_map, c_map = {}, {}, {}
        for sce in nav_tree:
            s_map[str(sce['id'])] = sce['name']
            for type_node in sce.get('types', []):
                t_map[str(type_node['id'])] = type_node['name']
                for char in type_node.get('characteristics', []):
                    c_map[str(char['id'])] = char['name']

        def lookup(name_map, key):
            if key and str(key) in name_map:
                return {'name': name_map[str(key)]}
            return None

        return lookup(s_map, s_id), lookup(t_map, t_id), lookup(c_map, c_id)


class CatalogDetailView(View):
    """产品详情：公开浏览，物性数值与文档仅登录后解锁。"""
    template_name = 'app_catalog/product_detail.html'

    def get(self, request, pk):
        gateway = get_gateway()
        member_token = request.session.get('member_token')
        try:
            material = gateway.material(pk, member_token=member_token)
        except UpstreamError as e:
            messages.error(request, str(e))
            return redirect('app_catalog:home')

        if member_token:
            target = material.get('display_name') or material.get('grade_name', '')
            gateway.push_feedback(member_token, 'VIEW', target)

        return render(request, self.template_name, {
            'product': material,
            'remote_material': material,
            'api_error': False,
        })


class MemberLoginView(View):
    """会员登录：实时调用主系统鉴权。"""
    template_name = 'app_catalog/login.html'

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        email = request.POST.get('email')
        password = request.POST.get('password')

        try:
            auth_res = get_gateway().verify(email, password)
        except UpstreamError as e:
            messages.error(request, str(e))
            return render(request, self.template_name)

        if auth_res.get('status') == 'success':
            user_data = auth_res['user']
            request.session.update({
                'is_member_authenticated': True,
                'member_token': user_data['token'],
                'member_name': user_data['display_name'],
                'user_type': user_data.get('user_type'),
                'user_level': user_data.get('user_level'),
                'dept_code': user_data.get('dept_code'),
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


class MaterialDownloadView(MemberRequiredMixin, View):
    """文档中转下载：代理主系统文件流，并回流下载行为。"""

    def get(self, request, pk, file_type):
        gateway = get_gateway()
        member_token = request.session.get('member_token')

        display_name = ''
        try:
            material = gateway.material(pk, member_token=member_token)
            display_name = material.get('display_name') or material.get('grade_name', '')
        except UpstreamError:
            pass

        try:
            response = gateway.file_stream(pk, file_type, member_token=member_token)
        except UpstreamError as e:
            raise Http404(str(e))

        if response.status_code != 200:
            raise Http404(f"主系统当前无法提供 {file_type.upper()} 文件，请稍后再试。")

        gateway.push_feedback(member_token, f"DOWNLOAD_{file_type.upper()}", display_name)

        proxy_response = StreamingHttpResponse(
            response.iter_content(chunk_size=8192),
            content_type=response.headers.get('Content-Type', 'application/pdf'),
        )
        content_disposition = response.headers.get('Content-Disposition')
        if content_disposition:
            proxy_response['Content-Disposition'] = content_disposition
        else:
            filename = f"{display_name or pk}_{file_type.upper()}.pdf"
            proxy_response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return proxy_response
