from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from app_project.models import Project, ProjectNode, ProjectStage

# 4. 信号量：创建项目时，自动生成9个节点
@receiver(post_save, sender=Project)
def create_project_nodes(sender, instance, created, **kwargs):
    if created:
        nodes_to_create = []
        for i, (code, label) in enumerate(ProjectStage.choices):
            if code not in ['FEEDBACK']:
                nodes_to_create.append(
                    ProjectNode(
                        project=instance,
                        stage=code,
                        order=i + 1,
                        round=1,
                        status='PENDING'
                    )
                )
        ProjectNode.objects.bulk_create(nodes_to_create)


# 信号量：更新父级 Project 的冗余字段
@receiver([post_save, post_delete], sender=ProjectNode)
def update_project_status_fields(sender, instance, **kwargs):
    _update_project_current_stage(instance.project)


def _update_project_current_stage(project):
    """
    重新计算并更新 Project 的冗余字段。
    修复逻辑：精确识别‘暂停’节点作为当前阶段。
    """
    # 重新从数据库获取最新的节点列表，避免缓存干扰
    all_nodes = project.nodes.all().order_by('order')

    # --- A. 定位当前阶段 (核心修复) ---
    
    # 1. 优先判断是否有“已终止”节点，如果有，项目阶段锁定在该节点
    terminated_node = all_nodes.filter(status='TERMINATED').last()
    
    if terminated_node:
        current_node = terminated_node
    else:
        # 2. 排除掉“已结束”性质的状态，剩下的第一个就是当前活跃/待办阶段
        # 排除状态：DONE(完成), FAILED(失败迭代), FEEDBACK(已提意见)
        # 包含状态：DOING(进行中), PAUSED(暂停), PENDING(未开始)
        current_node = all_nodes.exclude(status__in=['DONE', 'FAILED', 'FEEDBACK']).first()

    new_stage = ProjectStage.INIT
    new_remark = ""

    if current_node:
        new_stage = current_node.stage
        new_remark = current_node.remark or ""
    else:
        # 如果所有节点都处理完了，取最后一个
        last_node = all_nodes.last()
        if last_node:
            new_stage = last_node.stage
            new_remark = last_node.remark or ""

    # --- B. 计算进度百分比 ---
    # 这里的逻辑保持不变：只计算 DONE 节点的占比
    valid_nodes = [n for n in all_nodes if n.stage != 'FEEDBACK' and n.status != 'FAILED']
    total = len(valid_nodes)
    if total < 9: total = 9
    done_count = sum(1 for n in valid_nodes if n.status == 'DONE')
    new_percent = int((done_count / total) * 100) if total > 0 else 0

    # --- C. 计算是否终止 ---
    new_is_terminated = terminated_node is not None

    # --- D. 批量更新 ---
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

    new_remark = new_remark[:190]
    if project.latest_remark != new_remark:
        project.latest_remark = new_remark
        update_fields.append('latest_remark')

    if update_fields:
        project.save(update_fields=update_fields)
