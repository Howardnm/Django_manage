from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from .models import Project, ProjectNode, ProjectStage
from .forms import ProjectForm, ProjectNodeUpdateForm
from .mixins import ProjectPermissionMixin


# ==========================================
# 1. 项目列表 (查询与展示)
# ==========================================
class ProjectListView(LoginRequiredMixin, PermissionRequiredMixin, ProjectPermissionMixin, View):
    # 记得继承 ProjectPermissionMixin
    permission_required = 'app_project.view_project'

    def get(self, request):
        # 1. 构建基础查询集 (预加载)
        queryset = Project.objects.prefetch_related('nodes')

        # 2. 【核心修改】调用 Mixin 进行权限隔离
        queryset = self.get_permitted_queryset(queryset)

        # 3. 搜索功能 (在已有权限范围内搜索)
        search_query = request.GET.get('q', '').strip()
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(manager__username__icontains=search_query) |
                Q(description__icontains=search_query)
            )

        # 4. 筛选功能
        manager_filter = request.GET.get('manager', '')
        if manager_filter == 'me':
            queryset = queryset.filter(manager=request.user)

        # 5. 排序功能
        sort_by = request.GET.get('sort', '-created_at')
        allowed_sorts = ['name', '-name', 'created_at', '-created_at', 'manager', '-manager']
        if sort_by not in allowed_sorts:
            sort_by = '-created_at'
        queryset = queryset.order_by(sort_by)

        # 6. 分页
        paginator = Paginator(queryset, 10)
        page_obj = paginator.get_page(request.GET.get('page'))

        context = {
            'page_obj': page_obj,
            'search_query': search_query,
            'current_manager': manager_filter,
            'current_sort': sort_by,
        }
        return render(request, 'apps/projects/list.html', context)


# ==========================================
# 2. 项目创建
# ==========================================
class ProjectCreateView(LoginRequiredMixin, View):
    template_name = 'apps/projects/create.html'

    def get(self, request):
        return render(request, self.template_name, {'form': ProjectForm()})

    def post(self, request):
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.manager = request.user
            project.save()  # 触发 signals 生成节点
            return redirect('project_list')

        return render(request, self.template_name, {'form': form})


# ==========================================
# 3. 项目详情
# ==========================================
class ProjectDetailView(LoginRequiredMixin, ProjectPermissionMixin, View):
    def get(self, request, pk):
        # 1. 获取项目
        project = get_object_or_404(Project.objects.prefetch_related('nodes'), pk=pk)

        # 2. 【安全】行级权限检查
        self.check_project_permission(project)

        context = {
            'project': project,
            'nodes': project.cached_nodes,  # 使用 Model 中的缓存属性
        }
        return render(request, 'apps/projects/detail.html', context)


# ==========================================
# 4. 节点操作：常规更新
# ==========================================
class ProjectNodeUpdateView(LoginRequiredMixin, ProjectPermissionMixin, View):
    template_name = 'apps/projects/detail/modal_box/_project_progress_update.html'

    def get_node_and_check_perm(self, pk):
        """辅助方法：获取节点并检查权限"""
        node = get_object_or_404(ProjectNode, pk=pk)
        self.check_project_permission(node.project)
        return node

    def get(self, request, pk):
        node = self.get_node_and_check_perm(pk)
        return render(request, self.template_name, {
            'node': node,
            'status_choices': ProjectNode.STATUS_CHOICES
        })

    def post(self, request, pk):
        node = self.get_node_and_check_perm(pk)
        form = ProjectNodeUpdateForm(request.POST, instance=node)

        if form.is_valid():
            form.save()
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})

        return render(request, self.template_name, {
            'node': node,
            'status_choices': ProjectNode.STATUS_CHOICES,
            'form': form
        })


# ==========================================
# 5. 节点操作：申报不合格 (失败重开)
# ==========================================
class NodeFailedView(LoginRequiredMixin, ProjectPermissionMixin, View):
    template_name = 'apps/projects/detail/modal_box/_project_progress_failed.html'

    def get(self, request, pk):
        node = get_object_or_404(ProjectNode, pk=pk)
        self.check_project_permission(node.project)
        return render(request, self.template_name, {'node': node})

    def post(self, request, pk):
        node = get_object_or_404(ProjectNode, pk=pk)
        self.check_project_permission(node.project)  # 【安全】

        remark = request.POST.get('remark', '测试不通过，需返工')

        # 业务逻辑已下沉到 Model
        node.perform_failure_logic(remark)

        return HttpResponse(status=204, headers={'HX-Refresh': 'true'})


# ==========================================
# 6. 节点操作：客户干预/反馈
# ==========================================
class InsertFeedbackView(LoginRequiredMixin, ProjectPermissionMixin, View):
    template_name = 'apps/projects/detail/modal_box/_project_progress_feedback.html'

    def get(self, request, pk):
        node = get_object_or_404(ProjectNode, pk=pk)
        self.check_project_permission(node.project)
        return render(request, self.template_name, {'node': node})

    def post(self, request, pk):
        current_node = get_object_or_404(ProjectNode, pk=pk)

        # 权限检查 (假设你用了 Mixin)
        self.check_project_permission(current_node.project)

        # 核心逻辑：直接调用 Model 方法
        current_node.project.handle_customer_feedback(
            current_node=current_node,
            feedback_type=request.POST.get('feedback_type'),
            content=request.POST.get('remark')
        )

        return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
