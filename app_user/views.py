# apps/app_user/views.py
from django.shortcuts import render, redirect
from django.contrib.auth.views import LoginView, LogoutView
from django.views.generic import CreateView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from .forms import UserLoginForm, UserRegisterForm, UserUpdateForm, ProfileUpdateForm


# 1. 登录 (直接继承内置视图)
class CustomLoginView(LoginView):
    template_name = 'apps/app_user/login.html'
    authentication_form = UserLoginForm
    redirect_authenticated_user = True  # 如果已登录，直接跳走


# 2. 注册
class RegisterView(CreateView):
    template_name = 'apps/app_user/register.html'
    form_class = UserRegisterForm
    success_url = reverse_lazy('login')  # 注册成功跳登录

    def form_valid(self, form):
        messages.success(self.request, "注册成功，请登录")
        return super().form_valid(form)


# 3. 个人中心 (查看 + 修改)
class ProfileView(LoginRequiredMixin, View):
    template_name = 'apps/app_user/profile.html'

    def get(self, request):
        user_form = UserUpdateForm(instance=request.user)
        profile_form = ProfileUpdateForm(instance=request.user.profile)

        context = {
            'user_form': user_form,
            'profile_form': profile_form
        }
        return render(request, self.template_name, context)

    def post(self, request):
        user_form = UserUpdateForm(request.POST, instance=request.user)
        profile_form = ProfileUpdateForm(request.POST, instance=request.user.profile)

        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, "个人资料已更新！")
            return redirect('user_profile')

        context = {
            'user_form': user_form,
            'profile_form': profile_form
        }
        return render(request, self.template_name, context)