from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from app_basic_research.models import ResearchProject, ResearchProjectNode, ResearchStage

# 信号量：每当 ResearchProjectNode 发生变化（更新状态、插入新节点）时，自动重新计算并更新父级 ResearchProject 的冗余字段。
@receiver([post_save, post_delete], sender=ResearchProjectNode)
def update_research_project_status_fields(sender, instance, **kwargs):
    _update_project_current_stage(instance.project)


def _update_project_current_stage(project):
    """
    重新计算并更新 ResearchProject 的冗余字段
    """
    # 查出所有节点
    all_nodes = project.nodes.all().order_by('order')

    # --- A. 计算当前阶段 ---
    # 找到第一个处于 PENDING 或 DOING 的节点
    current_node = next((n for n in all_nodes if n.status in ['PENDING', 'DOING']), None)

    # 特殊情况：如果找到了 TERMINATED 节点，那当前阶段就是它
    terminated_node = next((n for n in reversed(all_nodes) if n.status == 'TERMINATED'), None)
    if terminated_node:
        current_node = terminated_node

    new_stage = ResearchStage.INIT
    new_remark = ""

    if current_node:
        new_stage = current_node.stage
        new_remark = current_node.remark or ""
    else:
        # 如果所有节点都跑完了（全是 DONE/FAILED），取最后一个的阶段
        if all_nodes:
            last_node = all_nodes.last()
            new_stage = last_node.stage
            new_remark = last_node.remark or ""

    # --- B. 计算进度百分比 ---
    # 预研项目标准流程有6个阶段，以此为基准计算
    # 排除失败的节点，只计算有效推进
    valid_nodes = [n for n in all_nodes if n.status != 'FAILED']
    total_standard_stages = 6 
    
    # 计算已完成的节点数
    done_count = sum(1 for n in valid_nodes if n.status == 'DONE')
    
    # 简单计算：完成数 / 总阶段数
    # 注意：如果因为迭代导致节点数超过6个，百分比可能会超过100%，这里做个限制
    new_percent = int((done_count / total_standard_stages) * 100)
    if new_percent > 100: new_percent = 100

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

    # 更新最新备注
    new_remark = new_remark[:190]
    if project.latest_remark != new_remark:
        project.latest_remark = new_remark
        update_fields.append('latest_remark')

    if update_fields:
        project.save(update_fields=update_fields)
