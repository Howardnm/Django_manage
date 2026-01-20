import os
import sys
import django
import random
import uuid
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from faker import Faker
from decimal import Decimal

# ================= 配置区域 =================
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Django_manage.settings')
django.setup()

from django.contrib.auth.models import User
from app_repository.models import (
    MaterialType, ApplicationScenario, MaterialLibrary,
    Customer, OEM, Salesperson, MetricCategory, TestConfig, MaterialDataPoint,
    MaterialFile, ProjectRepository, ProjectFile
)
from app_raw_material.models import Supplier, RawMaterialType, RawMaterial, RawMaterialProperty
from app_process.models import ProcessType, MachineModel, ScrewCombination, ProcessProfile
from app_formula.models import LabFormula, FormulaBOM, FormulaTestResult
from app_project.models import Project, ProjectNode, ProjectStage

# 参数设置 (压力测试规模)
NUM_USERS = 5
NUM_CUSTOMERS = 50000
NUM_SUPPLIERS = 20000
NUM_OEMS = 20000
NUM_SALES = 1000
NUM_MATERIALS = 20000  # 成品材料数量
NUM_RAW_MATERIALS = 20000 # 原材料数量
NUM_MACHINES = 100
NUM_SCREWS = 200
NUM_PROFILES = 50
NUM_FORMULAS = 20000  # 配方数量
NUM_PROJECTS = 20000  # 项目数量
BATCH_SIZE = 500

fake = Faker('zh_CN')

def print_step(msg):
    print(f"🔹 {msg}")

def clean_data():
    print_step("正在清空旧数据 (危险操作)...")
    # 按依赖关系反向删除
    ProjectFile.objects.all().delete()
    ProjectRepository.objects.all().delete()
    ProjectNode.objects.all().delete()
    Project.objects.all().delete()
    
    FormulaTestResult.objects.all().delete()
    FormulaBOM.objects.all().delete()
    LabFormula.objects.all().delete()
    
    ProcessProfile.objects.all().delete()
    ScrewCombination.objects.all().delete()
    MachineModel.objects.all().delete()
    ProcessType.objects.all().delete()
    
    RawMaterialProperty.objects.all().delete()
    RawMaterial.objects.all().delete()
    RawMaterialType.objects.all().delete()
    Supplier.objects.all().delete()
    
    MaterialFile.objects.all().delete()
    MaterialDataPoint.objects.all().delete()
    MaterialLibrary.objects.all().delete()
    
    Salesperson.objects.all().delete()
    OEM.objects.all().delete()
    Customer.objects.all().delete()
    
    print("   ... 旧数据已清空")

def get_random_remark(stage_code, status):
    """生成随机的阶段描述"""
    if status == 'PENDING':
        return ""
    if status == 'TERMINATED':
        return random.choice(["客户取消项目", "成本无法达成", "技术指标无法突破", "竞品低价抢单", "项目暂停"])
    if status == 'FAILED':
        return random.choice(["测试数据不达标", "客户验证失败", "外观缺陷严重", "成本超支", "阻燃测试不过"])
    
    # DONE 或 DOING 的正常备注
    remarks = {
        'INIT': ["项目立项审批中", "已召开启动会", "等待客户确认需求", "项目组建完成", "立项资料已归档"],
        'COLLECT': ["收到客户3D图纸", "正在分析物性表", "竞品分析完成", "等待客户提供标准", "技术参数确认中"],
        'FEASIBILITY': ["模流分析进行中", "成本核算完成", "技术可行性通过", "风险评估报告已出", "模具结构评审中"],
        'PRICING': ["报价单已发出", "客户觉得价格偏高，协商中", "价格已确认", "等待财务审核报价", "第二轮议价"],
        'RND': ["第一次试料完成", "配方调整：增加玻纤含量", "颜色匹配中", "实验室测试数据良好", "冲击强度待优化", "寄送首样"],
        'PILOT': ["客户小试样件寄出", "小试反馈：尺寸偏大", "小试通过，准备中试", "等待客户装机验证", "小批量试装"],
        'MID_TEST': ["中试生产500kg", "中试过程稳定", "等待客户中试报告", "加工工艺窗口确认", "现场技术支持中"],
        'MASS_PROD': ["PPAP文件准备中", "量产排期确认", "首批订单已排产", "产能评估通过", "SOP文件发布"],
        'ORDER': ["收到正式PO", "首批大货已发运", "持续供货中", "季度订单预测更新", "发货通知已出"],
        'FEEDBACK': ["客户投诉：表面流纹", "客户要求降本", "年度审核通过", "客户满意度调查", "售后技术支持"]
    }
    return random.choice(remarks.get(stage_code, ["进行中...", "阶段推进中"]))

