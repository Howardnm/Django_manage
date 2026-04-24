from django.db.models import Max
from decimal import Decimal
from app_project.models import ProjectStage

def calculate_project_performance_score(project):
    """
    【新增】根据规划文档计算项目总质量得分 (S_project)。
    逻辑：取所有已终结节点 (final_score > 0) 中得分最高的那个，排除客户意见阶段。
    """
    # 获取该项目下所有非反馈阶段节点的最高得分
    max_score = project.nodes.exclude(
        stage=ProjectStage.FEEDBACK
    ).aggregate(Max('final_score'))['final_score__max']
    
    return max_score or Decimal('0.00')

def calculate_member_performance_score(member):
    """
    【新增】计算成员个人绩效得分 (S_member)。
    公式：S_member = S_project * workload_share
    """
    project_score = calculate_project_performance_score(member.project)
    member_score = project_score * member.workload_share
    
    return member_score
