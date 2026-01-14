from pickletools import string1
from xmlrpc.client import boolean

from django.db import models

# Create your models here.
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.text import Truncator  # 导入文字截断器
from django.db import transaction  # 用于事务处理，保证排序修改的安全性
from django.utils.functional import cached_property  # 引入缓存装饰器


# 1. 定义标准流程阶段 (枚举) - 这相当于“类型库”
class ProjectStage(models.TextChoices):
    INIT = 'INIT', '① 项目立项'
    COLLECT = 'COLLECT', '② 收集资料'
    FEASIBILITY = 'FEASIBILITY', '③ 可行性评估'
    PRICING = 'PRICING', '④ 客户定价'
    RND = 'RND', '⑤ 研发阶段'  # 可能多次
    PILOT = 'PILOT', '⑥ 客户小试'  # 可能多次
    MID_TEST = 'MID_TEST', '⑦ 客户中试'  # 可能多次
    MASS_PROD = 'MASS_PROD', '⑧ 客户量产意向'
    ORDER = 'ORDER', '⑨ 客户下单情况'
    FEEDBACK = 'FEEDBACK', '客户意见'


# 2. 项目主体模型
class Project(models.Model):
    name = models.CharField("项目名称", max_length=100)
    manager = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="项目负责人")
    description = models.TextField("项目描述", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "项目"  # 给这个模型起一个名称。
        ordering = ['-created_at']  # 定义排序规则，给created_at字段倒序排序，“-”号为倒序，等价于.order_by('-created_at')

    def __str__(self):
        return self.name

    # --- 优化后的辅助方法 (针对 N+1 优化) ---
    # 核心思想：不要在方法里用 filter/exclude，因为那会强制查库。
    # 而是用 self.nodes.all()，配合 view 里的 prefetch_related，这样是在内存里操作。
    @cached_property
    def cached_nodes(self):
        """获取当前项目的节点列表。将节点按 order 正序排序缓存到内存中，供后续计算使用"""
        return sorted(self.nodes.all(), key=lambda x: x.order)

    def get_progress_info(self):
        """一次性计算进度信息，返回字典，避免模板多次调用不同的计算方法"""
        # 1、获取当前进度（计算百分比）
        valid_nodes = [n for n in self.cached_nodes if n.stage != ProjectStage.FEEDBACK and n.status != 'FAILED']
        total = len(valid_nodes)
        if total < 9: total = 9  # 避免除零
        done_count = sum(1 for n in valid_nodes if n.status == 'DONE')
        percent = int((done_count / total) * 100)
        # 2、寻找当前节点（只包含：未开始、进行中、已终止的节点，然后取最前的一个节点）
        current_node = next((n for n in self.cached_nodes if n.status in ['PENDING', 'DOING']), None)
        current_node_terminated = next((n for n in reversed(self.cached_nodes) if n.status in ['TERMINATED']), None)
        # -- 如果存在终止节点，把当前节点切换成终止节点。
        if current_node_terminated:
            current_node = current_node_terminated
        # 3、寻找最后更新时间
        last_updated = max((n.updated_at for n in self.cached_nodes), default=self.created_at)
        # 4、寻找是否有终止状态
        is_terminated = any(n.status == 'TERMINATED' for n in self.cached_nodes)
        # 5、寻找当前节点的描述
        current_remark = Truncator(current_node.remark).chars(30) if (current_node and current_node.remark) else " "

        return {
            'percent': percent,
            'current_label': self._format_stage_label(current_node),
            'current_remark': current_remark,
            'last_updated': last_updated,
            'is_terminated': is_terminated,
            # 【新增】返回原始对象，供仪表盘 View 做逻辑判断
            'current_node_obj': current_node
        }

    def _format_stage_label(self, node):
        if not node:
            return "✅已结束"
        if node.status in ['TERMINATED']:
            return "❌已终止"
        if node.round > 1:
            return f"🔂{node.get_stage_display()} (第{node.round}轮)"
        return f"⏳{node.get_stage_display()}"

    # --- 业务逻辑封装 ---
    # 【新增功能】插入一个新的迭代节点（例如：小试失败，重新插入一轮研发）
    def add_iteration_node(self, stage_code, after_node_order):
        '''
        在指定的 order 之后插入一个新节点
        :param stage_code: 新节点的阶段代码 (如 'RND' '研发阶段')
        :param after_node_order: 在哪个排序号之后插入
        '''
        with transaction.atomic():
            # 1. 把所有排在后面的节点，order 全部 +1 (腾出位置)。 使用 F() 表达式进行原子更新。
            from django.db.models import F
            self.nodes.filter(order__gt=after_node_order).update(order=F('order') + 1)
            # 2. 计算这是该阶段的第几轮 (用于绩效统计)。 比如之前已经有 1 个 RND 节点，现在加进来的就是第 2 轮。
            current_count = self.nodes.filter(stage=stage_code).count()
            new_round = current_count + 1
            # 3. 创建新节点
            ProjectNode.objects.create(
                project=self,
                stage=stage_code,
                order=after_node_order + 1,
                round=new_round,
                status='PENDING',  # 新插入的肯定未开始
                remark=f"第 {new_round} 轮调整：\n"
            )

    # 【新增】处理客户反馈/干预
    def handle_customer_feedback(self, current_node, feedback_type, content):
        '''
        统一处理客户反馈逻辑
        :param current_node: 当前触发反馈的节点对象
        :param feedback_type: 'STOP'(终止) 或 其他(仅记录意见)
        :param content: 反馈的具体内容
        '''
        with transaction.atomic():
            if feedback_type == 'STOP':
                # 1. 终止当前正在进行的节点
                current_node.status = 'TERMINATED'
                current_node.save()
                # 2. 终止整个项目流程
                self.terminate_project(current_node.order, content)
            else:
                # 1. 插入一个新的占位节点 (类型为 FEEDBACK)
                self.add_iteration_node(ProjectStage.FEEDBACK, current_node.order)

                # 2. 找到刚才插入的那个节点 (它现在排在 current_node 的后面，即 +1)
                feedback_node = self.nodes.filter(order=current_node.order + 1).first()

                if feedback_node:
                    feedback_node.status = 'FEEDBACK'  # 标记为客户意见状态
                    feedback_node.remark = content
                    feedback_node.save()

    # 【新增功能】终止项目
    def terminate_project(self, current_node_order, reason):
        '''
        终止项目：
        1. 清除当前节点之后的所有 PENDING 节点
        2. 插入一个“客户终止”节点作为结局
        '''
        with transaction.atomic():
            # 1. 删除后续所有未开始的节点（因为项目黄了，后面不用做了）
            self.nodes.filter(order__gt=current_node_order, status='PENDING').delete()

            # 2. 插入一个“客户意见”节点作为最后一个节点
            ProjectNode.objects.create(
                project=self,
                stage=ProjectStage.FEEDBACK,  # 插入一个“客户意见”
                order=current_node_order + 1,
                round=1,
                status='TERMINATED',  # 状态直接设为终止
                remark=f"终止原因：{reason}"
            )


# 3. 进度节点模型
class ProjectNode(models.Model):
    STATUS_CHOICES = [
        ('PENDING', '未开始'),
        ('DOING', '进行中'),
        ('DONE', '已完成'),
        ('FEEDBACK', '客户意见'),
        ('FAILED', '异常/节点迭代'),  # 新增一个状态，方便标记这一轮失败了
        ('TERMINATED', '已终止'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='nodes')
    stage = models.CharField("阶段", max_length=20, choices=ProjectStage.choices)
    # 【新增字段】轮次：记录这是该阶段的第几次尝试
    round = models.PositiveIntegerField("轮次", default=1)
    order = models.IntegerField("排序权重", default=0)  # 用于保证步骤顺序
    status = models.CharField("状态", max_length=10, choices=STATUS_CHOICES, default='PENDING')
    updated_at = models.DateTimeField("更新时间", auto_now=True)
    remark = models.TextField("备注/批注", blank=True, null=True)  # 比如：上传了什么文件，遇到了什么问题

    class Meta:
        verbose_name = "项目进度节点"  # 给这个模型起一个名称。
        ordering = ['order']  # 给order字段正序排序

    def __str__(self):
        return self.project.name

    # --- 逻辑判断属性 ---
    # 1. 判断节点是否处于“活跃/可操作”状态
    @property
    def is_active(self):
        return self.status not in ['DONE', 'TERMINATED', 'FAILED', 'FEEDBACK']

    @property
    def is_active_status(self):
        """是否节点已完成、进行中"""
        return self.status in ['DONE', 'DOING']

    # 2. 判断是否可以显示“常规更新”按钮
    # (逻辑：只要不是终止或已失败，通常都可以更新，比如把进行中改成已完成)
    @property
    def can_update_status(self):
        return self.status not in ['TERMINATED', 'FAILED', 'FEEDBACK']

    # 3. 判断是否可以“申报不合格”
    # (逻辑：必须是活跃状态，且阶段必须是 研发 或 小试)
    @property
    def can_report_failure(self):
        # 允许失败的阶段列表
        allowed_stages = [ProjectStage.RND, ProjectStage.PILOT, ProjectStage.MID_TEST]
        return self.is_active and (self.stage in allowed_stages)

    # 4. 判断是否可以“客户干预”
    # (逻辑：不是终止、完成状态，且当前节点本身不是反馈节点)
    @property
    def can_add_feedback(self):
        return (self.status not in ['TERMINATED', 'DONE', 'FAILED']) and (self.stage != ProjectStage.FEEDBACK)

    # --- 新增：UI 辅助属性 (把 HTML 里的 if/else 移到这里) ---
    @property
    def status_css_class(self):
        mapping = {
            'PENDING': 'bg-secondary-lt',  # 灰色
            'DOING': 'bg-blue-lt',  # 蓝色
            'DONE': 'bg-green-lt',  # 绿色
            'FEEDBACK': 'bg-yellow text-white',  # 黄色 (高亮)
            'FAILED': 'bg-red-lt',  # 红色 (浅色)
            'TERMINATED': 'bg-red text-white',  # 红色 (深色)
        }
        return mapping.get(self.status, 'bg-secondary-lt')

    @property
    def title_status_css_class(self):
        """返回状态对应的 Tabler 颜色类"""
        mapping = {
            'PENDING': 'text-secondary',
            'DOING': 'text-primary',
            'DONE': 'text-primary',
            'FEEDBACK': 'badge bg-yellow text-white',
            'FAILED': 'text-primary',
            'TERMINATED': 'text-primary'
        }
        return mapping.get(self.status, 'text-secondary')

    @property
    def row_active_class(self):
        """控制步骤条是否点亮"""
        if self.status not in ['DONE', 'FAILED', 'FEEDBACK']:
            return "active"
        return ""

    @property
    def is_feedback_stage(self):
        """是否为客户意见阶段节点"""
        return self.stage == ProjectStage.FEEDBACK

    # --- 新增：业务操作封装 ---
    def perform_failure_logic(self, reason):
        """处理申报不合格的完整逻辑"""
        with transaction.atomic():
            self.status = 'FAILED'
            self.remark = reason
            self.save()

        project = self.project
        # 根据当前阶段决定插入哪些节点
        if self.stage in ['RND', 'PILOT', 'MID_TEST']:
            # 1. 必插研发
            project.add_iteration_node(ProjectStage.RND, self.order)
            # 2. 如果是中试失败，还要补中试（先插中试，再插小试，确保小试在中试的前面）
            if self.stage == 'MID_TEST':
                project.add_iteration_node(ProjectStage.MID_TEST, self.order + 1)
            # 3. 如果是小试失败，还要补一个小试
            if self.stage in ['PILOT', 'MID_TEST']:
                # 基准是 +1 (刚插了一个研发)
                project.add_iteration_node(ProjectStage.PILOT, self.order + 1)


# 4. 【核心逻辑】信号量：创建项目时，自动生成9个节点(监听Project动作，自动触发)
@receiver(post_save, sender=Project)
def create_project_nodes(sender, instance, created, **kwargs):
    '''
    每当一个新的项目被创建时，系统自动为它生成那 9 个标准的进度节点，而不需要人工一个个去添加。
    @receiver(post_save, ...)：这是 Django 的信号接收器。它的意思是：“我要监听数据库的保存动作”。
    :param sender: 意思是“我只监听 Project (项目) 表的动作，其他表我不关心”。
    :param instance: 这就是刚刚被保存进去的那个具体的项目对象
    :param created: 这是一个布尔值（True/False）。True：表示这是一次新建（Insert）。False：表示这是一次修改（Update）。
    :param kwargs:
    :return:
    '''
    if created:
        nodes_to_create = []
        # 遍历定义好的枚举，按顺序生成
        for i, (code, label) in enumerate(ProjectStage.choices):
            if code not in ['FEEDBACK']:
                nodes_to_create.append(
                    ProjectNode(
                        project=instance,
                        stage=code,
                        order=i + 1,  # 1, 2, 3...
                        round=1,  # 默认都是第1轮
                        status='PENDING'  # 默认未开始
                    )
                )
        # 批量创建，性能更好（创建9个进度节点到ProjectNode）
        ProjectNode.objects.bulk_create(nodes_to_create)
