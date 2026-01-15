from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DetailView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.db.models import Q
from app_project.models import Project
from .models import Customer, MaterialLibrary, ProjectRepository, MaterialType, ApplicationScenario
from .forms import CustomerForm, MaterialForm, ProjectRepositoryForm, MaterialTypeForm, ApplicationScenarioForm
from .utils.filters import CustomerFilter, MaterialFilter
from django.apps import apps
import os


# ==========================================
# 1. 客户库视图 (Customer)
# ==========================================

class CustomerListView(LoginRequiredMixin, ListView):
    model = Customer
    template_name = 'apps/app_repository/customer_list.html'
    context_object_name = 'customers'  # 随便起一个名方便复用分页模板，但不能为 page_obj
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset().order_by('-id')
        # 实例化 Filter
        self.filterset = CustomerFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 传递 filter 对象供前端渲染搜索栏
        context['filter'] = self.filterset
        # 传递 current_sort 供前端渲染表头排序图标
        context['current_sort'] = self.request.GET.get('sort', '')
        return context


class CustomerCreateView(LoginRequiredMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'apps/app_repository/form_generic.html'  # 通用表单模板
    success_url = reverse_lazy('repo_customer_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增客户'
        return context


class CustomerUpdateView(LoginRequiredMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'apps/app_repository/form_generic.html'
    success_url = reverse_lazy('repo_customer_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑客户: {self.object.company_name}'
        return context


# ==========================================
# 2. 材料库视图 (Material)
# ==========================================

class MaterialListView(LoginRequiredMixin, ListView):
    model = MaterialLibrary
    template_name = 'apps/app_repository/material_list.html'
    context_object_name = 'materials'  # 统一变量名
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset().select_related('category', 'scenario').order_by('-created_at')
        self.filterset = MaterialFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        context['current_sort'] = self.request.GET.get('sort', '')
        return context


class MaterialDetailView(LoginRequiredMixin, DetailView):
    model = MaterialLibrary
    template_name = 'apps/app_repository/material_detail.html'
    context_object_name = 'material'  # 模板里用 material 调用

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 【核心优化】
        # 1. select_related: 获取项目和负责人 (Project, User)
        # 2. prefetch_related('project__nodes'): 获取项目节点 (用于计算进度条)
        related_repos = self.object.projectrepository_set.select_related(
            'project', 'project__manager'
        ).prefetch_related(
            'project__nodes'  # <--- 必须加上这句，否则页面会卡顿
        ).order_by('-updated_at')
        context['related_projects'] = [repo.project for repo in related_repos]
        return context

class MaterialCreateView(LoginRequiredMixin, CreateView):
    model = MaterialLibrary
    form_class = MaterialForm
    # 【修改】指向专用模板
    template_name = 'apps/app_repository/material_form.html'
    success_url = reverse_lazy('repo_material_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '录入新材料'
        context['is_edit'] = False
        return context

class MaterialUpdateView(LoginRequiredMixin, UpdateView):
    model = MaterialLibrary
    form_class = MaterialForm
    # 【修改】指向专用模板
    template_name = 'apps/app_repository/material_form.html'
    success_url = reverse_lazy('repo_material_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑材料: {self.object.grade_name}'
        context['is_edit'] = True
        return context


# ==========================================
# 3. 项目档案视图 (Project Repository)
# 这是一个特殊的视图，它是从“项目详情页”跳转过来的
# ==========================================

class ProjectRepositoryUpdateView(LoginRequiredMixin, UpdateView):
    """
    编辑指定项目的档案信息。
    如果该项目还没有档案，会自动创建一个。
    """
    model = ProjectRepository
    form_class = ProjectRepositoryForm
    template_name = 'apps/app_repository/project_repo_form.html'

    # 这里的 object 是通过 project_id 获取的，而不是 repo_id
    def get_object(self, queryset=None):
        project_id = self.kwargs.get('project_id')
        project = get_object_or_404(Project, pk=project_id)

        # get_or_create: 如果存在就获取，不存在就创建
        repo, created = ProjectRepository.objects.get_or_create(project=project)
        return repo

    def form_valid(self, form):
        messages.success(self.request, "项目档案已更新")
        return super().form_valid(form)

    def get_success_url(self):
        # 保存成功后，跳回项目详情页
        return reverse('project_detail', kwargs={'pk': self.object.project.id})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['project'] = self.object.project
        return context


# ==========================================
# 4. 材料类型管理 (MaterialType)
# ==========================================

class MaterialTypeListView(LoginRequiredMixin, ListView):
    model = MaterialType
    template_name = 'apps/app_repository/type_list.html'
    context_object_name = 'types'
    ordering = ['name']

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
        return qs


class MaterialTypeCreateView(LoginRequiredMixin, CreateView):
    model = MaterialType
    form_class = MaterialTypeForm
    template_name = 'apps/app_repository/form_generic.html'  # 复用通用模板
    success_url = reverse_lazy('repo_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增材料类型'
        return context


class MaterialTypeUpdateView(LoginRequiredMixin, UpdateView):
    model = MaterialType
    form_class = MaterialTypeForm
    template_name = 'apps/app_repository/form_generic.html'
    success_url = reverse_lazy('repo_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑类型: {self.object.name}'
        return context


# ==========================================
# 5. 应用场景管理 (ApplicationScenario)
# ==========================================

class ScenarioListView(LoginRequiredMixin, ListView):
    model = ApplicationScenario
    template_name = 'apps/app_repository/scenario_list.html'
    context_object_name = 'scenarios'
    ordering = ['name']

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(requirements__icontains=q))
        return qs


class ScenarioCreateView(LoginRequiredMixin, CreateView):
    model = ApplicationScenario
    form_class = ApplicationScenarioForm
    template_name = 'apps/app_repository/form_generic.html'
    success_url = reverse_lazy('repo_scenario_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增应用场景'
        return context


class ScenarioUpdateView(LoginRequiredMixin, UpdateView):
    model = ApplicationScenario
    form_class = ApplicationScenarioForm
    template_name = 'apps/app_repository/form_generic.html'
    success_url = reverse_lazy('repo_scenario_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑场景: {self.object.name}'
        return context


class SecureFileDownloadView(LoginRequiredMixin, View):
    """
    通用安全文件下载视图
    URL格式: /repository/download/<app_label>/<model_name>/<pk>/<field_name>/
    """

    def get(self, request, app_label, model_name, pk, field_name):
        # 1. 动态获取模型
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            raise Http404("模型不存在")

        # 2. 获取对象
        try:
            obj = model.objects.get(pk=pk)
        except model.DoesNotExist:
            raise Http404("文件记录不存在")

        # 3. 权限检查 (可选：更细粒度的检查)
        # 例如：如果是 'app_project' 下的文件，检查用户是否属于该项目组
        # if app_label == 'app_project' and not request.user.has_perm(...):
        #     return HttpResponseForbidden("您无权下载此文件")

        # 4. 获取文件字段
        if not hasattr(obj, field_name):
            raise Http404("字段不存在")

        file_field = getattr(obj, field_name)

        # 5. 检查文件是否存在
        if not file_field:
            raise Http404("未上传文件")

        try:
            # 6. 返回文件流 (FileResponse 会自动处理断点续传和 Content-Type)
            # as_attachment=False 表示尝试在浏览器内预览(如PDF)，True表示强制下载
            response = FileResponse(file_field.open('rb'), as_attachment=False)
            return response
        except FileNotFoundError:
            raise Http404("物理文件丢失")
