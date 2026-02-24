import os
import sys
import django
import random
import datetime
from decimal import Decimal

# 初始化 Django 环境
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Django_manage.settings')
django.setup()

# ==========================================
# 配置生成数量 (可在此处调整)
# ==========================================
COUNT_SALESPERSON = 0      # 业务员数量
COUNT_CUSTOMER = 0         # 客户数量
COUNT_MATERIAL = 5         # 成品材料库数量
COUNT_SUPPLIER = 0         # 供应商数量
COUNT_RAW_MATERIAL = 0     # 原材料数量
COUNT_MACHINE = 0          # 机台型号数量
COUNT_SCREW = 0            # 螺杆组合数量
COUNT_PROFILE = 0          # 工艺方案数量
COUNT_PROJECT = 0          # 研发项目数量
COUNT_FORMULA = 0          # 实验配方数量

# 尝试导入 Faker，如果没有则使用简单的随机生成
try:
    from faker import Faker
    fake = Faker('zh_CN')
except ImportError:
    print("⚠️ 未检测到 faker 库，将使用内置随机生成器。建议安装: pip install faker")
    class SimpleFaker:
        def name(self): return f"测试人员_{random.randint(1000, 9999)}"
        def company(self): return f"测试公司_{random.randint(1000, 9999)}"
        def address(self): return f"测试地址_{random.randint(1000, 9999)}"
        def phone_number(self): return f"138{random.randint(10000000, 99999999)}"
        def email(self): return f"test_{random.randint(1000, 9999)}@example.com"
        def sentence(self): return "这是一个测试句子。"
        def text(self): return "这是一段测试文本内容。" * 5
        def date_between(self, start_date='-1y', end_date='today'): return datetime.date.today()
        def date_time_between(self, start_date='-1y', end_date='now'): return datetime.datetime.now()
    fake = SimpleFaker()

from django.contrib.auth.models import User
from django.utils import timezone

# App Models
from app_repository.models import (
    MaterialType, ApplicationScenario, OEM, Salesperson, 
    MetricCategory, TestConfig, MaterialLibrary, MaterialDataPoint, 
    Customer, ProjectRepository
)
from app_project.models import Project, ProjectNode, ProjectStage
from app_raw_material.models import RawMaterialType, Supplier, RawMaterial, RawMaterialProperty
from app_process.models import MachineModel, ScrewCombination, ProcessProfile
from app_formula.models import LabFormula, FormulaBOM, FormulaTestResult

def create_test_configs():
    """确保有基本的测试指标配置"""
    print("   ...检查测试指标配置")
    cat_phys, _ = MetricCategory.objects.get_or_create(name="物理性能", defaults={'order': 10})
    cat_mech, _ = MetricCategory.objects.get_or_create(name="机械性能", defaults={'order': 20})
    
    # ISO 标准配置
    configs_iso = [
        (cat_phys, "密度", "ISO 1183", "23℃", "g/cm³"),
        (cat_phys, "熔融指数 (MFR)", "ISO 1133", "230℃/2.16kg", "g/10min"),
        (cat_phys, "灰分", "ISO 3451", "600℃/30min", "%"),
        (cat_mech, "拉伸强度", "ISO 527", "50mm/min", "MPa"),
        (cat_mech, "断裂伸长率", "ISO 527", "50mm/min", "%"),
        (cat_mech, "弯曲强度", "ISO 178", "2mm/min", "MPa"),
        (cat_mech, "弯曲模量", "ISO 178", "2mm/min", "MPa"),
        (cat_mech, "悬臂梁缺口冲击", "ISO 180/1A", "23℃", "kJ/m²"),
    ]
    
    # ASTM 标准配置
    configs_astm = [
        (cat_phys, "比重", "ASTM D792", "23℃", ""),
        (cat_phys, "熔融指数 (MFR)", "ASTM D1238", "230℃/2.16kg", "g/10min"),
        (cat_phys, "灰分", "ASTM D5630", "600℃", "%"),
        (cat_mech, "拉伸强度", "ASTM D638", "50mm/min", "MPa"),
        (cat_mech, "断裂伸长率", "ASTM D638", "50mm/min", "%"),
        (cat_mech, "弯曲强度", "ASTM D790", "1.3mm/min", "MPa"),
        (cat_mech, "弯曲模量", "ASTM D790", "1.3mm/min", "MPa"),
        (cat_mech, "悬臂梁缺口冲击", "ASTM D256", "23℃", "J/m"),
    ]
    
    created_configs_iso = []
    for cat, name, std, cond, unit in configs_iso:
        # 修复 MultipleObjectsReturned 错误
        # 如果数据库里已经存在同名但不同标准的记录，或者同名同标准的记录有多个（脏数据），
        # get_or_create 可能会报错。
        # 这里我们更严谨地先 filter，如果存在则取第一个，不存在则创建。
        
        existing = TestConfig.objects.filter(name=name, standard=std).first()
        if existing:
            obj = existing
        else:
            obj = TestConfig.objects.create(
                name=name, 
                standard=std,
                category=cat, 
                condition=cond, 
                unit=unit
            )
        created_configs_iso.append(obj)
        
    created_configs_astm = []
    for cat, name, std, cond, unit in configs_astm:
        existing = TestConfig.objects.filter(name=name, standard=std).first()
        if existing:
            obj = existing
        else:
            obj = TestConfig.objects.create(
                name=name, 
                standard=std,
                category=cat, 
                condition=cond, 
                unit=unit
            )
        created_configs_astm.append(obj)
        
    return created_configs_iso, created_configs_astm

