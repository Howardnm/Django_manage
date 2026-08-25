import logging
from decimal import Decimal

from django.db.models.signals import post_save, post_delete, pre_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone
from django.db.models import Max, Q
from app_project.models import (
    Project,
    ProjectNode,
    ProjectStage,
    NodeScoreRule,
    ProjectConfig,
    ProjectMember,
    ProjectSalesMember,
    MemberScoreSnapshot,
)

logger = logging.getLogger(__name__)

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
    try:
        _calculate_node_final_score(instance)
    except Exception:
        logger.exception("计算节点得分失败 node=%s", instance.pk)
    try:
        _update_project_current_stage(instance.project)
    except Exception:
        logger.exception("更新项目成绩失败 project=%s", instance.project_id)
        return
    try:
        record_project_score_snapshots(instance.project)
    except Exception:
        logger.exception("写成员成绩快照失败 project=%s", instance.project_id)

@receiver([post_save, post_delete], sender=NodeScoreRule)
def trigger_global_score_recalculation(sender, instance, **kwargs):
    affected_nodes = ProjectNode.objects.filter(status__in=['DONE', 'FAILED', 'TERMINATED'])

    affected_projects = set()
    for node in affected_nodes:
        _calculate_node_final_score(node)
        affected_projects.add(node.project)

    for project in affected_projects:
        _update_project_current_stage(project)
        try:
            record_project_score_snapshots(project)
        except Exception:
            logger.exception("评分规则变更后写快照失败 project=%s", project.pk)

# --- 成员占比变更 / 成员增删 → 写快照 ---

@receiver(post_save, sender=ProjectMember)
def project_member_saved(sender, instance, **kwargs):
    """新增或改占比：重算并写幂等快照（新成员立即按当前项目分计）。"""
    try:
        record_project_score_snapshots(instance.project)
    except Exception:
        logger.exception("成员变更写快照失败 project=%s user=%s", instance.project_id, instance.user_id)

@receiver(post_delete, sender=ProjectMember)
def project_member_deleted(sender, instance, **kwargs):
    """退出项目：写 0 分终止快照，累计分归零。"""
    try:
        record_member_exit_snapshot(instance.project_id, instance.user_id, 'RD')
    except Exception:
        logger.exception("成员退出写快照失败 project=%s user=%s", instance.project_id, instance.user_id)

@receiver(post_save, sender=ProjectSalesMember)
def project_sales_member_saved(sender, instance, **kwargs):
    try:
        record_project_score_snapshots(instance.project)
    except Exception:
        logger.exception("销售成员变更写快照失败 project=%s user=%s", instance.project_id, instance.user_id)

@receiver(post_delete, sender=ProjectSalesMember)
def project_sales_member_deleted(sender, instance, **kwargs):
    try:
        record_member_exit_snapshot(instance.project_id, instance.user_id, 'SALES')
    except Exception:
        logger.exception("销售成员退出写快照失败 project=%s user=%s", instance.project_id, instance.user_id)


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


# --- 全局配置变更 → 项目同步 ---

# ================================================================
#  成员成绩快照写入口
# ================================================================
def _snapshot_factor_for(project):
    """取项目等级因子（无等级则 1.00）。"""
    if project.grade_id:
        try:
            return project.grade.factor
        except Exception:
            return Decimal('1.00')
    return Decimal('1.00')


def _record_member_snapshot(project, user_id, track, quality_score, workload_share, grade_factor, snapshot_at):
    """计算并写入单条快照（幂等：与最新一条值相同时跳过）。"""
    if workload_share is None:
        workload_share = Decimal('0.00')
    factor = grade_factor if grade_factor is not None else Decimal('1.00')

    workload = (quality_score * workload_share / Decimal('100.0')).quantize(Decimal('0.01'))
    effective = (workload * factor).quantize(Decimal('0.01'))

    latest = (
        MemberScoreSnapshot.objects.filter(project_id=project.pk, user_id=user_id, track=track)
        .order_by('-snapshot_at', '-pk')
        .first()
    )
    if latest and latest.effective_score == effective and latest.workload_score == workload:
        return None

    return MemberScoreSnapshot.objects.create(
        project_id=project.pk,
        user_id=user_id,
        track=track,
        snapshot_at=snapshot_at,
        effective_score=effective,
        workload_score=workload,
        quality_score=quality_score,
        workload_share=workload_share,
        grade_factor=factor,
    )