def init_users():
    print_step("初始化用户...")
    users = []
    admin, _ = User.objects.get_or_create(username='admin', defaults={'is_staff': True, 'is_superuser': True})
    if _:
        admin.set_password('admin123')
        admin.save()
    users.append(admin)
    for i in range(1, NUM_USERS + 1):
        u, created = User.objects.get_or_create(username=f'engineer{i}')
        if created:
            u.set_password('123456')
            u.save()
        users.append(u)
    return users

def init_configs():
    print_step("初始化基础配置...")
    # 场景
    scenarios = ['汽车内饰', '新能源电池包', '消费电子', '医疗器械', '光伏储能', '高铁航空', '智能家居', '工业连接器']
    scenario_objs = [ApplicationScenario.objects.get_or_create(name=name)[0] for name in scenarios]

    # 材料类型
    mat_types = ['PA66', 'PC', 'ABS', 'PBT', 'POM', 'PP', 'PEI', 'PPS', 'PC/ABS', 'LCP', 'PEEK']
    type_objs = [MaterialType.objects.get_or_create(name=name)[0] for name in mat_types]

    # 测试配置 (依赖 init_configs.py 运行结果)
    test_configs = list(TestConfig.objects.all())
    
    # 【修复】如果数据库为空，尝试自动调用 init_configs.py 的逻辑，或者提示用户
    if not test_configs:
        print("⚠️ 检测到测试配置为空，正在尝试自动初始化...")
        try:
            # 尝试导入并运行 init_configs.py 中的 run 函数
            # 注意：这里假设 init_configs.py 在同一目录下
            import init_configs
            init_configs.run()
            test_configs = list(TestConfig.objects.all())
        except ImportError:
            print("❌ 无法自动初始化，请手动运行 'python init_configs.py'")
            return [], [], []

    return scenario_objs, type_objs, test_configs

def create_business_data():
    print_step("生成商业数据 (CRM)...")
    customers = []
    for _ in range(NUM_CUSTOMERS):
        c = Customer(
            company_name=fake.company(),
            short_name=fake.company_suffix(),
            contact_name=fake.name(),
            phone=fake.phone_number(),
            email=fake.email(),
            address=fake.address()
        )
        customers.append(c)
    Customer.objects.bulk_create(customers, ignore_conflicts=True)
    
    oem_names = ['比亚迪', '特斯拉', '吉利', '奇瑞', '长城', '大众', '丰田', '本田', '蔚来', '理想', '小鹏', '小米', '华为', '宝马', '奔驰']
    # 补充更多 OEM 以满足数量要求
    oems = [OEM(name=name, short_name=name) for name in oem_names]
    for _ in range(NUM_OEMS - len(oem_names)):
        oems.append(OEM(name=fake.company(), short_name=fake.word()))
    OEM.objects.bulk_create(oems, ignore_conflicts=True)
    
    sales = [Salesperson(name=fake.name(), phone=fake.phone_number(), email=fake.email()) for _ in range(NUM_SALES)]
    Salesperson.objects.bulk_create(sales, ignore_conflicts=True)
    
    return list(Customer.objects.all()), list(OEM.objects.all()), list(Salesperson.objects.all())