def run():
    print(f"🚀 开始生成伪数据...")
    
    # 0. 基础准备
    users = list(User.objects.all())
    if not users:
        print("⚠️ 没有用户，正在创建默认用户...")
        u = User.objects.create_user('test_admin', 'test@example.com', '123456')
        users = [u]
    
    # 确保基础配置存在
    test_configs_iso, test_configs_astm = create_test_configs()
    all_test_configs = test_configs_iso + test_configs_astm
    
    # 获取现有基础数据 (假设 init_*.py 已经运行)
    material_types = list(MaterialType.objects.all())
    scenarios = list(ApplicationScenario.objects.all())
    oems = list(OEM.objects.all())
    raw_types = list(RawMaterialType.objects.all())
    
    if not material_types:
        print("⚠️ 缺少材料类型，请先运行 init_materials_data.py")
        return
    if not raw_types:
        print("⚠️ 缺少原材料类型，请先运行 init_raw_materials_data.py")
        return

    # ==========================================
    # 1. app_repository (公共基础库)
    # ==========================================
    print("\n🔹 [1/5] 生成 app_repository 数据...")
    
    # Salesperson
    print(f"   ...生成业务员 ({COUNT_SALESPERSON} 条)")
    salespersons = list(Salesperson.objects.all())
    for _ in range(COUNT_SALESPERSON):
        sp, created = Salesperson.objects.get_or_create(
            name=fake.name(),
            defaults={
                'phone': fake.phone_number(),
                'email': fake.email()
            }
        )
        if created:
            salespersons.append(sp)
        
    # Customer
    print(f"   ...生成客户 ({COUNT_CUSTOMER} 条)")
    customers = list(Customer.objects.all())
    for _ in range(COUNT_CUSTOMER):
        company_name = fake.company()
        c, created = Customer.objects.get_or_create(
            company_name=company_name,
            defaults={
                'short_name': company_name[:4],
                'address': fake.address(),
                'contact_name': fake.name(),
                'phone': fake.phone_number(),
                'email': fake.email()
            }
        )
        if created:
            customers.append(c)

    # MaterialLibrary
    print(f"   ...生成材料库 ({COUNT_MATERIAL} 条)")
    materials = list(MaterialLibrary.objects.all())
    for i in range(COUNT_MATERIAL):
        mt = random.choice(material_types)
        grade = f"{mt.name}-{random.randint(100, 999)}G{random.randint(10, 50)}"
        mat, created = MaterialLibrary.objects.get_or_create(
            grade_name=grade,
            defaults={
                'manufacturer': fake.company(),
                'category': mt,
                'flammability': random.choice(['HB', 'V-2', 'V-0']),
                'description': fake.sentence()
            }
        )
        
        if created:
            # 关联场景
            if scenarios:
                mat.scenarios.set(random.sample(scenarios, k=random.randint(1, 3)))
            
            # 生成性能数据 - 随机选择 ISO 或 ASTM 体系
            use_iso = random.choice([True, False])
            selected_configs = test_configs_iso if use_iso else test_configs_astm
            
            for tc in selected_configs:
                val = Decimal(random.uniform(1, 100)).quantize(Decimal("0.001"))
                MaterialDataPoint.objects.create(
                    material=mat,
                    test_config=tc,
                    value=val
                )
            materials.append(mat)

    # ==========================================
    # 2. app_raw_material (原材料库)
    # ==========================================
    print("\n🔹 [2/5] 生成 app_raw_material 数据...")
    
    # Supplier
    print(f"   ...生成供应商 ({COUNT_SUPPLIER} 条)")
    suppliers = list(Supplier.objects.all())
    for _ in range(COUNT_SUPPLIER):
        # 使用 get_or_create 避免唯一性约束错误
        s, _ = Supplier.objects.get_or_create(
            name=fake.company(),
            defaults={
                'sales_contact': fake.name(),
                'sales_phone': fake.phone_number()
            }
        )
        s.product_categories.set(random.sample(raw_types, k=random.randint(1, 3)))
        suppliers.append(s)
        
    # RawMaterial
    print(f"   ...生成原材料 ({COUNT_RAW_MATERIAL} 条)")
    raw_materials = list(RawMaterial.objects.all())
    for i in range(COUNT_RAW_MATERIAL):
        rt = random.choice(raw_types)
        rm = RawMaterial.objects.create(
            name=f"{rt.code}_{random.randint(1000, 9999)}",
            model_name=f"M-{random.randint(100, 999)}",
            warehouse_code=f"WH-{random.randint(10000, 99999)}",
            category=rt,
            supplier=random.choice(suppliers) if suppliers else None,
            cost_price=Decimal(random.uniform(5, 50)).quantize(Decimal("0.01")),
            purchase_date=fake.date_between(start_date='-2y', end_date='today')
        )
        # 性能指标 - 原材料随机选几个指标即可
        for tc in random.sample(all_test_configs, k=3):
            RawMaterialProperty.objects.create(
                raw_material=rm,
                test_config=tc,
                value=Decimal(random.uniform(0.1, 10)).quantize(Decimal("0.001"))
            )
        raw_materials.append(rm)

    # ==========================================
    # 3. app_process (工艺库)
    # ==========================================
    print("\n🔹 [3/5] 生成 app_process 数据...")
    
    # MachineModel
    print(f"   ...生成机台型号 ({COUNT_MACHINE} 条)")
    machines = list(MachineModel.objects.all())
    brands = ['Coperion', 'KraussMaffei', 'Toshiba', 'Jwell', 'Keya']
    for i in range(COUNT_MACHINE):
        dia = random.choice([26, 35, 50, 75, 90])
        m = MachineModel.objects.create(
            brand=random.choice(brands),
            model_name=f"EXT-{dia}-{random.randint(1, 99)}",
            machine_code=f"{random.randint(1, 20)}",
            screw_diameter=dia,
            ld_ratio=random.choice([40, 44, 48, 52]),
            max_speed=random.choice([600, 900, 1200])
        )
        m.suitable_materials.set(random.sample(material_types, k=random.randint(1, 3)))
        machines.append(m)
        
    # ScrewCombination
    print(f"   ...生成螺杆组合 ({COUNT_SCREW} 条)")
    screws = list(ScrewCombination.objects.all())
    for i in range(COUNT_SCREW):
        if not machines:
             print("⚠️ 缺少机台型号，无法生成螺杆组合")
             break
        sc = ScrewCombination.objects.create(
            name=f"组合-{random.choice(['高剪切', '弱剪切', '高分散'])}-V{i}",
            description="输送-熔融-剪切-排气-建压"
        )
        sc.machines.set(random.sample(machines, k=random.randint(1, min(3, len(machines)))))
        sc.suitable_materials.set(random.sample(material_types, k=random.randint(1, 3)))
        screws.append(sc)
        
    # ProcessProfile
    print(f"   ...生成工艺方案 ({COUNT_PROFILE} 条)")
    profiles = list(ProcessProfile.objects.all())
    for i in range(COUNT_PROFILE):
        if not machines or not screws:
             print("⚠️ 缺少机台或螺杆，无法生成工艺方案")
             break
        pp = ProcessProfile.objects.create(
            name=f"工艺方案-{fake.date_between()}-{i}",
            process_type_name="双螺杆挤出",
            machine=random.choice(machines),
            screw_combination=random.choice(screws),
            temp_zone_1=random.randint(20, 50),
            temp_zone_2=random.randint(150, 200),
            temp_zone_3=random.randint(200, 250),
            temp_zone_4=random.randint(220, 260),
            temp_zone_5=random.randint(230, 270),
            temp_zone_6=random.randint(230, 270),
            temp_zone_7=random.randint(230, 270),
            temp_zone_8=random.randint(230, 270),
            temp_zone_9=random.randint(230, 270),
            temp_zone_10=random.randint(230, 270),
            temp_zone_11=random.randint(230, 270),
            temp_zone_12=random.randint(230, 270),
            temp_head=random.randint(240, 280),
            screw_speed=random.randint(300, 800),
            throughput=random.randint(50, 500),
            torque=random.randint(60, 90)
        )
        pp.material_types.set(random.sample(material_types, k=random.randint(1, 2)))
        profiles.append(pp)

    # ==========================================
    # 4. app_project (项目管理)
    # ==========================================
    print("\n🔹 [4/5] 生成 app_project 数据...")
    
    projects = []
    # 定义所有可能的阶段顺序
    ALL_STAGES = [
        ProjectStage.INIT,
        ProjectStage.COLLECT,
        ProjectStage.FEASIBILITY,
        ProjectStage.PRICING,
        ProjectStage.RND,
        ProjectStage.PILOT,
        ProjectStage.MID_TEST,
        ProjectStage.MASS_PROD,
        ProjectStage.ORDER
    ]
    
    for i in range(COUNT_PROJECT):
        # 随机决定这个项目进行到了哪个阶段
        # 比如：current_stage_index = 4，意味着项目进行到了 RND 阶段
        current_stage_index = random.randint(0, len(ALL_STAGES) - 1)
        current_stage_code = ALL_STAGES[current_stage_index]
        
        # 计算进度百分比 (简单估算)
        progress = int((current_stage_index / len(ALL_STAGES)) * 100)
        
        # Project
        # 注意：如果 Project 的 save() 方法或信号里已经自动创建了节点，
        # 那么这里 create 之后，数据库里应该已经有一套默认节点了。
        proj = Project.objects.create(
            name=f"研发项目-{fake.company()}-{i}",
            manager=random.choice(users),
            current_stage=current_stage_code,
            progress_percent=progress,
            description=fake.text()
        )
        projects.append(proj)
        
        # ProjectRepository (关联档案)
        repo, _ = ProjectRepository.objects.get_or_create(project=proj)
        if customers:
            repo.customer = random.choice(customers)
        if oems:
            repo.oem = random.choice(oems)
        if salespersons:
            repo.salesperson = random.choice(salespersons)
        if materials:
            repo.material = random.choice(materials)
        repo.product_name = f"部件-{random.randint(100, 999)}"
        repo.target_cost = Decimal(random.uniform(10, 30)).quantize(Decimal("0.01"))
        repo.save()
        
        # ProjectNode (更新标准流程节点)
        # 既然 Project 创建时已经自动生成了节点（假设是这样），
        # 那么我们应该查询出这些节点并更新它们的状态，而不是 create 新的。
        
        # 先尝试获取现有的节点
        existing_nodes = list(ProjectNode.objects.filter(project=proj).order_by('order'))
        
        # 如果没有自动生成节点（比如信号没触发），则手动创建（兼容性处理）
        if not existing_nodes:
            for idx, stage in enumerate(ALL_STAGES):
                ProjectNode.objects.create(
                    project=proj,
                    stage=stage,
                    order=idx + 1,
                    status='PENDING'
                )
            existing_nodes = list(ProjectNode.objects.filter(project=proj).order_by('order'))

        # 更新节点状态
        for idx, node in enumerate(existing_nodes):
            status = 'PENDING'
            if idx < current_stage_index:
                status = 'DONE'
            elif idx == current_stage_index:
                status = 'DOING'
            
            node.status = status
            if status != 'PENDING':
                node.remark = f"节点备注-{idx}"
            node.save()

    # ==========================================
    # 5. app_formula (配方数据库)
    # ==========================================
    print("\n🔹 [5/5] 生成 app_formula 数据...")
    
    for i in range(COUNT_FORMULA):
        if not profiles:
            print("⚠️ 缺少工艺方案，跳过配方生成")
            break
            
        # LabFormula
        # 注意：code 字段在 save() 时会自动生成，这里不需要手动指定
        formula = LabFormula.objects.create(
            name=f"实验配方-{fake.date_between()}-{i}",
            material_type=random.choice(material_types),
            process=random.choice(profiles),
            creator=random.choice(users),
            cost_predicted=Decimal(random.uniform(10, 20)).quantize(Decimal("0.01"))
        )
        
        # FormulaBOM
        if len(raw_materials) >= 1:
            k = random.randint(1, min(5, len(raw_materials)))
            used_raws = random.sample(raw_materials, k=k)
            for raw in used_raws:
                phr = random.randint(5, 50)
                FormulaBOM.objects.create(
                    formula=formula,
                    raw_material=raw,
                    percentage=phr
                )
            
        # FormulaTestResult
        for tc in random.sample(all_test_configs, k=4):
            FormulaTestResult.objects.create(
                formula=formula,
                test_config=tc,
                value=Decimal(random.uniform(1, 100)).quantize(Decimal("0.001")),
                test_date=datetime.date.today()
            )

    print(f"\n✅ 伪数据生成完成！")

if __name__ == '__main__':
    run()
