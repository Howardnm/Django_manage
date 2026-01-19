from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from app_project.models import Project, ProjectNode, ProjectStage

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


# 信号量：每当 ProjectNode 发生变化（更新状态、插入新节点）时，自动重新计算并更新父级 Project 的 current_stage。
@receiver([post_save, post_delete], sender=ProjectNode)
def update_project_status_fields(sender, instance, **kwargs):
    _update_project_current_stage(instance.project)


def _update_project_current_stage(project):
    """
    重新计算并更新 Project 的三个冗余字段
    """
    # 查出所有节点
    all_nodes = project.nodes.all().order_by('order')

    # --- A. 计算当前阶段 ---
    current_node = next((n for n in all_nodes if n.status in ['PENDING', 'DOING']), None)

    # 特殊情况：如果找到了 TERMINATED 节点，那当前阶段就是它
    terminated_node = next((n for n in reversed(all_nodes) if n.status == 'TERMINATED'), None)
    if terminated_node:
        current_node = terminated_node

    new_stage = ProjectStage.INIT
    new_remark = ""  # 【新增】最新备注

    if current_node:
        new_stage = current_node.stage
        new_remark = current_node.remark or ""  # 获取当前节点的备注
    else:
        # 如果所有节点都跑完了（全是 DONE/FAILED/FEEDBACK），取最后一个的阶段
        if all_nodes:
            last_node = all_nodes.last()
            new_stage = last_node.stage
            new_remark = last_node.remark or ""

    # --- B. 计算进度百分比 ---
    valid_nodes = [n for n in all_nodes if n.stage != 'FEEDBACK' and n.status != 'FAILED']
    total = len(valid_nodes)
    if total < 9: total = 9
    done_count = sum(1 for n in valid_nodes if n.status == 'DONE')
    new_percent = int((done_count / total) * 100) if total > 0 else 0

    # --- C. 计算是否终止 ---
    new_is_terminated = any(n.status == 'TERMINATED' for n in all_nodes)

    # --- D. 批量更新 (只更新变动的字段) ---
    update_fields = []

    if project.current_stage != new_stage:
        project.current_stage = new_stage
        update_fields.append('current_stage')

    if project.progress_percent != new_percent:
        project.progress_percent = new_percent
        update_fields.append('progress_percent')

    if project.is_terminated != new_is_terminated:
        project.is_terminated = new_is_terminated
        update_fields.append('is_terminated')

    # 【新增】更新最新备注
    # 注意：这里我们截取前200个字符，防止溢出
    new_remark = new_remark[:190]
    if project.latest_remark != new_remark:
        project.latest_remark = new_remark
        update_fields.append('latest_remark')

    if update_fields:
        project.save(update_fields=update_fields)