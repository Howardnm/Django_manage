"""
app_workflow 伪数据生成器

业务逻辑：
  - WorkflowDefinition：从 init/bpmn/*.bpmn.xml 读取 BPMN 2.0 XML 文件导入
  - ReviewGroup：审批组，对应 BPMN 中 camunda:candidateGroups 引用的组名
  - 指派用户：对应 camunda:assignee 引用的特定用户

BPMN XML 文件（位于 init/bpmn/）：
  1. rd_review.bpmn.xml   — 研发评审流程：串行 → 并行网关（工艺复核 + 销售确认）
  2. mass_prod.bpmn.xml   — 量产放行流程：串行三步审批
  3. exception.bpmn.xml   — 异常审批流程：异常说明 → 部门负责人 → 总监裁决
"""

from pathlib import Path
from django.db import transaction
from django.contrib.auth import get_user_model
from ._base import FakeContext, COUNT_WORKFLOW_DEFS

User = get_user_model()

# BPMN XML 目录：init/bpmn/（与 init/fake/ 同级）
_BPMN_DIR = Path(__file__).resolve().parent.parent / 'bpmn'

# workflow → (xml 文件名, 流程名称)
WORKFLOW_FILES = [
    ('rd_review.bpmn.xml',   '研发评审流程'),
    ('mass_prod.bpmn.xml',   '量产放行流程'),
    ('exception.bpmn.xml',   '异常审批流程'),
]


def _read_bpmn_xml(filename: str) -> str:
    """从 init/bpmn/ 目录读取 BPMN XML 文件内容"""
    filepath = _BPMN_DIR / filename
    if not filepath.exists():
        raise FileNotFoundError(f"BPMN XML file not found: {filepath}")
    return filepath.read_text(encoding='utf-8')


@transaction.atomic
def run(ctx: FakeContext) -> None:
    print("\n[6/13] Creating workflow definitions & review groups...")

    # =====================================================================
    # 1. 创建 ReviewGroup（对接到 BPMN camunda:candidateGroups）
    # =====================================================================
    from app_user.models import ReviewGroup

    review_group_defs = {
        'dept_manager': ('部门经理审批组', [ctx.admin] + ctx.rnd_users[:3]),
        'process_lead': ('工艺主管组', ctx.proc_users[:2]),
        'sales_lead':    ('销售主管组', ctx.sales_users[:2]),
        'qa_lead':       ('品质主管组', ctx.rnd_users[3:5] if len(ctx.rnd_users) >= 5 else ctx.rnd_users[:2]),
    }

    for group_name, (desc, members) in review_group_defs.items():
        rg, _ = ReviewGroup.objects.update_or_create(
            name=group_name,
            defaults={'description': desc},
        )
        if members:
            rg.members.set(members)

    # =====================================================================
    # 2. 创建 BPMN assignee 用户（对接到 camunda:assignee）
    # =====================================================================
    def get_or_create_assignee(username, role, first_name):
        user, created = User.objects.update_or_create(
            username=username,
            defaults={
                'user_type': role,
                'department': ctx.depts.get('RND'),
                'user_level': 12,
                'first_name': first_name,
                'email': f'{username}@sunwill.com.cn',
                'is_staff': False,
            },
        )
        if created:
            user.set_password('Sunwill@123')
        user.save()
        if user not in ctx.all_internal:
            ctx.all_internal.append(user)
        return user

    rnd_dir = get_or_create_assignee('rnd_dir', 'ADMIN', '研发总监')
    prod_mgr = get_or_create_assignee('prod_mgr', 'PROCESS_ENGINEER', '生产经理')

    # =====================================================================
    # 3. 从 init/bpmn/*.xml 导入 WorkflowDefinition
    # =====================================================================
    from app_workflow.models import WorkflowDefinition

    workflow_defs = []
    for i, (filename, wf_name) in enumerate(WORKFLOW_FILES):
        if i >= COUNT_WORKFLOW_DEFS:
            break
        bpmn_xml = _read_bpmn_xml(filename)
        obj, _ = WorkflowDefinition.objects.update_or_create(
            name=wf_name,
            defaults={
                'description': f'{wf_name} — from init/bpmn/{filename}',
                'bpmn_xml': bpmn_xml,
                'created_by': ctx.admin,
            },
        )
        workflow_defs.append(obj)
    ctx.workflow_defs = workflow_defs

    print(f"  review_groups=4, assignee_users=['rnd_dir','prod_mgr'], "
          f"workflow_definitions={len(workflow_defs)}")
