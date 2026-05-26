"""
伪数据生成器
补充 management commands 未覆盖的测试数据，生成有业务关联的伪数据。

已由 management commands 导入的数据（本脚本不再重复创建）：
  - MaterialType, ApplicationScenario  → import_base_data
  - MetricCategory, TestConfig        → import_configs
  - RawMaterialType                    → import_raw_material_types
  - Supplier                           → import_suppliers
  - RawMaterial                        → import_raw_materials
  - OEM                                → import_oems
  - NodeScoreRule                      → init_performance_rules

用法: python init/generate_fake_data.py
"""

import os
import sys
import random
import datetime
from decimal import Decimal

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Django_manage.settings')
import django
django.setup()

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

User = get_user_model()

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
COUNT_RND = 8
COUNT_PROCESS = 4
COUNT_SALES = 5
COUNT_PURCH = 2
COUNT_CUSTOMERS = 10
COUNT_MATERIALS = 12
COUNT_MACHINES = 5
COUNT_SCREW_COMBINATIONS = 6
COUNT_PROCESS_PROFILES = 8
COUNT_PROJECTS = 15
COUNT_RESEARCH_PROJECTS = 6
COUNT_FORMULAS = 20
COUNT_WORKFLOW_DEFS = 3
COUNT_FORM_TEMPLATES = 4
COUNT_CATALOG_PRODUCTS = 10
COUNT_NOTIFICATIONS = 30

# ---------------------------------------------------------------------------
# Faker
# ---------------------------------------------------------------------------
try:
    from faker import Faker
    fake = Faker('zh_CN')
except ImportError:
    class SimpleFaker:
        def name(self): return f"测试员_{random.randint(100, 999)}"
        def company(self): return f"公司_{random.randint(1000, 9999)}"
        def email(self): return f"user_{random.randint(1000, 9999)}@example.com"
        def phone_number(self): return f"138{random.randint(10000000, 99999999)}"
        def address(self): return f"地址_{random.randint(100, 999)}号"
        def text(self, nb=50): return f"描述文本_{random.randint(1000, 9999)}"
        def url(self): return f"https://www.example{random.randint(1,99)}.com"
    fake = SimpleFaker()

# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def pick_one(items):
    return random.choice(items) if items else None

def pick(items, k=1):
    if not items:
        return []
    return random.sample(items, min(k, len(items)))

def rand_decimal(min_v=0, max_v=100, precision=2):
    return Decimal(f"{random.uniform(min_v, max_v):.{precision}f}")

def rand_date(days_back=365):
    return timezone.now().date() - datetime.timedelta(days=random.randint(0, days_back))


