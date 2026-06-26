"""
app_basic_research 伪数据生成器

业务逻辑：
  - ResearchProject：预研项目按 6 阶段推进（立项→文献调研→方案制定→实验验证→结果分析→结项）
  - ResearchProjectNode：按阶段顺序创建节点，模拟不同推进程度
  - 预研项目独立于商业项目，可通过 M2M 与配方关联
"""

import random
from django.db import transaction
from ._base import FakeContext, fake, pick_one, COUNT_RESEARCH_PROJECTS


@transaction.atomic
def run(ctx: FakeContext) -> None:
    print("\n[8/16] Creating research projects...")

    from app_basic_research.models import ResearchProject, ResearchProjectNode, ResearchStage

    rp_stages = [
        ResearchStage.INIT, ResearchStage.LITERATURE, ResearchStage.PLANNING,
        ResearchStage.EXPERIMENT, ResearchStage.ANALYSIS, ResearchStage.CONCLUSION,
    ]
    rp_topics = [
        '生物基PA', '纳米复合材料', '导电高分子',
        '自修复材料', '导热塑料', '可降解',
    ]

    for i in range(COUNT_RESEARCH_PROJECTS):
        rp = ResearchProject.objects.create(
            name=f"{rp_topics[i]} 预研",
            manager=pick_one(ctx.rnd_users),
            description=fake.text(80),
        )
        # 创建节点
        for j, stage in enumerate(rp_stages):
            ResearchProjectNode.objects.create(
                project=rp, stage=stage, order=j + 1, round=1, status='PENDING',
            )
        # 推进节点
        all_nodes = list(rp.nodes.all().order_by('order'))
        target = random.randint(1, len(all_nodes))
        for idx, node in enumerate(all_nodes):
            if idx < target:
                node.status = 'DONE'
                node.remark = "done" if idx < target - 1 else "in progress"
            elif idx == target:
                node.status = random.choice(['DOING', 'DOING', 'PAUSED'])
            node.save()

    ctx.research_projects = list(ResearchProject.objects.all())

    print(f"  research_projects={len(ctx.research_projects)}, "
          f"nodes={ResearchProjectNode.objects.count()}")