def record_project_score_snapshots(project):
    """为 project 的所有 RD/SALES 在册成员写幂等快照。"""
    snapshot_at = timezone.now()
    rd_quality = project.quality_score or Decimal('0.00')
    sales_quality = project.sales_quality_score or Decimal('0.00')
    factor = _snapshot_factor_for(project)

    created = 0
    for member in project.members.all():
        if _record_member_snapshot(
            project, member.user_id, 'RD', rd_quality,
            member.workload_share, factor, snapshot_at,
        ):
            created += 1
    for member in project.sales_members.all():
        if _record_member_snapshot(
            project, member.user_id, 'SALES', sales_quality,
            member.workload_share, factor, snapshot_at,
        ):
            created += 1
    return created


def record_member_exit_snapshot(project_id, user_id, track):
    """成员退出项目时写一条 0 分终止快照，使其在该项目的累计分归零。"""
    return MemberScoreSnapshot.objects.create(
        project_id=project_id,
        user_id=user_id,
        track=track,
        snapshot_at=timezone.now(),
        effective_score=Decimal('0.00'),
        workload_score=Decimal('0.00'),
        quality_score=Decimal('0.00'),
        workload_share=Decimal('0.00'),
        grade_factor=Decimal('1.00'),
    )


def recalculate_project_scores(project):
    """公共重算入口：刷新项目冗余分（quality_score 等）并写成员快照。

    供 admin 兜底与 backfill 命令复用，绕过信号时序依赖。
    """
    _update_project_current_stage(project)
    record_project_score_snapshots(project)


@receiver(post_save, sender=ProjectConfig)
def sync_default_workflow_to_projects(sender, instance, **kwargs):
    """全局默认审批流程变更后，所有项目统一同步为新默认流程"""
    Project.objects.update(approval_workflow=instance.default_approval_workflow)


# ================================================================
#  等级因子变更 / 项目换等级 → 写快照
# ================================================================
# 记录 Project 保存前的 grade_id，用于检测「项目换等级」这一外键变化。
_project_grade_cache = {}


@receiver(pre_save, sender=Project)
def _cache_project_grade(sender, instance, **kwargs):
    if instance.pk:
        _project_grade_cache[instance.pk] = Project.objects.filter(pk=instance.pk).values_list('grade_id', flat=True).first()


@receiver(post_save, sender=Project)
def _project_grade_changed(sender, instance, created, **kwargs):
    """项目换等级（grade 外键变化）→ 重算并写快照。"""
    if created or not instance.pk:
        return
    old_grade = _project_grade_cache.pop(instance.pk, None)
    if old_grade != instance.grade_id:
        try:
            record_project_score_snapshots(instance)
        except Exception:
            logger.exception("项目换等级写快照失败 project=%s", instance.pk)


def _record_grade_factor_changed(grade):
    """GradeFactor 值变更后，重算并写快照到所有引用它的项目。

    注意：传入的 grade 可能是已从 DB 删除的实例，需靠调用方预先缓存
    被引用的 project id，否则 SET_NULL 置空后 filter 已查不到项目。
    """
    try:
        from app_repository.models import GradeFactor
        project_ids = Project.objects.filter(grade=grade).values_list('pk', flat=True)
        for pk in project_ids:
            try:
                project = Project.objects.get(pk=pk)
                record_project_score_snapshots(project)
            except Exception:
                logger.exception("等级因子变更写快照失败 project=%s", pk)
    except Exception:
        logger.exception("等级因子变更处理失败 grade=%s", getattr(grade, 'pk', None))


# 缓存 GradeFactor 删除前被引用的 project id（SET_NULL 置空后 filter 查不到）
_grade_factor_projects_cache = {}


@receiver(pre_delete, sender='app_repository.GradeFactor')
def _cache_grade_factor_projects(sender, instance, **kwargs):
    _grade_factor_projects_cache[instance.pk] = list(
        Project.objects.filter(grade_id=instance.pk).values_list('pk', flat=True)
    )


@receiver(post_save, sender='app_repository.GradeFactor')
def grade_factor_saved(sender, instance, **kwargs):
    _record_grade_factor_changed(instance)


@receiver(post_delete, sender='app_repository.GradeFactor')
def grade_factor_deleted(sender, instance, **kwargs):
    """删除等级因子：刷新被引用项目（grade 已被 SET_NULL 置 1.00）。"""
    project_ids = _grade_factor_projects_cache.pop(instance.pk, [])
    for pk in project_ids:
        try:
            project = Project.objects.get(pk=pk)
            record_project_score_snapshots(project)
        except Exception:
            logger.exception("等级因子删除写快照失败 project=%s", pk)
