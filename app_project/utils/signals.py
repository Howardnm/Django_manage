from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import Max, Q
from app_project.models import Project, ProjectNode, ProjectStage, NodeScoreRule

@receiver(post_save, sender=Project)
def create_project_nodes(sender, instance, created, **kwargs):
    if created:
        nodes_to_create = []
        for i, (code, label) in enumerate(ProjectStage.choices):
            if code not in ['FEEDBACK']:
                nodes_to_create.append(
                    ProjectNode(
                        project=instance, stage=code, order=i + 1, round=1, status='PENDING'
                    )
                )
        ProjectNode.objects.bulk_create(nodes_to_create)

@receiver([post_save, post_delete], sender=ProjectNode)
def update_project_status_fields(sender, instance, **kwargs):
    _calculate_node_final_score(instance)
    _update_project_current_stage(instance.project)

@receiver([post_save, post_delete], sender=NodeScoreRule)
def trigger_global_score_recalculation(sender, instance, **kwargs):
    affected_nodes = ProjectNode.objects.filter(status__in=['DONE', 'FAILED', 'TERMINATED'])

    affected_projects = set()
    for node in affected_nodes:
        _calculate_node_final_score(node)
        affected_projects.add(node.project)

    for project in affected_projects:
        _update_project_current_stage(project)


def _calculate_node_final_score(node):
    if node.status not in ['DONE', 'FAILED', 'TERMINATED']:
        kwargs = {'final_score': 0}
        if node.sales_final_score != 0:
            kwargs['sales_final_score'] = 0
        if node.final_score != 0 or node.sales_final_score != 0:
            ProjectNode.objects.filter(pk=node.pk).update(**kwargs)
        return

    is_multiple = node.round > 1

    # 研发评分
    rd_rule = NodeScoreRule.objects.filter(
        rule_type='RD', trigger_status=node.status,
        trigger_stage=node.stage, is_multiple_rounds=is_multiple
    ).first()
    if not rd_rule:
        rd_rule = NodeScoreRule.objects.filter(
            Q(rule_type='RD'),
            Q(trigger_stage__isnull=True) | Q(trigger_stage=''),
            Q(trigger_status=node.status), Q(is_multiple_rounds=is_multiple)
        ).first()
    rd_score = rd_rule.score_value if rd_rule else 0

    # 销售评分
    sales_rule = NodeScoreRule.objects.filter(
        rule_type='SALES', trigger_status=node.status,
        trigger_stage=node.stage, is_multiple_rounds=is_multiple
    ).first()
    if not sales_rule:
        sales_rule = NodeScoreRule.objects.filter(
            Q(rule_type='SALES'),
            Q(trigger_stage__isnull=True) | Q(trigger_stage=''),
            Q(trigger_status=node.status), Q(is_multiple_rounds=is_multiple)
        ).first()
    sales_score = sales_rule.score_value if sales_rule else 0

    ProjectNode.objects.filter(pk=node.pk).update(
        final_score=rd_score, sales_final_score=sales_score
    )


def _update_project_current_stage(project):
    """
    重新计算并更新 Project 的冗余字段。
    """
    all_nodes = project.nodes.all().order_by('order')

    # --- A. 定位当前阶段 ---
    terminated_node = all_nodes.filter(status='TERMINATED').last()
    if terminated_node:
        current_node = terminated_node
    else:
        current_node = all_nodes.exclude(status__in=['DONE', 'FAILED', 'FEEDBACK']).first()

    new_stage = ProjectStage.INIT
    new_remark = ""
    if current_node:
        new_stage = current_node.stage
        new_remark = current_node.remark or ""
    else:
        last_node = all_nodes.last()
        if last_node:
            new_stage = last_node.stage
            new_remark = last_node.remark or ""

    # --- B. 计算进度百分比 ---
    valid_nodes = [n for n in all_nodes if n.stage != 'FEEDBACK' and n.status != 'FAILED']
    total = len(valid_nodes)
    if total < 9: total = 9
    done_count = sum(1 for n in valid_nodes if n.status == 'DONE')
    new_percent = int((done_count / total) * 100) if total > 0 else 0

    # --- C. 计算是否终止 ---
    new_is_terminated = terminated_node is not None

    # --- D. 项目质量分逻辑 ---
    # 取"最近一个已有结果且非反馈阶段的节点"的得分
    last_terminal_node = all_nodes.filter(
        status__in=['DONE', 'FAILED', 'TERMINATED']
    ).exclude(stage=ProjectStage.FEEDBACK).last()

    current_quality_score = last_terminal_node.final_score if last_terminal_node else 0
    current_sales_quality_score = last_terminal_node.sales_final_score if last_terminal_node else 0

    # --- E. 批量更新 ---
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
    if project.quality_score != current_quality_score:
        project.quality_score = current_quality_score
        update_fields.append('quality_score')
    if project.sales_quality_score != current_sales_quality_score:
        project.sales_quality_score = current_sales_quality_score
        update_fields.append('sales_quality_score')

    new_remark = new_remark[:190]
    if project.latest_remark != new_remark:
        project.latest_remark = new_remark
        update_fields.append('latest_remark')

    if update_fields:
        project.save(update_fields=update_fields)
