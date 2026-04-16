from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, UpdateView, CreateView, DetailView
from django.db.models import Q
from django.contrib.auth import get_user_model
from app_repository.forms import ProjectRepositoryForm, ProjectFileForm
from app_repository.utils.filters import ProjectRepositoryFilter
from app_project.models import Project
from app_repository.models import ProjectRepository, ProjectFile, Customer, OEM
from app_project.mixins import ProjectPermissionMixin

User = get_user_model()

# ==========================================
# 3. 项目档案视图 (Project Repository)
# ==========================================

class ProjectRepositoryListView(LoginRequiredMixin, PermissionRequiredMixin, ProjectPermissionMixin, ListView):
    permission_required = 'app_repository.view_projectrepository'
    model = ProjectRepository
    template_name = 'apps/app_repository/project_repo/repo_list.html'
    context_object_name = 'repos'
    paginate_by = 10

    def get_queryset(self):
        # 1. 基础查询
        qs = super().get_queryset().select_related(
            'project', 'project__manager', 'customer', 'oem', 'material', 'salesperson'
        ).prefetch_related('files').order_by('-updated_at')
        
        # 2. 调用项目权限 Mixin 过滤 (管控研发层面的权限)
        qs = self.get_permitted_queryset(qs, manager_field='project__manager')
        
        # 3. 【权限隔离】业务员层面的行级隔离 (直接对比 User)
        if not self.request.user.is_superuser:
            # 只要不是超管，就只能看自己作为业务员负责的项目
            qs = qs.filter(salesperson=self.request.user)

        self.filterset = ProjectRepositoryFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        context['current_sort'] = self.request.GET.get('sort', '')
        return context


class ProjectRepositoryUpdateView(LoginRequiredMixin, PermissionRequiredMixin, ProjectPermissionMixin, UpdateView):
    permission_required = 'app_repository.change_projectrepository'
    model = ProjectRepository
    form_class = ProjectRepositoryForm
    template_name = 'apps/app_repository/project_repo/project_repo_form.html'

    def get_object(self, queryset=None):
        project_id = self.kwargs.get('project_id')
        project = get_object_or_404(Project, pk=project_id)
        self.check_project_permission(project)
        repo, created = ProjectRepository.objects.get_or_create(project=project)
        
        # 【越权检查】直接基于 request.user
        if not self.request.user.is_superuser:
            if repo.salesperson and repo.salesperson != self.request.user:
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied("您无权编辑其他业务员负责的项目档案")
                
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


class ProjectFileDetailView(LoginRequiredMixin, PermissionRequiredMixin, ProjectPermissionMixin, DetailView):
    permission_required = 'app_repository.view_projectrepository'
    model = ProjectRepository
    template_name = 'apps/app_repository/project_repo/project_file_detail.html'
    context_object_name = 'repo'

    def get_object(self, queryset=None):
        repo = super().get_object(queryset)
        self.check_project_permission(repo.project)
        
        # 【越权检查】
        if not self.request.user.is_superuser:
            if repo.salesperson and repo.salesperson != self.request.user:
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied("您无权查看该项目的详细资料")
                
        return repo

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        files = self.object.files.all().select_related('node').order_by('node__order', '-uploaded_at')
        grouped_list = []
        node_map = {}
        general_files = []
        for file in files:
            if file.node:
                if file.node.id not in node_map:
                    node_map[file.node.id] = len(grouped_list)
                    grouped_list.append({'node': file.node, 'files': []})
                idx = node_map[file.node.id]
                grouped_list[idx]['files'].append(file)
            else:
                general_files.append(file)
        context['grouped_files'] = grouped_list
        context['general_files'] = general_files
        context['project'] = self.object.project
        return context


class ProjectFileUploadView(LoginRequiredMixin, PermissionRequiredMixin, ProjectPermissionMixin, CreateView):
    permission_required = 'app_repository.add_projectfile'
    model = ProjectFile
    form_class = ProjectFileForm
    template_name = 'apps/app_repository/project_repo/project_file_form.html'

    def dispatch(self, request, *args, **kwargs):
        repo_id = self.kwargs.get('repo_id')
        self.repo = get_object_or_404(ProjectRepository, pk=repo_id)
        self.check_project_permission(self.repo.project)
        
        # 【越权检查】
        if not self.request.user.is_superuser:
            if self.repo.salesperson and self.repo.salesperson != self.request.user:
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied("您无权为其他业务员的项目上传资料")
                
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['repository'] = self.repo
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        node_id = self.request.GET.get('node_id')
        if node_id: initial['node'] = node_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['repo'] = self.repo
        context['page_title'] = '上传项目资料'
        return context

    def get_template_names(self):
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


class ProjectFileDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'app_repository.delete_projectfile'

    def post(self, request, pk):
        file_obj = get_object_or_404(ProjectFile, pk=pk)
        project = file_obj.repository.project
        self.check_project_permission(project)
        file_obj.delete()
        messages.success(request, "文件已删除")
        next_url = request.META.get('HTTP_REFERER', reverse('project_detail', kwargs={'pk': project.id}))
        return redirect(next_url)


class RepoAutocompleteView(LoginRequiredMixin, View):
    def get(self, request):
        model_type = request.GET.get('model')
        query = request.GET.get('q', '')
        data = []

        if model_type == 'customer':
            qs = Customer.objects.filter(company_name__icontains=query)[:20]
            data = [{'value': item.pk, 'text': item.company_name} for item in qs]

        elif model_type == 'oem':
            qs = OEM.objects.filter(Q(name__icontains=query) | Q(short_name__icontains=query))[:20]
            data = [{'value': item.pk, 'text': f"{item.name} ({item.short_name})" if item.short_name else item.name} for item in qs]

        elif model_type == 'salesperson':
            # 【重要修正】：现在搜索业务员，实际上是搜索内部 User 账号
            # 我们过滤 is_staff=True 的用户
            qs = User.objects.filter(
                Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query),
                is_staff=True
            )[:20]
            data = [{'value': item.pk, 'text': item.get_full_name() or item.username} for item in qs]

        return JsonResponse(data, safe=False)
