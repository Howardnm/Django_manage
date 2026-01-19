from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, UpdateView, CreateView
from django.db.models import Q
from app_repository.forms import ProjectRepositoryForm, ProjectFileForm
from app_repository.utils.filters import ProjectRepositoryFilter
from app_project.models import Project
from app_repository.models import ProjectRepository, ProjectFile
from app_repository.models import MaterialLibrary, Customer, OEM, Salesperson
from app_project.mixins import ProjectPermissionMixin


# ==========================================
# 3. 项目档案视图 (Project Repository)
# ==========================================

# 8. 项目档案总览列表 (已修复，保持不变)
class ProjectRepositoryListView(LoginRequiredMixin, ProjectPermissionMixin, ListView):
    model = ProjectRepository
    template_name = 'apps/app_repository/project_repo/repo_list.html'
    context_object_name = 'repos'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            'project',
            'project__manager',
            'customer',
            'oem',
            'material',
            'salesperson'
        ).prefetch_related('files').order_by('-updated_at')

        qs = self.get_permitted_queryset(qs, manager_field='project__manager')
        self.filterset = ProjectRepositoryFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        context['current_sort'] = self.request.GET.get('sort', '')
        return context


# 1. 档案基本信息编辑 (UpdateView)
class ProjectRepositoryUpdateView(LoginRequiredMixin, ProjectPermissionMixin, UpdateView):
    model = ProjectRepository
    form_class = ProjectRepositoryForm
    template_name = 'apps/app_repository/project_repo/project_repo_form.html'

    def get_object(self, queryset=None):
        project_id = self.kwargs.get('project_id')
        project = get_object_or_404(Project, pk=project_id)
        
        # 【安全修复】检查权限
        self.check_project_permission(project)
        
        repo, created = ProjectRepository.objects.get_or_create(project=project)
        return repo

    def form_valid(self, form):
        messages.success(self.request, "项目档案基础信息已更新")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('project_detail', kwargs={'pk': self.object.project.id})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['project'] = self.object.project
        return context


# 2. 图纸文件上传视图
class ProjectFileUploadView(LoginRequiredMixin, ProjectPermissionMixin, CreateView):
    model = ProjectFile
    form_class = ProjectFileForm
    template_name = 'apps/app_repository/project_repo/project_file_form.html'

    def dispatch(self, request, *args, **kwargs):
        # 【安全修复】在 dispatch 阶段就检查权限
        # 因为 get_context_data 和 form_valid 都会用到 repo，不如直接在这里查一次
        repo_id = self.kwargs.get('repo_id')
        self.repo = get_object_or_404(ProjectRepository, pk=repo_id)
        
        # 检查关联项目的权限
        self.check_project_permission(self.repo.project)
        
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 直接使用 dispatch 里查到的 self.repo
        context['repo'] = self.repo
        context['page_title'] = '上传项目资料'
        return context

    def form_valid(self, form):
        # 直接使用 dispatch 里查到的 self.repo
        form.instance.repository = self.repo
        messages.success(self.request, "文件上传成功")
        return super().form_valid(form)

    def get_success_url(self):
        # 【修改】上传成功后，跳转回项目详情页
        return reverse('project_detail', kwargs={'pk': self.object.repository.project.id})


# 3. 文件删除视图
class ProjectFileDeleteView(LoginRequiredMixin, ProjectPermissionMixin, View):
    def post(self, request, pk):
        file_obj = get_object_or_404(ProjectFile, pk=pk)
        project = file_obj.repository.project
        
        # 【安全修复】检查权限
        self.check_project_permission(project)
        
        project_id = project.id
        file_obj.delete()
        messages.success(request, "文件已删除")
        return redirect('project_detail', pk=project_id)


class RepoAutocompleteView(LoginRequiredMixin, View):
    """
    通用搜索接口，用于 Select 下拉框的异步加载
    URL: /repository/api/search/?model=material&q=keyword
    """
    # 这个接口只返回基础数据（材料、客户等），不涉及项目敏感信息，
    # 且通常所有登录用户都有权查看基础库，所以不需要 ProjectPermissionMixin。
    
    def get(self, request):
        model_type = request.GET.get('model')
        query = request.GET.get('q', '')

        data = []
        qs = None

        if model_type == 'material':
            qs = MaterialLibrary.objects.all()
            if query:
                qs = qs.filter(Q(grade_name__icontains=query) | Q(manufacturer__icontains=query))
            qs = qs.values('id', 'grade_name', 'manufacturer')[:20]
            data = [{'value': item['id'], 'text': f"{item['grade_name']} ({item['manufacturer']})"} for item in qs]

        elif model_type == 'customer':
            qs = Customer.objects.all()
            if query:
                qs = qs.filter(company_name__icontains=query)
            qs = qs.values('id', 'company_name')[:20]
            data = [{'value': item['id'], 'text': item['company_name']} for item in qs]

        elif model_type == 'oem':
            qs = OEM.objects.all()
            if query:
                qs = qs.filter(name__icontains=query)
            qs = qs.values('id', 'name')[:20]
            data = [{'value': item['id'], 'text': item['name']} for item in qs]

        elif model_type == 'salesperson':
            qs = Salesperson.objects.all()
            if query:
                qs = qs.filter(name__icontains=query)
            qs = qs.values('id', 'name')[:20]
            data = [{'value': item['id'], 'text': item['name']} for item in qs]

        return JsonResponse(data, safe=False)
