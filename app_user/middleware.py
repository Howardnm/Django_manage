import uuid
from django.shortcuts import render, redirect
from django.urls import reverse

class SecurityShieldMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 如果是访问 admin 登录页，直接重定向到主登录页
        if request.path == reverse('admin:login'):
            return redirect('login')

        # 定义需要防护的路径 (登录、注册、重置密码)
        # 注意：不要包含静态文件、验证码接口、验证接口本身
        protected_paths = [
            reverse('login'),
            reverse('register'),
            reverse('password_reset'),
            reverse('register_success'),
        ]

        # 如果请求的路径在保护列表中
        if request.path in protected_paths:
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