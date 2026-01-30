from django.urls import path
from django.contrib.auth.views import LogoutView
from .views import CustomLoginView, RegisterView, ProfileView, captcha_view, send_email_code, RegisterSuccessView, PasswordResetView, verify_browser

urlpatterns = [
    path('login/', CustomLoginView.as_view(), name='login'),
    # LogoutView 只要 POST 请求就会注销，Django 5.0+ 推荐这种写法
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),
    path('register/', RegisterView.as_view(), name='register'),
    path('register/success/', RegisterSuccessView.as_view(), name='register_success'),
    path('password-reset/', PasswordResetView.as_view(), name='password_reset'),
    path('profile/', ProfileView.as_view(), name='user_profile'),
    path('captcha/', captcha_view, name='captcha'),
    path('send_email_code/', send_email_code, name='send_email_code'),
    path('verify_browser/', verify_browser, name='verify_browser'),
]