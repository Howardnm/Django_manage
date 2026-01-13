from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View  # 这是最基础的类视图
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import Project, ProjectNode, ProjectStage
from .forms import ProjectForm, ProjectNodeUpdateForm


# 1. 项目列表
class ProjectListView(LoginRequiredMixin, View):
    def get(self, request):
        # 显式查询所有项目
        # 虽然在models.py已经设置排序，但为了解耦，还是加上order_by
        projects = Project.objects.all().order_by('-created_at')
        # 这里你可以很方便地加过滤，比如只看自己的：Project.objects.filter(manager=request.user)

        context = {
            'projects': projects
        }
        return render(request, 'apps/projects/list.html', context)


# 2. 创建项目
class ProjectCreateView(LoginRequiredMixin, View):
    def get(self, request):
        # GET 请求：展示一个空表单
        form = ProjectForm()
        return render(request, 'apps/projects/create.html', {'form': form})

    def post(self, request):
        # POST 请求：接收数据
        form = ProjectForm(request.POST)

        if form.is_valid():
            # 1. 暂时不保存到数据库，因为要手动填 manager
            project = form.save(commit=False)
            # 2. 手动把当前登录用户赋给 manager
            project.manager = request.user
            # 3. 正式保存（此时信号量 signal 会自动触发生成9个节点）
            project.save()

            return redirect('project_list')  # 成功后跳转

        # 失败则重新渲染页面，并带上错误信息
        return render(request, 'apps/projects/create.html', {'form': form})


# 3. 项目详情（含进度时间轴）
class ProjectDetailView(LoginRequiredMixin, View):
    def get(self, request, pk):
        # 1. 获取项目对象，如果找不到由 Django 自动抛出 404
        project = get_object_or_404(Project, pk=pk)

        # 2. 获取该项目下的所有节点
        # 这里的 nodes 就是我们之前说的 related_name
        nodes = project.nodes.all().order_by('order')

        context = {
            'project': project,
            'nodes': nodes,
            # 【关键修改】把 Status 的选项传给前端，这样前端就不用写死 <option> 了
            'status_choices': ProjectNode.STATUS_CHOICES,
            # 把阶段类型也传过去，方便前端判断是否显示“不合格”按钮
            'stage_pilot': ProjectStage.PILOT,
            'stage_rnd': ProjectStage.RND,
        }
        return render(request, 'apps/projects/detail.html', context)


# 4. 更新节点状态
class ProjectNodeUpdateView(LoginRequiredMixin, View):
    # 如果你是做模态框加载，可能需要 GET 方法来渲染模态框内容
    def get(self, request, pk):
        node = get_object_or_404(ProjectNode, pk=pk)
        # 传递 status_choices 给模板
        context = {
            'node': node,
            'status_choices': ProjectNode.STATUS_CHOICES
        }
        return render(request, 'apps/projects/detail/modal_box/_project_progress_update.html', context)

    def post(self, request, pk):
        node = get_object_or_404(ProjectNode, pk=pk)
        # 关键：instance=node 告诉 Django 我们是在修改这个已存在的对象，而不是创建新的
        form = ProjectNodeUpdateForm(request.POST, instance=node)
        if form.is_valid():
            form.save()
            # 【关键】保存成功后，返回一个空响应，但带上 HX-Refresh 头
            # 这会告诉 HTMX：“我处理完了，请刷新整个页面以显示最新进度”
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
            # return redirect('project_detail', pk=node.project.id)

        # 如果校验失败，重新返回表单片段（含错误信息）
        context = {'node': node, 'status_choices': ProjectNode.STATUS_CHOICES, 'form': form}
        return render(request, 'apps/projects/detail/modal_box/_project_progress_update.html', context)


# 5. 添加失败申报迭代节点
class NodeFailedView(LoginRequiredMixin, View):
    # 【新增 GET】: 返回红色的失败申报表单
    def get(self, request, pk):
        node = get_object_or_404(ProjectNode, pk=pk)
        return render(request, 'apps/projects/detail/modal_box/_project_progress_failed.html', {'node': node})

    def post(self, request, pk):
        # 1. 获取当前失败的节点（比如那个小试节点）
        failed_node = get_object_or_404(ProjectNode, pk=pk)
        project = failed_node.project

        # 2. 更新当前节点为 FAILED
        failed_node.status = 'FAILED'
        failed_node.remark = request.POST.get('remark', '测试不通过，需返工')
        failed_node.save()

        # 3. 判断逻辑：如果是小试失败，插入 "研发" + "小试"
        if failed_node.stage in ['RND', 'PILOT', 'MID_TEST']:
            # 第一步：插入研发 (插在 6 后面，占用 7)
            # 现在的顺序：... 小试(6) -> 研发(7) -> 中试(8)
            project.add_iteration_node(
                stage_code=ProjectStage.RND,  # 'RND','研发阶段'
                after_node_order=failed_node.order
            )
            if failed_node.stage in ['PILOT']:
                # 第二步：插入小试 (插在 7 后面，占用 8)
                # 注意：这里基准位置是 failed_node.order + 1
                # 现在的顺序：... 小试(6) -> 研发(7) -> 小试(8) -> 中试(9)
                project.add_iteration_node(
                    stage_code=ProjectStage.PILOT,  # 'PILOT','客户小试'
                    after_node_order=failed_node.order + 1
                )
            if failed_node.stage in ['MID_TEST']:
                # 第三步：插入中试
                project.add_iteration_node(
                    stage_code=ProjectStage.MID_TEST,  # 'PILOT','客户小试'
                    after_node_order=failed_node.order + 1
                )

        # 最后返回刷新指令
        return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
        # return redirect('product_detail', pk=project.id)


# 6. 添加客户意见节点
class InsertFeedbackView(LoginRequiredMixin, View):
    # 【新增 GET】: 返回客户干预表单
    def get(self, request, pk):
        node = get_object_or_404(ProjectNode, pk=pk)
        return render(request, 'apps/projects/detail/modal_box/_project_progress_feedback.html', {'node': node})

    def post(self, request, pk):
        # pk 是当前正在进行的节点 ID
        current_node = get_object_or_404(ProjectNode, pk=pk)
        project = current_node.project

        feedback_type = request.POST.get('feedback_type')  # 'CHANGE' (变更) 或 'STOP' (终止)
        content = request.POST.get('remark')

        if feedback_type == 'STOP':
            # 情况 A: 客户不想要了 -> 终止项目
            # 先把当前正在做的这个节点强行结束（标记为终止）
            current_node.status = 'TERMINATED'
            current_node.remark = f"{current_node.remark or ''} (被客户叫停)"
            current_node.save()

            # 调用刚才写的 model 方法，清理后续并封板
            project.terminate_project(current_node.order, content)

        else:
            # 情况 B: 客户有意见，但项目继续 -> 插入一个记录节点
            # 在当前节点后面插一个 FEEDBACK 节点
            # 这里的 status 可以是 DONE，表示这是一条已记录的信息
            project.add_iteration_node(ProjectStage.FEEDBACK, current_node.order)

            # 找到刚才插入的那个节点（order+1那个），把客户意见写进去
            feedback_node = ProjectNode.objects.get(
                project=project,
                order=current_node.order + 1
            )
            feedback_node.status = 'DONE'  # 意见已接收
            feedback_node.remark = content
            feedback_node.save()

        return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
        # return redirect('product_detail', pk=project.id)
