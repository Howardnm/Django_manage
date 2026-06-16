"""
app_workflow 伪数据生成器

业务逻辑：
  - WorkflowDefinition：存储 BPMN XML 流程定义
  - 仅创建流程定义（审批实例在 app_project 之后，由各业务模块关联创建）
"""

import random
from django.db import transaction
from ._base import FakeContext, pick_one, COUNT_WORKFLOW_DEFS


# 最小可用的 BPMN 骨架（仅含开始/结束事件，不阻塞流程引擎解析）
BPMN_SKELETON = (
    '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">'
    '<bpmn:process id="Process_1">'
    '<bpmn:startEvent id="Start"/><bpmn:endEvent id="End"/>'
    '</bpmn:process></bpmn:definitions>'
)


@transaction.atomic
def run(ctx: FakeContext) -> None:
    print("\n[6/13] Creating workflow definitions...")

    from app_workflow.models import WorkflowDefinition

    wf_names = ['研发评审', '量产放行', '异常审批']
    workflow_defs = []
    for i in range(COUNT_WORKFLOW_DEFS):
        name = f"{wf_names[i % len(wf_names)]}流程"
        obj, created = WorkflowDefinition.objects.get_or_create(
            name=name,
            defaults={
                'description': f"{name} - auto generated",
                'bpmn_xml': BPMN_SKELETON,
                'created_by': ctx.admin,
            },
        )
        workflow_defs.append(obj)
    ctx.workflow_defs = workflow_defs

    print(f"  workflow_definitions={len(workflow_defs)}")
