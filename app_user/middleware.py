from django.shortcuts import render
from django.urls import reverse

class SecurityShieldMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
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
                # 如果没有授权，渲染防护盾页面
                # 将当前请求的路径传递给模板，以便验证通过后跳转回来
                return render(request, 'shield.html', {'next_url': request.path})

        response = self.get_response(request)
        return response