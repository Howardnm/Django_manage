"""
app_project 伪数据生成器

业务逻辑：
  - Project 创建时 signal 自动生成 9 个 PENDING ProjectNode（9 个阶段）
  - 按业务推进节点状态：DONE → DOING/PAUSED → PENDING
  - ProjectRepository 关联 Customer/OEM/Salesperson
  - ProjectMember + ProjectSalesMember 分配项目人员和工作量
  - ~15% 项目在研发/小试/中试阶段设置为终止（FAILED → TERMINATED）
"""

import random
from decimal import Decimal
from django.db import transaction
from django.db.models import Max
from ._base import FakeContext, pick_one, pick, rand_decimal, COUNT_PROJECTS


@transaction.atomic
def run(ctx: FakeContext) -> None:
    print("\n[7/16] Creating projects...")

    from app_project.models import (
        Project, ProjectNode, ProjectMember, ProjectSalesMember, ProjectStage,
    )
    from app_repository.models import ProjectRepository
    from app_project.utils.signals import _update_project_current_stage

    ordered_stages = [
        ProjectStage.INIT, ProjectStage.COLLECT, ProjectStage.FEASIBILITY,
        ProjectStage.PRICING, ProjectStage.RND, ProjectStage.PILOT,
        ProjectStage.MID_TEST, ProjectStage.MASS_PROD, ProjectStage.ORDER,
    ]
    oem_nicks = ["吉利", "长城", "比亚迪", "蔚来", "小鹏"]
    project_templates = [
        ("汽车内饰件", "PP-TD20"), ("前端模块", "PA66-GF30"),
        ("灯罩", "PC-HT"), ("保险杠", "PP-EPDM"),
        ("连接器", "PBT-GF30"), ("风扇叶片", "PA6-GF15"),
        ("密封条", "TPE"), ("电池包支架", "PPS-GF40"),
        ("进气歧管", "PA6-GF30"), ("轮毂罩", "ABS"),
        ("门板", "PP-TD15"), ("仪表板", "PP-GF20"),
        ("充电枪", "PC-FR"), ("底护板", "PA6-MD20"),
        ("水室", "PA66-GF35"),
    ]

    projects = []
    for i in range(COUNT_PROJECTS):
        if i < len(project_templates):
            app_name, mat = project_templates[i]
        else:
            app_name = f"产品_{random.randint(100, 999)}"
            mat = f"材料-{random.randint(10, 99)}"

        p = Project.objects.create(
            name=f"{pick_one(oem_nicks)} {app_name} {mat} #{random.randint(100, 999)}",
            manager=pick_one(ctx.rnd_users),
            material=pick_one(ctx.materials) if random.random() < 0.6 else None,
            grade=pick_one(ctx.grades),
            approval_workflow=pick_one(ctx.workflow_defs) if random.random() < 0.5 else None,
        )
        # signal auto-creates 9 PENDING nodes — 现在推进状态
        target_idx = random.randint(0, len(ordered_stages))
        all_nodes = list(p.nodes.all().order_by('order'))
        for idx, node in enumerate(all_nodes):
            if idx < target_idx:
                node.status = 'DONE'
                node.remark = f"phase {idx + 1} done"
            elif idx == target_idx and idx < len(all_nodes):
                node.status = random.choice(['DOING', 'DOING', 'DOING', 'PAUSED'])
                node.remark = "in progress"
            else:
                node.status = 'PENDING'
            node.save()

        # --- ProjectRepository ---
        repo = p.repository
        repo.customer = pick_one(ctx.customers) if random.random() < 0.8 else None
        repo.oem = pick_one(ctx.oem_list) if random.random() < 0.6 else None
        repo.salesperson = pick_one(ctx.sales_users) if random.random() < 0.7 else None
        repo.target_cost = rand_decimal(15, 60, 2) if random.random() < 0.5 else None
        repo.save()

        # --- ProjectMember ---
        role_pool = [('PROCESS', 20), ('RND', 50), ('SALES', 30), ('ASSIST', 10)]
        for role, share in pick(role_pool, random.randint(1, 3)):
            pool_map = {
                'RND': ctx.rnd_users,
                'PROCESS': ctx.proc_users,
                'SALES': ctx.sales_users,
                'ASSIST': ctx.rnd_users + ctx.proc_users,
            }
            ProjectMember.objects.get_or_create(
                project=p, user=pick_one(pool_map[role]),
                defaults={'role': role, 'workload_share': Decimal(str(share))},
            )
        if random.random() < 0.3:
            ProjectSalesMember.objects.get_or_create(
                project=p, user=pick_one(ctx.sales_users),
                defaults={'workload_share': rand_decimal(20, 80, 2)},
            )

        projects.append(p)

    # --- 终止项目（~15%） ---
    for p in pick(projects, max(2, COUNT_PROJECTS // 7)):
        rnd_nodes = [n for n in p.nodes.all() if n.stage in ['RND', 'PILOT', 'MID_TEST']]
        if rnd_nodes:
            node = pick_one(rnd_nodes)
            node.status = 'FAILED'
            node.remark = "terminated due to performance issue"
            node.save()
            max_o = p.nodes.aggregate(Max('order'))['order__max'] or 0
            ProjectNode.objects.create(
                project=p, stage=ProjectStage.ORDER, order=max_o + 1,
                round=1, status='TERMINATED', remark="project terminated",
            )
            _update_project_current_stage(p)

    ctx.projects = projects

    print(f"  projects={len(projects)}, nodes={ProjectNode.objects.count()}")