# ===========================================================================
# 主逻辑
# ===========================================================================
@transaction.atomic
def run():
    print("=" * 60)
    print("  Fake data generator")
    print("=" * 60)

    # ------------------------------------------------------------------
    # Phase 1: 读取已导入的基础数据 (management commands 已处理)
    # ------------------------------------------------------------------
    print("\n[1/8] Reading existing seed data...")

    from app_material.models.material import MaterialType, TestConfig, ApplicationScenario
    from app_material.models.material import MetricCategory
    from app_raw_material.models import RawMaterialType, Supplier, RawMaterial
    from app_repository.models import OEM, Customer
    from app_project.models import NodeScoreRule

    material_types = list(MaterialType.objects.all())
    test_configs = list(TestConfig.objects.all())
    scenarios = list(ApplicationScenario.objects.all())
    categories = list(MetricCategory.objects.all())
    raw_material_types = list(RawMaterialType.objects.all())
    suppliers = list(Supplier.objects.all())
    raw_materials = list(RawMaterial.objects.all())
    oem_list = list(OEM.objects.all())

    print(f"  Types: material={len(material_types)}, test_config={len(test_configs)}, "
          f"scenario={len(scenarios)}, category={len(categories)}")
    print(f"  Raw: material_type={len(raw_material_types)}, supplier={len(suppliers)}, "
          f"raw_material={len(raw_materials)}, OEM={len(oem_list)}")

    # ------------------------------------------------------------------
    # Phase 2: 基础配置 (Department, MaterialCharacteristic, GradeFactor, Customer)
    # ------------------------------------------------------------------
    print("\n[2/8] Creating base config...")

    from app_user.models import Department
    depts = {}
    for name, code in [("研发中心", "RND"), ("工艺工程部", "PROCESS"),
                        ("销售部", "SALES"), ("供应链中心", "PURCH")]:
        depts[code], _ = Department.objects.get_or_create(name=name, defaults={'code': code})

    from app_material.models.material import MaterialCharacteristic
    characteristics = []
    for name in ["高刚性", "高韧性", "耐高温", "耐化学", "阻燃", "导电",
                  "抗UV", "低翘曲", "高光泽", "免喷涂", "可降解", "轻量化"]:
        obj, _ = MaterialCharacteristic.objects.get_or_create(name=name)
        characteristics.append(obj)

    from app_repository.models import GradeFactor
    grades = []
    for name, factor in [("A级", 1.50), ("B级", 1.20), ("C级", 1.00), ("D级", 0.80)]:
        obj, _ = GradeFactor.objects.get_or_create(name=name, defaults={'factor': factor})
        grades.append(obj)

    # Customer (management commands 未导入)
    customers = list(Customer.objects.all())
    if len(customers) < COUNT_CUSTOMERS:
        for i in range(COUNT_CUSTOMERS - len(customers)):
            name = f"{fake.company()}_{random.randint(100, 999)}"
            obj, _ = Customer.objects.get_or_create(
                company_name=name,
                defaults={'short_name': name[:4], 'address': fake.address()},
            )
            customers.append(obj)
    print(f"  dept={len(depts)}, characteristics={len(characteristics)}, "
          f"grades={len(grades)}, customers={len(customers)}")

    # ------------------------------------------------------------------
    # Phase 3: 用户
    # ------------------------------------------------------------------
    print("\n[3/8] Creating users...")

    def create_user(username, role, dept=None, level=1, customer=None, oem=None):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'user_type': role, 'department': dept, 'user_level': level,
                'associated_customer': customer, 'associated_oem': oem,
                'first_name': fake.name(),
                'email': f"{username}@sunwill.com.cn",
                'phone': fake.phone_number(),
                'is_staff': role not in ['CUSTOMER', 'OEM'],
            },
        )
        if created:
            user.set_password('Sunwill@123')
            user.save()
        return user

    admin = create_user("admin", "ADMIN", depts['RND'], 15)
    rnd_users = [create_user(f"rnd_{i}", "ENGINEER", depts['RND'],
                              random.randint(1, 15)) for i in range(COUNT_RND)]
    proc_users = [create_user(f"proc_{i}", "PROCESS_ENGINEER", depts['PROCESS'],
                               random.randint(3, 12)) for i in range(COUNT_PROCESS)]
    sales_users = [create_user(f"sales_{i}", "SALES", depts['SALES'],
                                random.randint(1, 10)) for i in range(COUNT_SALES)]
    purch_users = [create_user(f"purch_{i}", "PURCHASING", depts['PURCH'],
                                random.randint(1, 8)) for i in range(COUNT_PURCH)]

    all_internal = rnd_users + proc_users + sales_users + purch_users + [admin]
    print(f"  users: {len(all_internal)} internal")

    # ------------------------------------------------------------------
    # Phase 4: 材料库 & 原材料属性
    # ------------------------------------------------------------------
    print("\n[4/8] Creating material library...")

    from app_material.models.material import MaterialLibrary, MaterialDataPoint

    manufacturer_names = ["金发", "普利特", "巴斯夫", "杜邦", "帝斯曼", "旭化成", "宝理"]
    flammability_choices = ["HB", "V-2", "V-0", "5VB"]
    prefix_list = ["G", "H", "K", "L", "M", "N", "P", "R", "S", "T", "X", "Z"]
    materials = []

    for i in range(COUNT_MATERIALS):
        prefix = prefix_list[i % len(prefix_list)]
        grade_name = (f"{prefix}{random.randint(100, 999)}"
                      f"{random.choice(['A', 'B', 'C', ''])}"
                      f"-{random.choice(['H', 'N', 'G', ''])}{random.randint(10, 99)}")
        m, created = MaterialLibrary.objects.get_or_create(
            grade_name=grade_name,
            defaults={
                'manufacturer': pick_one(manufacturer_names),
                'category': pick_one(material_types),
                'is_published': random.random() < 0.7,
                'flammability': pick_one(flammability_choices),
            },
        )
        if created:
            m.characteristics.set(pick(characteristics, random.randint(2, 5)))
            m.scenarios.set(pick(scenarios, random.randint(1, 3)))
        materials.append(m)

    dp_count = 0
    for m in materials:
        for tc in pick(test_configs, random.randint(8, 14)):
            value = None
            value_text = ""
            if tc.data_type == "NUMBER":
                value = rand_decimal(0.1, 500, 1)
            elif tc.data_type == "SELECT":
                value_text = pick_one(["V-0", "V-2", "HB", "Pass", "Fail", "合格"])
            _, created = MaterialDataPoint.objects.get_or_create(
                material=m, test_config=tc,
                defaults={'value': value, 'value_text': value_text},
            )
            if created:
                dp_count += 1
    print(f"  materials: {len(materials)}, data_points: {dp_count}")

    # RawMaterialProperty (为已有原材料补充属性)
    from app_raw_material.models import RawMaterialProperty
    rmp_count = 0
    for rm in pick(raw_materials, min(15, len(raw_materials))):
        for tc in pick(test_configs, random.randint(3, 8)):
            _, created = RawMaterialProperty.objects.get_or_create(
                raw_material=rm, test_config=tc,
                defaults={
                    'value': rand_decimal(0.1, 300, 1) if tc.data_type == "NUMBER" else None,
                    'value_text': pick_one(["合格", "优", "-"]) if tc.data_type != "NUMBER" else "",
                },
            )
            if created:
                rmp_count += 1
    print(f"  raw_material_properties: {rmp_count}")

    # ------------------------------------------------------------------
    # Phase 5: 工艺数据
    # ------------------------------------------------------------------
    print("\n[5/8] Creating process data...")

    from app_process.models import MachineModel, ScrewCombination, ProcessProfile

    machine_brands = ["科倍隆", "莱斯特瑞兹", "JSW", "东芝", "南京科亚"]
    machines = []
    for i in range(COUNT_MACHINES):
        brand = machine_brands[i]
        model_name = f"{brand}-{random.randint(35, 95)}"
        obj, created = MachineModel.objects.get_or_create(
            model_name=model_name,
            defaults={
                'brand': brand, 'machine_code': 100 + i,
                'screw_diameter': random.choice([35, 50, 65, 75, 95]),
                'ld_ratio': random.choice([32, 40, 44, 48, 52]),
                'motor_power': random.choice([55, 90, 160, 250, 400]),
                'max_speed': random.choice([600, 800, 1000, 1200]),
            },
        )
        if created:
            obj.suitable_materials.set(pick(material_types, random.randint(3, 8)))
        machines.append(obj)

    screw_combinations = []
    screw_types = ['高剪切', '中剪切', '低剪切', '通用型', '阻燃专用', 'GF专用']
    for i in range(COUNT_SCREW_COMBINATIONS):
        obj, created = ScrewCombination.objects.get_or_create(
            name=f"螺杆组合-{screw_types[i % len(screw_types)]}{i + 1}",
            defaults={'combination_code': 200 + i},
        )
        if created:
            obj.machines.set(pick(machines, random.randint(1, 3)))
            obj.suitable_materials.set(pick(material_types, random.randint(3, 6)))
        screw_combinations.append(obj)

    process_names = ['PP增强', 'PA6阻燃', 'PC/ABS', 'PA66-GF30', 'PPS', '弹性体', '通用PP', 'PA6增韧']
    process_profiles = []
    for i in range(COUNT_PROCESS_PROFILES):
        machine = pick_one(machines)
        obj, created = ProcessProfile.objects.get_or_create(
            name=f"工艺-{machine.brand}-{process_names[i % len(process_names)]}",
            defaults={
                'machine': machine,
                'screw_combination': pick_one(screw_combinations),
                'screw_speed': random.randint(200, 800),
                'throughput': rand_decimal(100, 500, 1),
                'temp_zone_1': random.randint(180, 240),
                'temp_zone_2': random.randint(200, 260),
                'temp_zone_3': random.randint(210, 270),
                'temp_zone_4': random.randint(220, 280),
                'temp_zone_5': random.randint(220, 280),
                'temp_head': random.randint(230, 290),
                'melt_pressure': rand_decimal(20, 80, 1),
                'melt_temp': random.randint(230, 300),
                'vacuum': rand_decimal(-0.1, -0.06, 2),
                'main_feeder_speed': rand_decimal(20, 80, 1),
                'cooling_method': pick_one(['WATER_STRAND', 'WATER_RING', 'UNDERWATER']),
                'strand_count': random.randint(3, 12),
                'water_temp': random.randint(20, 35),
                'pelletizing_speed': rand_decimal(50, 200, 1),
                'creator': pick_one(rnd_users + proc_users),
            },
        )
        if created:
            obj.material_types.set(pick(material_types, random.randint(1, 4)))
        process_profiles.append(obj)

    print(f"  machines={len(machines)}, screws={len(screw_combinations)}, "
          f"profiles={len(process_profiles)}")

    # ------------------------------------------------------------------
    # Phase 6: 工作流定义 + 项目 + 预研
    # ------------------------------------------------------------------
    print("\n[6/8] Creating workflow / projects / research...")

    from app_workflow.models import WorkflowDefinition

    wf_names = ['研发评审', '量产放行', '异常审批', '阶段评审', '项目立项']
    BPMN = (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">'
        '<bpmn:process id="Process_1">'
        '<bpmn:startEvent id="Start"/><bpmn:endEvent id="End"/>'
        '</bpmn:process></bpmn:definitions>'
    )
    workflow_defs = []
    for i in range(COUNT_WORKFLOW_DEFS):
        name = f"{wf_names[i % len(wf_names)]}流程"
        obj, created = WorkflowDefinition.objects.get_or_create(
            name=name,
            defaults={
                'description': f"{name} - auto generated",
                'bpmn_xml': BPMN, 'created_by': admin,
            },
        )
        workflow_defs.append(obj)

    # --- 项目 ---
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
            manager=pick_one(rnd_users),
            material=pick_one(materials) if random.random() < 0.6 else None,
            grade=pick_one(grades),
            approval_workflow=pick_one(workflow_defs) if random.random() < 0.5 else None,
        )
        # signal auto-creates 9 PENDING nodes

        # 推进节点状态
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

        # repository
        repo = p.repository
        repo.customer = pick_one(customers) if random.random() < 0.8 else None
        repo.oem = pick_one(oem_list) if random.random() < 0.6 else None
        repo.salesperson = pick_one(sales_users) if random.random() < 0.7 else None
        repo.target_cost = rand_decimal(15, 60, 2) if random.random() < 0.5 else None
        repo.save()

        # members
        for role, share in pick([('PROCESS', 0.2), ('RND', 0.5), ('SALES', 0.3), ('ASSIST', 0.1)],
                                random.randint(1, 3)):
            pool = {'RND': rnd_users, 'PROCESS': proc_users,
                    'SALES': sales_users, 'ASSIST': rnd_users + proc_users}[role]
            ProjectMember.objects.get_or_create(
                project=p, user=pick_one(pool),
                defaults={'role': role, 'workload_share': Decimal(str(share))},
            )
        if random.random() < 0.3:
            ProjectSalesMember.objects.get_or_create(
                project=p, user=pick_one(sales_users),
                defaults={'workload_share': rand_decimal(0.2, 0.8, 2)},
            )
        projects.append(p)

    # ~15% 终止
    for p in pick(projects, max(2, COUNT_PROJECTS // 7)):
        rnd_nodes = [n for n in p.nodes.all() if n.stage in ['RND', 'PILOT', 'MID_TEST']]
        if rnd_nodes:
            node = pick_one(rnd_nodes)
            node.status = 'FAILED'
            node.remark = "terminated due to performance issue"
            node.save()
            from django.db.models import Max
            max_o = p.nodes.aggregate(Max('order'))['order__max'] or 0
            ProjectNode.objects.create(
                project=p, stage=ProjectStage.ORDER, order=max_o + 1,
                round=1, status='TERMINATED', remark="project terminated",
            )
            _update_project_current_stage(p)

    # --- 预研项目 ---
    from app_basic_research.models import ResearchProject, ResearchProjectNode, ResearchStage
    rp_stages = [ResearchStage.INIT, ResearchStage.LITERATURE, ResearchStage.PLANNING,
                 ResearchStage.EXPERIMENT, ResearchStage.ANALYSIS, ResearchStage.CONCLUSION]
    rp_topics = ['生物基PA', '纳米复合材料', '导电高分子', '自修复材料', '导热塑料', '可降解']

    for i in range(COUNT_RESEARCH_PROJECTS):
        rp = ResearchProject.objects.create(
            name=f"{rp_topics[i]} 预研", manager=pick_one(rnd_users),
            description=fake.text(80),
        )
        for j, stage in enumerate(rp_stages):
            ResearchProjectNode.objects.create(
                project=rp, stage=stage, order=j + 1, round=1, status='PENDING',
            )
        all_nodes = list(rp.nodes.all().order_by('order'))
        target = random.randint(1, len(all_nodes))
        for idx, node in enumerate(all_nodes):
            if idx < target:
                node.status = 'DONE'
                node.remark = "done" if idx < target - 1 else "in progress"
            elif idx == target:
                node.status = random.choice(['DOING', 'DOING', 'PAUSED'])
            node.save()

    print(f"  projects={len(projects)}, nodes={ProjectNode.objects.count()}, "
          f"research={COUNT_RESEARCH_PROJECTS}, workflows={len(workflow_defs)}")

    # ------------------------------------------------------------------
    # Phase 7: 配方
    # ------------------------------------------------------------------
    print("\n[7/8] Creating formulas...")

    from app_formula.models import LabFormula, FormulaBOM, FormulaTestResult

    feeding_ports = ['1_MAIN', '2_SIDE_1', '3_SIDE_2', '4_LIQUID']
    weighing_scales = ['A', 'B', 'C', 'D', 'E']
    today_str = timezone.now().strftime('%Y%m%d')

    formulas = []
    for i in range(COUNT_FORMULAS):
        project = pick_one(projects)
        p_nodes = list(project.nodes.filter(stage__in=['RND', 'PILOT', 'MID_TEST', 'MASS_PROD']))
        p_node = pick_one(p_nodes) if p_nodes else None

        code_prefix = f"L{today_str}"
        last = LabFormula.objects.filter(code__startswith=code_prefix).order_by('code').last()
        seq = (int(last.code.split('-')[-1]) + 1) if last else 1
        code = f"{code_prefix}-{seq:02d}"

        f = LabFormula.objects.create(
            code=code,
            name=f"{project.name} - {p_node.get_stage_display() if p_node else 'RND'} formula",
            material_type=pick_one(material_types),
            process=pick_one(process_profiles) if random.random() < 0.3 else None,
            project=project, project_node=p_node, version=1,
            creator=pick_one(rnd_users),
            cost_predicted=rand_decimal(10, 50, 2),
            cost_actual=rand_decimal(12, 55, 2) if random.random() < 0.4 else None,
            description=fake.text(60) if random.random() < 0.5 else "",
        )

        # BOM
        bom_mats = pick(raw_materials, random.randint(5, 10))
        total = Decimal('0')
        for j, rm in enumerate(bom_mats):
            rem = len(bom_mats) - j - 1
            pct = Decimal('100') - total if rem == 0 else rand_decimal(1, max(1, float(100 - total) - rem), 2)
            total += pct
            FormulaBOM.objects.create(
                formula=f, feeding_port=pick_one(feeding_ports),
                weighing_scale=pick_one(weighing_scales), raw_material=rm,
                percentage=pct,
                is_tail=random.random() < 0.15,
                is_pre_mix=random.random() < 0.2,
                pre_mix_order=random.randint(0, 3) if random.random() < 0.2 else 0,
            )

        # test results
        for tc in pick(test_configs, random.randint(8, 16)):
            value = None
            value_text = ""
            if random.random() < 0.6:
                if tc.data_type == "NUMBER":
                    value = rand_decimal(0.05, 400, 1)
                elif tc.data_type == "SELECT":
                    value_text = pick_one(["V-0", "V-2", "HB", "Pass", "Fail"])
                else:
                    value_text = fake.text(10)
            if value is not None or value_text:
                FormulaTestResult.objects.create(
                    formula=f, test_config=tc, value=value, value_text=value_text,
                    test_date=rand_date() if random.random() < 0.7 else None,
                )
        formulas.append(f)

    # 多版本配方
    for f in pick(formulas, 5):
        for v in range(2, random.randint(2, 4)):
            f2 = LabFormula.objects.create(
                code=f.code, name=f"{f.name} v{v}",
                material_type=f.material_type, process=f.process,
                project=f.project, project_node=f.project_node,
                version=v, creator=f.creator,
                cost_predicted=f.cost_predicted, description=f.description,
            )
            for b in f.bom_lines.all():
                FormulaBOM.objects.create(
                    formula=f2, feeding_port=b.feeding_port,
                    weighing_scale=b.weighing_scale, raw_material=b.raw_material,
                    percentage=b.percentage + rand_decimal(-5, 5, 2) if random.random() < 0.3 else b.percentage,
                    is_tail=b.is_tail, is_pre_mix=b.is_pre_mix,
                    pre_mix_order=b.pre_mix_order,
                )
            for t in f.test_results.all()[:5]:
                FormulaTestResult.objects.create(
                    formula=f2, test_config=t.test_config,
                    value=t.value + rand_decimal(-5, 5, 1) if t.value and random.random() < 0.4 else t.value,
                    value_text=t.value_text, test_date=rand_date(),
                )

    print(f"  formulas={LabFormula.objects.count()}, BOM={FormulaBOM.objects.count()}, "
          f"tests={FormulaTestResult.objects.count()}")

    # ------------------------------------------------------------------
    # Phase 8: 表单 / 手册 / 通知 / 审批实例
    # ------------------------------------------------------------------
    print("\n[8/8] Creating forms / catalog / notifications / approvals...")

    # 表单
    from app_form_management.models import FormTemplate, FormSubmission
    from django.contrib.contenttypes.models import ContentType

    form_templates = []
    for name, group in [("来料检验单", "质检"), ("出货检验单", "质检"),
                         ("实验记录表", "研发"), ("客户投诉单", "售后")]:
        t, _ = FormTemplate.objects.get_or_create(
            name=name,
            defaults={
                'group': group, 'description': f"{name} - auto generated",
                'form_config': [
                    {'type': 'text', 'label': 'title', 'key': 'title'},
                    {'type': 'textarea', 'label': 'content', 'key': 'content'},
                ],
                'workflow': pick_one(workflow_defs) if random.random() < 0.5 else None,
                'created_by': admin,
            },
        )
        form_templates.append(t)

    project_ct = ContentType.objects.get_for_model(Project)
    for _ in range(8):
        FormSubmission.objects.create(
            template=pick_one(form_templates), content_type=project_ct,
            object_id=pick_one(projects).pk, submitted_by=pick_one(all_internal),
            form_data={'title': f"submission-{random.randint(100, 999)}",
                        'content': fake.text(30)},
            status=pick_one(['DRAFT', 'SUBMITTED', 'SUBMITTED']),
        )

    # 手册
    from app_catalog.models.catalog import (
        CatalogCategory, MirrorScenario, MirrorCharacteristic, CatalogProduct,
    )
    from app_catalog.models.member import CatalogMember

    cat_categories = []
    for mt in material_types[:8]:
        obj, _ = CatalogCategory.objects.get_or_create(
            name=mt.name, defaults={'order': mt.id, 'icon': 'package'},
        )
        cat_categories.append(obj)

    mirror_scenarios = []
    for s in scenarios:
        obj, _ = MirrorScenario.objects.get_or_create(name=s.name, defaults={'remote_id': s.id})
        mirror_scenarios.append(obj)
    mirror_chars = []
    for c in characteristics[:6]:
        obj, _ = MirrorCharacteristic.objects.get_or_create(name=c.name, defaults={'remote_id': c.id})
        mirror_chars.append(obj)

    for i in range(min(COUNT_CATALOG_PRODUCTS, len(materials))):
        m = materials[i]
        obj, _ = CatalogProduct.objects.get_or_create(
            remote_material_id=m.id,
            defaults={
                'display_name': m.grade_name, 'category': pick_one(cat_categories),
                'is_published': m.is_published, 'is_featured': i < 4,
                'view_count': random.randint(10, 500),
                'download_count': random.randint(0, 50),
            },
        )
        if obj.scenarios.count() == 0:
            obj.scenarios.set(pick(mirror_scenarios, random.randint(1, 3)))
        if obj.characteristics.count() == 0:
            obj.characteristics.set(pick(mirror_chars, random.randint(1, 3)))

    for cu in [u for u in User.objects.filter(user_type='CUSTOMER')[:3]]:
        CatalogMember.objects.get_or_create(
            remote_member_token=str(cu.member_token),
            defaults={'display_name': cu.first_name, 'role': 'CUSTOMER'},
        )
    for ou in [u for u in User.objects.filter(user_type='OEM')[:3]]:
        CatalogMember.objects.get_or_create(
            remote_member_token=str(ou.member_token),
            defaults={'display_name': ou.first_name, 'role': 'OEM'},
        )

    # 通知
    from app_notification.models import Notification
    verbs = ["created project", "updated node", "submitted approval",
             "uploaded file", "reported failure", "added formula",
             "completed review", "modified BOM", "submitted test data"]
    for _ in range(COUNT_NOTIFICATIONS):
        recipient = pick_one(all_internal)
        Notification.objects.create(
            recipient=recipient,
            actor=pick_one([u for u in all_internal if u != recipient]),
            verb=pick_one(verbs),
            unread=random.random() < 0.5,
        )

    # 审批实例
    from app_workflow.models import WorkflowInstance, WorkflowTask, ApprovalHistory

    wf_inst = 0
    for p in pick(projects, 5):
        wf_def = p.approval_workflow or pick_one(workflow_defs)
        instance = WorkflowInstance.objects.create(
            definition=wf_def,
            status=pick_one(['RUNNING', 'COMPLETED', 'COMPLETED', 'COMPLETED']),
            started_by=pick_one(all_internal),
            completed_at=timezone.now() if random.random() < 0.6 else None,
        )
        wf_inst += 1
        for j in range(random.randint(1, 3)):
            assignee = pick_one(all_internal)
            status = pick_one(['COMPLETED', 'COMPLETED', 'COMPLETED', 'PENDING'])
            task = WorkflowTask.objects.create(
                instance=instance, task_name=f"approval step {j + 1}",
                assigned_to=assignee, status=status,
                spiff_task_id=f"task_{instance.id}_{j}",
            )
            if task.status == 'COMPLETED':
                ApprovalHistory.objects.create(
                    instance=instance, task=task,
                    approver=task.assigned_to or pick_one(all_internal),
                    action=pick_one(['APPROVE', 'APPROVE', 'APPROVE', 'REJECT']),
                    remark="approved" if random.random() < 0.8 else "needs revision",
                )
        active_nodes = [n for n in p.nodes.all() if n.status == 'DOING']
        if active_nodes:
            active_nodes[0].workflow_instance = instance
            active_nodes[0].status = 'AWAITING_APPROVAL'
            active_nodes[0].save()

    print(f"  forms={len(form_templates)}+{FormSubmission.objects.count()}, "
          f"catalog={min(COUNT_CATALOG_PRODUCTS, len(materials))}, "
          f"notifications={COUNT_NOTIFICATIONS}, wf_instances={wf_inst}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)
    stats = [
        ("Department", Department.objects.count()),
        ("User", User.objects.count()),
        ("Customer", Customer.objects.count()),
        ("MaterialCharacteristic", MaterialCharacteristic.objects.count()),
        ("GradeFactor", GradeFactor.objects.count()),
        ("MaterialLibrary", MaterialLibrary.objects.count()),
        ("MaterialDataPoint", MaterialDataPoint.objects.count()),
        ("RawMaterialProperty", RawMaterialProperty.objects.count()),
        ("MachineModel", MachineModel.objects.count()),
        ("ScrewCombination", ScrewCombination.objects.count()),
        ("ProcessProfile", ProcessProfile.objects.count()),
        ("WorkflowDefinition", WorkflowDefinition.objects.count()),
        ("Project", Project.objects.count()),
        ("ProjectNode", ProjectNode.objects.count()),
        ("ResearchProject", ResearchProject.objects.count()),
        ("LabFormula", LabFormula.objects.count()),
        ("FormulaBOM", FormulaBOM.objects.count()),
        ("FormulaTestResult", FormulaTestResult.objects.count()),
        ("FormTemplate", FormTemplate.objects.count()),
        ("FormSubmission", FormSubmission.objects.count()),
        ("CatalogProduct", CatalogProduct.objects.count()),
        ("CatalogMember", CatalogMember.objects.count()),
        ("Notification", Notification.objects.count()),
        ("WorkflowInstance", WorkflowInstance.objects.count()),
        ("WorkflowTask", WorkflowTask.objects.count()),
        ("ApprovalHistory", ApprovalHistory.objects.count()),
    ]
    for label, count in stats:
        print(f"  {label:<25} {count}")
    print("=" * 60)
    print("  Done!")


if __name__ == '__main__':
    run()