def create_raw_materials(test_configs):
    print_step(f"生成原材料库 ({NUM_RAW_MATERIALS} 条)...")
    
    # 1. 供应商
    suppliers = []
    for _ in range(NUM_SUPPLIERS):
        suppliers.append(Supplier(
            name=fake.company(),
            sales_contact=fake.name(),
            sales_phone=fake.phone_number(),
            tech_contact=fake.name(),
            tech_phone=fake.phone_number(),
            description=fake.sentence()
        ))
    Supplier.objects.bulk_create(suppliers, ignore_conflicts=True)
    all_suppliers = list(Supplier.objects.all())

    # 2. 原材料类型
    raw_types_data = [
        ('树脂', 'RESIN', 1), ('填料', 'FILLER', 2), ('阻燃剂', 'FR', 3), 
        ('增韧剂', 'IM', 4), ('助剂', 'ADD', 5), ('色粉', 'COLOR', 6)
    ]
    raw_types = []
    for name, code, order in raw_types_data:
        obj, _ = RawMaterialType.objects.get_or_create(name=name, defaults={'code': code, 'order': order})
        raw_types.append(obj)

    # 3. 原材料
    raw_materials = []
    for _ in range(NUM_RAW_MATERIALS):
        rtype = random.choice(raw_types)
        name_prefix = {
            '树脂': ['PA66', 'PA6', 'PC', 'PBT', 'PP', 'ABS'],
            '填料': ['玻纤', '矿粉', '滑石粉', '碳纤'],
            '阻燃剂': ['溴系', '磷系', '氮系'],
            '增韧剂': ['POE', 'EPDM'],
            '助剂': ['抗氧剂', '润滑剂', '偶联剂'],
            '色粉': ['黑种', '白种', '蓝种']
        }.get(rtype.name, ['通用原料'])
        
        # 【修复】增加随机性，防止唯一性冲突
        name = f"{random.choice(name_prefix)}-{random.randint(100, 9999)}-{uuid.uuid4().hex[:4]}"
        
        raw_materials.append(RawMaterial(
            name=name,
            model_name=f"{fake.word().upper()}{random.randint(1000, 9999)}",
            warehouse_code=f"W{random.randint(10000, 99999)}",
            category=rtype,
            supplier=random.choice(all_suppliers),
            cost_price=random.uniform(10, 200),
            purchase_date=timezone.now().date() - timedelta(days=random.randint(0, 365))
        ))
    
    # 【修复】使用 ignore_conflicts=True
    RawMaterial.objects.bulk_create(raw_materials, batch_size=BATCH_SIZE, ignore_conflicts=True)
    all_raw_materials = list(RawMaterial.objects.all())

    # 4. 原材料性能
    props = []
    for rm in all_raw_materials:
        for tc in random.sample(test_configs, k=random.randint(3, 8)):
            base_date = rm.purchase_date if rm.purchase_date else timezone.now().date()
            props.append(RawMaterialProperty(
                raw_material=rm,
                test_config=tc,
                value=round(random.uniform(1, 100), 2),
                test_date=base_date + timedelta(days=random.randint(1, 30))
            ))
    RawMaterialProperty.objects.bulk_create(props, batch_size=5000, ignore_conflicts=True)
    
    return all_raw_materials

