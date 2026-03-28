from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, UpdateView, CreateView, DetailView
from django.db.models import Q, Count
from app_repository.forms import ProjectRepositoryForm, ProjectFileForm
from app_repository.utils.filters import ProjectRepositoryFilter
from app_project.models import Project, ProjectNode
from app_repository.models import ProjectRepository, ProjectFile
from app_repository.models import MaterialLibrary, Customer, OEM, Salesperson, TestConfig, MaterialType, ApplicationScenario # 导入 ApplicationScenario
from app_project.mixins import ProjectPermissionMixin
from app_process.models import ProcessProfile
from app_raw_material.models import RawMaterial
from app_basic_research.models import ResearchProject
from django.contrib.auth.models import User


# ==========================================
# 3. 项目档案视图 (Project Repository)
# ==========================================

# 8. 项目档案总览列表 (已修复，保持不变)
class ProjectRepositoryListView(LoginRequiredMixin, PermissionRequiredMixin, ProjectPermissionMixin, ListView):
    permission_required = 'app_repository.view_projectrepository'
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
class ProjectRepositoryUpdateView(LoginRequiredMixin, PermissionRequiredMixin, ProjectPermissionMixin, UpdateView):
    permission_required = 'app_repository.change_projectrepository'
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


# 【新增】项目资料详细页面
class ProjectFileDetailView(LoginRequiredMixin, PermissionRequiredMixin, ProjectPermissionMixin, DetailView):
    permission_required = 'app_repository.view_projectrepository'
    model = ProjectRepository
    template_name = 'apps/app_repository/project_repo/project_file_detail.html'
    context_object_name = 'repo'

    def get_object(self, queryset=None):
        repo = super().get_object(queryset)
        self.check_project_permission(repo.project)
        return repo

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 按节点分组文件
        files = self.object.files.all().select_related('node').order_by('node__order', '-uploaded_at')
        
        # 使用列表存储分组，包含节点对象，方便模板访问属性
        grouped_list = []
        node_map = {} # node_id -> index in grouped_list
        general_files = []
        
        for file in files:
            if file.node:
                if file.node.id not in node_map:
                    node_map[file.node.id] = len(grouped_list)
                    grouped_list.append({
                        'node': file.node,
                        'files': []
                    })
                idx = node_map[file.node.id]
                grouped_list[idx]['files'].append(file)
            else:
                general_files.append(file)
        
        context['grouped_files'] = grouped_list # 现在是列表
        context['general_files'] = general_files
        context['project'] = self.object.project
        return context


# 2. 文件上传视图
class ProjectFileUploadView(LoginRequiredMixin, PermissionRequiredMixin, ProjectPermissionMixin, CreateView):
    permission_required = 'app_repository.add_projectfile'
    model = ProjectFile
    form_class = ProjectFileForm
    template_name = 'apps/app_repository/project_repo/project_file_form.html'

    def dispatch(self, request, *args, **kwargs):
        repo_id = self.kwargs.get('repo_id')
        self.repo = get_object_or_404(ProjectRepository, pk=repo_id)
        self.check_project_permission(self.repo.project)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['repository'] = self.repo
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        node_id = self.request.GET.get('node_id')
        if node_id:
            initial['node'] = node_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['repo'] = self.repo
        context['page_title'] = '上传项目资料'
        return context

    def get_template_names(self):
        # 修复模态框内容不显示的问题：明确区分普通页面请求和 HTMX 模态框请求
        if self.request.headers.get('HX-Request'):
            return ['apps/app_repository/project_repo/modal_project_file_form.html']
        return [self.template_name]

    def form_valid(self, form):
        form.instance.repository = self.repo
        self.object = form.save()
        
        if self.request.headers.get('HX-Request'):
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
            
        messages.success(self.request, "文件上传成功")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('project_detail', kwargs={'pk': self.object.repository.project.id})


