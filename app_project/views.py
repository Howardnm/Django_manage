from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.urls import reverse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.views.generic import UpdateView, CreateView

from .models import Project, ProjectNode, ProjectStage
from .forms import ProjectForm, ProjectNodeUpdateForm
from .mixins import ProjectPermissionMixin
from .utils.calculate_project_gantt import get_project_gantt_data # 【关键】导入甘特图工具函数
from .utils.filters import ProjectFilter # 导入刚才定义的类


# ==========================================
# 1. 项目列表 (查询与展示)
# ==========================================
class ProjectListView(LoginRequiredMixin, PermissionRequiredMixin, ProjectPermissionMixin, View):
    permission_required = 'app_project.view_project'

    def get(self, request):
        # 1. 基础数据 + 权限控制 (这部分是你的核心业务，不能动)
        base_qs = Project.objects.prefetch_related('nodes')
        base_qs = self.get_permitted_queryset(base_qs)

        # 2. 【核心修改】使用 django-filter
        # 语法: FilterSet(GET参数, queryset=基础集, request=请求对象)
        # 传入 request 是为了在 filter 类里能用 self.request.user
        filter_set = ProjectFilter(request.GET, queryset=base_qs, request=request)

        # 获取过滤后的结果 (filter_set.qs 自动执行了所有逻辑)
        queryset = filter_set.qs

        # 3. 分页 (代码不变)
        paginator = Paginator(queryset, 10)
        page_obj = paginator.get_page(request.GET.get('page'))

        context = {
            'page_obj': page_obj,
            'filter': filter_set,  # 【关键】把 filter 对象传给前端
            # 【额外好处】filter_set.form 可以直接在模板里渲染出表单（如果你想用 Django Form 的话）
            # 但你用的是 Tabler 手写 HTML，所以依然回显参数：
            'current_sort': request.GET.get('sort', ''),
        }
        return render(request, 'apps/app_project/list.html', context)


# 2. 项目创建
class ProjectCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    # 建议将权限改为 add_project，这更符合 Django 规范，当然用 view_project 也能跑
    permission_required = 'app_project.add_project'
    raise_exception = True

    model = Project
    form_class = ProjectForm
    # 【关键】指向通用模板
    template_name = 'apps/app_project/project_form.html'

    def form_valid(self, form):
        # 相当于你原来 post 方法里的 project.manager = request.user
        form.instance.manager = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        # 创建成功后跳转到列表
        return reverse('project_list')


# 2. 编辑项目视图 (新增)
class ProjectUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    # 编辑权限通常是 change_project
    permission_required = 'app_project.change_project'
    raise_exception = True

    model = Project
    form_class = ProjectForm
    # 【关键】指向同一个通用模板
    template_name = 'apps/app_project/project_form.html'

    def get_success_url(self):
        # 编辑成功后，跳回该项目的详情页
        return reverse('project_detail', kwargs={'pk': self.object.pk})


# ==========================================
# 3. 项目详情
# ==========================================
class ProjectDetailView(LoginRequiredMixin, ProjectPermissionMixin, View):
    def get(self, request, pk):
        # 1. 获取数据 & 优化查询
        # 使用 select_related 一次性把 档案、客户、材料、材料分类 全部抓取出来
        project = get_object_or_404(
            Project.objects.select_related(
                'manager',
                'repository',
                'repository__customer',
                'repository__material',
                'repository__material__category',
                'repository__material__scenario'
            ).prefetch_related('nodes'),
            pk=pk
        )

        self.check_project_permission(project)

        nodes = project.cached_nodes
        gantt_data_json = get_project_gantt_data(project)

        context = {
            'project': project,
            'nodes': nodes,
            'gantt_data_json': gantt_data_json,
            # 将 repository 单独提出来传给模板，方便调用 (虽然 project.repository 也能用)
            'repo': getattr(project, 'repository', None)
        }

        return render(request, 'apps/app_project/detail.html', context)



# ==========================================
# 4. 节点操作：常规更新
# ==========================================
class ProjectNodeUpdateView(LoginRequiredMixin, ProjectPermissionMixin, View):
    template_name = 'apps/app_project/detail/modal_box/_project_progress_update.html'

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
    template_name = 'apps/app_project/detail/modal_box/_project_progress_failed.html'

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
    template_name = 'apps/app_project/detail/modal_box/_project_progress_feedback.html'

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
