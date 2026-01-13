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


# 1. 定义标准流程阶段 (枚举) - 这相当于“类型库”
class ProjectStage(models.TextChoices):
    INIT = 'INIT', '① 项目立项'
    COLLECT = 'COLLECT', '② 收集资料'
    FEASIBILITY = 'FEASIBILITY', '③ 可行性评估'
    PRICING = 'PRICING', '④ 客户定价'
    RND = 'RND', '⑤ 研发阶段'  # 可能多次
    PILOT = 'PILOT', '⑥ 客户小试'  # 可能多次
    MID_TEST = 'MID_TEST', '⑦ 客户中试'  # 可能多次
    MASS_PROD = 'MASS_PROD', '⑧ 客户量产'
    ORDER = 'ORDER', '⑨ 客户量产订单'
    FEEDBACK = 'FEEDBACK', '📢客户意见/变更'


# 2. 项目主体模型
class Project(models.Model):
    name = models.CharField("项目名称", max_length=100)
    manager = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="项目负责人")
    description = models.TextField("项目描述", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    # 辅助方法：获取当前进度（计算百分比）
    def get_progress_percent(self):
        # 这里的self.nodes，就是引用了ProjectNode模型的关联外键
        valid_nodes = self.nodes.exclude(stage=ProjectStage.FEEDBACK).exclude(status='FAILED') # 排除【客户反馈】的节点
        total = valid_nodes.count()
        if total == 0: return 0
        if total < 9: total = 9
        done = valid_nodes.filter(status='DONE').count()
        return int((done / total) * 100)

    # 辅助方法：获取当前阶段名称
    def get_current_stage_label(self):
        # 找第一个“进行中”或者第一个“未开始”的（即排除“已完成”）
        node = self.nodes.exclude(status='DONE').order_by('order').first()
        if node:
            # 如果是第2轮以后，显示 "研发阶段 (第2轮)"
            if node.round > 1:
                return f"{node.get_stage_display()} (第{node.round}轮)"
            return f"⏳{node.get_stage_display()}"
        return "✅已完成"

    # 辅助方法：获取当前阶段描述
    def get_current_stage_remark(self):
        # 找第一个“进行中”或者第一个“未开始”的（即排除“已完成”）
        node = self.nodes.exclude(status='PENDING').order_by('-order').first()
        if node and node.remark:
            # Truncator：如果大于20个字，截取前20个字，然后加“...”
            return Truncator(node.remark).chars(30, truncate='...')
        return "⚠️暂无备注"

    # 辅助方法：获取当前阶段更新时间
    def get_current_stage_updated_time(self):
        node = self.nodes.order_by('-updated_at').first()
        return node.updated_at

    # 辅助方法：获取当前阶段状态
    def get_current_stage_status(self):
        node = self.nodes.order_by('-updated_at').first()
        return node.status

    # 【新增功能】插入一个新的迭代节点（例如：小试失败，重新插入一轮研发）
    def add_iteration_node(self, stage_code, after_node_order):
        '''
        在指定的 order 之后插入一个新节点
        :param stage_code: 新节点的阶段代码 (如 'RND' '研发阶段')
        :param after_node_order: 在哪个排序号之后插入
        '''
        with transaction.atomic():
            # 1. 把所有排在后面的节点，order 全部 +1 (腾出位置)
            # 使用 F() 表达式进行原子更新
            from django.db.models import F
            self.nodes.filter(order__gt=after_node_order).update(order=F('order') + 1)

            # 2. 计算这是该阶段的第几轮 (用于绩效统计)
            # 比如之前已经有 1 个 RND 节点，现在加进来的就是第 2 轮
            current_count = self.nodes.filter(stage=stage_code).count()
            new_round = current_count + 1

            # 3. 创建新节点
            ProjectNode.objects.create(
                project=self,
                stage=stage_code,
                order=after_node_order + 1,
                round=new_round,
                status='PENDING',  # 新插入的肯定未开始
                remark=f"新增第 {new_round} 轮迭代"
            )

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
                stage=ProjectStage.FEEDBACK, # 插入一个“客户意见”
                order=current_node_order + 1,
                round=1,
                status='TERMINATED',  # 状态直接设为终止
                remark=f"项目终止。原因：{reason}"
            )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "项目"  # 给这个模型起一个名称。
        ordering = ['-created_at']  # 定义排序规则，给created_at字段倒序排序，“-”号为倒序，等价于.order_by('-created_at')


    # 3. 进度节点模型
class ProjectNode(models.Model):
    STATUS_CHOICES = [
        ('PENDING', '未开始'),
        ('DOING', '进行中'),
        ('DONE', '已完成'),
        ('FAILED', '不合格/需返工'), # 新增一个状态，方便标记这一轮失败了
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

    # 1. 判断节点是否处于“活跃/可操作”状态
    # (即：不是完成、不是终止、不是失败)
    @property
    def is_active(self):
        return self.status not in ['DONE', 'TERMINATED', 'FAILED']

    # 2. 判断是否可以显示“常规更新”按钮
    # (逻辑：只要不是终止或已失败，通常都可以更新，比如把进行中改成已完成)
    @property
    def can_update_status(self):
        return self.status not in ['TERMINATED', 'FAILED']

    # 3. 判断是否可以“申报不合格”
    # (逻辑：必须是活跃状态，且阶段必须是 研发 或 小试)
    @property
    def can_report_failure(self):
        # 允许失败的阶段列表
        allowed_stages = [ProjectStage.RND, ProjectStage.PILOT, ProjectStage.MID_TEST]
        return self.is_active and (self.stage in allowed_stages)

    # 4. 判断是否可以“客户干预”
    # (逻辑：不是终止状态，且当前节点本身不是反馈节点)
    @property
    def can_add_feedback(self):
        return (self.status != 'TERMINATED') and (self.stage != ProjectStage.FEEDBACK)



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
