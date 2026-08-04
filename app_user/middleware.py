"""安全中间件。拦截登录/注册页面，要求浏览器滑动验证通过后才放行。

导出: SecurityShieldMiddleware。
"""

import uuid
from django.shortcuts import render, redirect
from django.urls import reverse, NoReverseMatch


class SecurityShieldMiddleware:
    """浏览器验证盾中间件。对 login/register/reset-password 页面检查 session 中的 access_granted 标记，未通过则展示滑动验证页。"""
    def __init__(self, get_response):
        """缓存受保护路径列表和管理登录 URL，避免每次请求调用 reverse。Args: get_response: 下一个中间件/视图的可调用对象。"""
        self.get_response = get_response
        try:
            self.admin_login = reverse('admin:login')
        except NoReverseMatch:
            self.admin_login = '/admin/login/'
        self.protected_paths = []
        for name in ['login', 'register', 'password_reset', 'register_success']:
            try:
                self.protected_paths.append(reverse(name))
            except NoReverseMatch:
                pass

    def __call__(self, request):
        """拦截请求：将 admin login 重定向到主登录页；对受保护路径检查 access_granted。Args: request: HttpRequest。Returns: HttpResponse。"""
        # 如果是访问 admin 登录页，直接重定向到主登录页
        if request.path == self.admin_login:
            return redirect('login')

        # 如果请求的路径在保护列表中
        # 注意：不要包含静态文件、验证码接口、验证接口本身
        if request.path in self.protected_paths:
            # 检查 Session 中是否有访问授权标记
            if not request.session.get('access_granted', False):
                # --- Nonce 生成 ---
                # 1. 生成一个唯一的一次性令牌
                nonce = uuid.uuid4().hex
                # 2. 将令牌存储在 session 中
                request.session['shield_nonce'] = nonce
                
                # 3. 将令牌和目标URL传递给模板
                context = {
                    'next_url': request.path,
                    'nonce': nonce,
                }
                return render(request, 'shield.html', context)

        response = self.get_response(request)
        return response