from .thread_local import set_current_user, unset_current_user

class CurrentUserMiddleware:
    """
    一个中间件，用于在每个请求中捕获当前登录的用户，
    以便信号处理器等无法直接访问 request 的地方可以使用。
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 在视图处理前，设置当前用户
        set_current_user(getattr(request, 'user', None))
        
        response = self.get_response(request)
        
        # 在响应返回后，清理当前用户
        unset_current_user()
        
        return response