def create_process_data(mat_types):
    print_step("生成工艺库数据...")
    
    pt_extrusion, _ = ProcessType.objects.get_or_create(name="双螺杆挤出")
    pt_injection, _ = ProcessType.objects.get_or_create(name="注塑成型")
    pt_extrusion.material_types.set(mat_types)

    machines = []
    brands = ['Coperion', 'KraussMaffei', 'Toshiba', 'Jwell', 'Keya']
    for i in range(NUM_MACHINES):
        machines.append(MachineModel(
            brand=random.choice(brands),
            model_name=f"ZSK-{26 + i*10}",
            screw_diameter=26 + i*10,
            ld_ratio=random.choice([40, 44, 48, 52]),
            max_speed=random.choice([600, 900, 1200])
        ))
    MachineModel.objects.bulk_create(machines, ignore_conflicts=True)
    all_machines = list(MachineModel.objects.all())
    
    for m in all_machines:
        m.suitable_materials.set(random.sample(mat_types, k=random.randint(2, 5)))

    screws = []
    for i in range(NUM_SCREWS):
        screws.append(ScrewCombination(
            name=f"组合-{fake.word()}-{i}",
            description="输送-熔融-剪切-排气-建压"
        ))
    ScrewCombination.objects.bulk_create(screws, ignore_conflicts=True)
    all_screws = list(ScrewCombination.objects.all())
    
    for s in all_screws:
        s.machines.set(random.sample(all_machines, k=random.randint(1, 3)))
        s.suitable_materials.set(random.sample(mat_types, k=random.randint(2, 5)))

    profiles = []
    for i in range(NUM_PROFILES):
        machine = random.choice(all_machines)
        screw = ScrewCombination.objects.filter(machines=machine).first()
        
        profiles.append(ProcessProfile(
            name=f"工艺-{fake.word()}-{i}",
            process_type=pt_extrusion,
            machine=machine,
            screw_combination=screw,
            temp_zone_1=random.randint(20, 50),
            temp_zone_2=random.randint(150, 200),
            temp_zone_3=random.randint(200, 260),
            temp_head=random.randint(240, 280),
            screw_speed=random.randint(300, 800),
            torque=random.uniform(60, 85),
            throughput=random.uniform(100, 500),
            cooling_method='WATER_STRAND',
            water_bath_length=random.uniform(2, 5)
        ))
    ProcessProfile.objects.bulk_create(profiles, batch_size=BATCH_SIZE)
    return list(ProcessProfile.objects.all())

def create_formulas(users, raw_materials, profiles, test_configs, mat_types):
    print_step(f"生成配方数据 ({NUM_FORMULAS} 条)...")
    
    formulas = []
    boms = []
    results = []
    
    raw_map = {}
    for rm in raw_materials:
        t_name = rm.category.name
        if t_name not in raw_map: raw_map[t_name] = []
        raw_map[t_name].append(rm)
        
    config_map = {}
    for tc in test_configs:
        key = tc.name.split(' ')[0]
        if key not in config_map: config_map[key] = []
        config_map[key].append(tc)

    for i in range(NUM_FORMULAS):
        creator = random.choice(users)
        m_type = random.choice(mat_types)
        process = random.choice(profiles)
        
        f = LabFormula(
            name=f"{m_type.name}改性配方-{uuid.uuid4().hex[:4]}",
            material_type=m_type,
            process=process,
            creator=creator,
            description=fake.sentence(),
            created_at=timezone.now() - timedelta(days=random.randint(0, 365))
        )
        today_str = f.created_at.strftime('%Y%m%d')
        f.code = f"L{today_str}-{i+1:03d}"
        formulas.append(f)
    
    LabFormula.objects.bulk_create(formulas, batch_size=BATCH_SIZE)
    all_formulas = list(LabFormula.objects.all())

    for f in all_formulas:
        # BOM
        if '树脂' in raw_map:
            resin = random.choice(raw_map['树脂'])
            boms.append(FormulaBOM(
                formula=f, raw_material=resin, percentage=random.uniform(40, 80),
                feeding_port='1_MAIN'
            ))
        
        if '填料' in raw_map and random.random() > 0.3:
            filler = random.choice(raw_map['填料'])
            boms.append(FormulaBOM(
                formula=f, raw_material=filler, percentage=random.uniform(10, 40),
                feeding_port='2_SIDE_1'
            ))
            
        if '助剂' in raw_map:
            add = random.choice(raw_map['助剂'])
            boms.append(FormulaBOM(
                formula=f, raw_material=add, percentage=random.uniform(0.5, 5),
                feeding_port='1_MAIN', is_pre_mix=True, pre_mix_time=120
            ))

        # Test Results
        for key, tcs in config_map.items():
            if random.random() > 0.7: continue
            
            for tc in tcs:
                val = random.uniform(10, 100)
                if '密度' in key: val = random.uniform(1.1, 1.6)
                elif '拉伸' in key: val = random.uniform(40, 180)
                
                results.append(FormulaTestResult(
                    formula=f,
                    test_config=tc,
                    value=round(val, 2),
                    test_date=f.created_at.date() + timedelta(days=random.randint(1, 7))
                ))

    FormulaBOM.objects.bulk_create(boms, batch_size=5000, ignore_conflicts=True)
    FormulaTestResult.objects.bulk_create(results, batch_size=5000, ignore_conflicts=True)
    
    print("   ... 计算配方成本")
    for f in all_formulas:
        f.calculate_cost()
        
    return all_formulas

