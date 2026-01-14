from django.urls import path
from django.contrib.auth.views import LogoutView
from .views import CustomLoginView, RegisterView, ProfileView

urlpatterns = [
    path('login/', CustomLoginView.as_view(), name='login'),
    # LogoutView 只要 POST 请求就会注销，Django 5.0+ 推荐这种写法
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),
    path('register/', RegisterView.as_view(), name='register'),
    path('profile/', ProfileView.as_view(), name='user_profile'),
]