# 3. 文件删除视图
class ProjectFileDeleteView(LoginRequiredMixin, PermissionRequiredMixin, ProjectPermissionMixin, View):
    permission_required = 'app_repository.delete_projectfile'

    def post(self, request, pk):
        file_obj = get_object_or_404(ProjectFile, pk=pk)
        project = file_obj.repository.project
        self.check_project_permission(project)
        
        file_obj.delete()
        messages.success(request, "文件已删除")
        
        # 支持从不同页面返回
        next_url = request.META.get('HTTP_REFERER', reverse('project_detail', kwargs={'pk': project.id}))
        return redirect(next_url)


class RepoAutocompleteView(LoginRequiredMixin, View):
    """
    通用搜索接口，用于 Select 下拉框的异步加载
    URL: /repository/api/search/?model=material&q=keyword
    """
    # 这个接口只返回基础数据（材料、客户等），不涉及项目敏感信息，
    #且通常所有登录用户都有权查看基础库，所以不需要 ProjectPermissionMixin。
    
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
                qs = qs.filter(Q(name__icontains=query) | Q(short_name__icontains=query))
            qs = qs.values('id', 'name', 'short_name')[:20]
            # 【修改】显示格式：名称 (简称)
            data = [{'value': item['id'], 'text': f"{item['name']} ({item['short_name']})" if item['short_name'] else item['name']} for item in qs]

        elif model_type == 'salesperson':
            qs = Salesperson.objects.all()
            if query:
                qs = qs.filter(name__icontains=query)
            qs = qs.values('id', 'name')[:20]
            data = [{'value': item['id'], 'text': item['name']} for item in qs]
            
        # 【新增】工艺方案搜索
        elif model_type == 'process':
            qs = ProcessProfile.objects.all()
            if query:
                qs = qs.filter(name__icontains=query)
            qs = qs.values('id', 'name')[:20]
            data = [{'value': item['id'], 'text': item['name']} for item in qs]
            
        # 【新增】原材料搜索
        elif model_type == 'raw_material':
            qs = RawMaterial.objects.select_related('category').all()
            if query:
                qs = qs.filter(Q(name__icontains=query) | Q(model_name__icontains=query))
            qs = qs.values('id', 'name', 'model_name', 'category__name')[:20]
            # 【修改】单行显示：名称 型号 (类别)
            data = [{'value': item['id'], 'text': f"{item['name']} {item['model_name'] or ''} ({item['category__name']})"} for item in qs]

        # 【新增】测试标准搜索
        elif model_type == 'test_config':
            qs = TestConfig.objects.select_related('category').all()
            if query:
                qs = qs.filter(Q(name__icontains=query) | Q(standard__icontains=query))
            qs = qs.values('id', 'name', 'standard', 'condition', 'category__name')[:20]
            # 【修改】单行显示：[分类] 名称 - 标准 (条件)
            data = []
            for item in qs:
                cond_str = f" ({item['condition']})" if item['condition'] else ""
                text = f"[{item['category__name']}] {item['name']} - {item['standard']}{cond_str}"
                data.append({'value': item['id'], 'text': text})

        # 【新增】预研项目搜索
        elif model_type == 'research_project':
            qs = ResearchProject.objects.all()
            if query:
                qs = qs.filter(Q(code__icontains=query) | Q(name__icontains=query))
            qs = qs.values('id', 'code', 'name')[:20]
            data = [{'value': item['id'], 'text': f"{item['code']} {item['name']}"} for item in qs]

        # 【新增】用户搜索
        elif model_type == 'user':
            qs = User.objects.filter(is_active=True)
            if query:
                qs = qs.filter(Q(username__icontains=query) | Q(first_name__icontains=query))
            qs = qs.values('id', 'username', 'first_name')[:20]
            data = [{'value': item['id'], 'text': f"{item['first_name'] or item['username']}"} for item in qs]

        # 【新增】应用场景搜索
        elif model_type == 'applicationscenario':
            qs = ApplicationScenario.objects.all()
            if query:
                qs = qs.filter(name__icontains=query)
            qs = qs.values('id', 'name')[:20]
            data = [{'value': item['id'], 'text': item['name']} for item in qs]

        return JsonResponse(data, safe=False)