def create_finished_materials(type_objs, scenario_objs, test_configs, formulas):
    print_step(f"生成成品材料库 ({NUM_MATERIALS} 条)...")
    
    materials = []
    manufacturers = ['BASF', 'Covestro', 'Dupont', 'Sabic', 'LG Chem', 'Toray']
    
    for i in range(NUM_MATERIALS):
        cat = random.choice(type_objs)
        grade = f"{cat.name}-{fake.word().upper()}{random.randint(100, 999)}-{uuid.uuid4().hex[:4]}"
        
        mat = MaterialLibrary(
            grade_name=grade,
            manufacturer=random.choice(manufacturers),
            category=cat,
            flammability=random.choice(['HB', 'V-0', 'V-2', '5VB']),
            description=fake.sentence(),
            created_at=timezone.now() - timedelta(days=random.randint(0, 365))
        )
        materials.append(mat)
    
    MaterialLibrary.objects.bulk_create(materials, batch_size=BATCH_SIZE)
    all_mats = list(MaterialLibrary.objects.all().order_by('-id')[:NUM_MATERIALS])

    # 关联场景 & 性能数据 & 配方
    m2m_rels = []
    data_points = []
    mat_files = []
    ThroughModel = MaterialLibrary.scenarios.through

    for mat in all_mats:
        for s in random.sample(scenario_objs, k=random.randint(1, 3)):
            m2m_rels.append(ThroughModel(materiallibrary_id=mat.id, applicationscenario_id=s.id))
        
        # 关联配方 (模拟从配方量产)
        if formulas:
            mat.formulas.set(random.sample(formulas, k=random.randint(0, 2)))

        for tc in random.sample(test_configs, k=min(len(test_configs), 10)):
            val = random.uniform(10, 100)
            data_points.append(MaterialDataPoint(
                material=mat, test_config=tc, value=round(val, 2)
            ))
            
        if random.random() < 0.3:
            mat_files.append(MaterialFile(
                material=mat, file_type='TDS', description="TDS Report", file="uploads/sample.pdf"
            ))

    MaterialDataPoint.objects.bulk_create(data_points, batch_size=5000, ignore_conflicts=True)
    ThroughModel.objects.bulk_create(m2m_rels, batch_size=5000, ignore_conflicts=True)
    MaterialFile.objects.bulk_create(mat_files, batch_size=5000)
    
    return all_mats

