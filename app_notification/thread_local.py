from threading import local

_thread_locals = local()

def get_current_user():
    """
    返回当前请求的用户。
    """
    return getattr(_thread_locals, 'user', None)

def set_current_user(user):
    """
    在中间件中设置当前请求的用户。
    """
    _thread_locals.user = user

def unset_current_user():
    """
    在请求结束后清理用户，防止数据泄露。
    """
    if hasattr(_thread_locals, 'user'):
        del _thread_locals.user