def create_projects(users, customers, oems, sales, materials):
    print_step(f"生成项目数据 ({NUM_PROJECTS} 条)...")
    
    projects_batch = []
    nodes_batch = []
    repos_batch = []
    files_batch = []
    
    stage_codes = [s[0] for s in ProjectStage.choices]
    
    for _ in range(NUM_PROJECTS):
        manager = random.choice(users)
        create_dt = timezone.now() - timedelta(days=random.randint(10, 365))
        
        rand_status = random.random()
        is_terminated = False
        if rand_status < 0.1:
            is_terminated = True
            target_stage_idx = random.randint(0, len(stage_codes) - 2)
            current_stage = stage_codes[target_stage_idx]
        elif rand_status > 0.9:
            target_stage_idx = len(stage_codes) - 1
            current_stage = stage_codes[target_stage_idx]
        else:
            target_stage_idx = random.randint(0, len(stage_codes) - 1)
            current_stage = stage_codes[target_stage_idx]

        p = Project(
            name=f"{fake.word()}项目-{uuid.uuid4().hex[:6]}",
            manager=manager,
            description=fake.sentence(),
            created_at=create_dt,
            current_stage=current_stage,
            is_terminated=is_terminated,
            progress_percent=0,
            latest_remark=""
        )
        projects_batch.append(p)

    Project.objects.bulk_create(projects_batch, batch_size=BATCH_SIZE)
    new_projects = Project.objects.order_by('-id')[:NUM_PROJECTS]
    
    for p in new_projects:
        try:
            target_stage_idx = stage_codes.index(p.current_stage)
        except ValueError:
            target_stage_idx = 0
            
        is_terminated = p.is_terminated
        
        for i, code in enumerate(stage_codes):
            status = 'PENDING'
            remark = ""
            
            if i < target_stage_idx:
                status = 'DONE'
                if random.random() < 0.3:
                    remark = get_random_remark(code, 'DONE')
            elif i == target_stage_idx:
                if is_terminated:
                    status = 'TERMINATED'
                else:
                    status = 'DOING'
                    if random.random() < 0.1: status = 'FAILED'
                
                remark = get_random_remark(code, status)
                p.latest_remark = remark
            else:
                status = 'PENDING'
            
            nodes_batch.append(ProjectNode(
                project=p, stage=code, order=i + 1, round=1,
                status=status, remark=remark,
                updated_at=p.created_at + timedelta(days=i*5)
            ))
            
        repos_batch.append(ProjectRepository(
            project=p,
            customer=random.choice(customers),
            oem=random.choice(oems),
            salesperson=random.choice(sales),
            material=random.choice(materials),
            product_name=f"{fake.word()}部件",
            product_code=f"P-{random.randint(1000,9999)}",
            target_cost=random.uniform(20, 100),
            competitor_price=random.uniform(25, 120)
        ))

    ProjectNode.objects.bulk_create(nodes_batch, batch_size=5000)
    Project.objects.bulk_update(new_projects, ['progress_percent', 'latest_remark'], batch_size=BATCH_SIZE)
    ProjectRepository.objects.bulk_create(repos_batch, batch_size=BATCH_SIZE)
    
    recent_repos = ProjectRepository.objects.order_by('-id')[:100]
    for repo in recent_repos:
        files_batch.append(ProjectFile(
            repository=repo, file_type='DRAWING_2D', description="初始图纸", file="uploads/drawing.pdf"
        ))
    ProjectFile.objects.bulk_create(files_batch)

def run():
    print("🚀 开始生成全量压力测试数据...")
    
    from app_repository.models import MaterialType, TestConfig
    mat_types = list(MaterialType.objects.all())
    test_configs = list(TestConfig.objects.all())
    
    if not mat_types or not test_configs:
        print("⚠️ 警告：未找到测试配置，请先运行 init_configs.py！")
        # 简单兜底
        cat, _ = MetricCategory.objects.get_or_create(name='物理性能')
        tc, _ = TestConfig.objects.get_or_create(category=cat, name='密度', standard='ISO 1183', unit='g/cm³')
        test_configs = [tc]

    with transaction.atomic():
        # 【新增】清空旧数据
        clean_data()
        
        users = init_users()
        scenario_objs, type_objs, test_configs = init_configs()
        customers, oems, sales = create_business_data()
        
        raw_materials = create_raw_materials(test_configs)
        profiles = create_process_data(type_objs)
        formulas = create_formulas(users, raw_materials, profiles, test_configs, type_objs)
        
        materials = create_finished_materials(type_objs, scenario_objs, test_configs, formulas)
        create_projects(users, customers, oems, sales, materials)
    
    print("\n✅ 所有数据生成完毕！")

if __name__ == '__main__':
    run()