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

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

User = get_user_model()

# ==========================================
# 配置生成数量
# ==========================================
COUNT_ENGINEER = 5
COUNT_SALESPERSON = 5
COUNT_CUSTOMER_ENTITIES = 10
COUNT_OEM_ENTITIES = 5
COUNT_MATERIAL = 40  # 20 ISO, 20 ASTM
COUNT_SUPPLIER = 5
COUNT_RAW_MATERIAL = 30
COUNT_PROJECT = 20
COUNT_FORMULA = 30

try:
    from faker import Faker
    fake = Faker('zh_CN')
except ImportError:
    class SimpleFaker:
        def name(self): return f"测试人员_{random.randint(1000, 9999)}"
        def company(self): return f"测试公司_{random.randint(1000, 9999)}"
        def address(self): return f"测试地址_{random.randint(1000, 9999)}"
        def phone_number(self): return f"138{random.randint(10000000, 99999999)}"
        def email(self): return f"test_{random.randint(1000, 9999)}@example.com"
        def sentence(self): return "这是一个测试句子。"
        def text(self): return "这是一段测试文本内容。"
        def date_between(self, start_date='-1y', end_date='today'): return datetime.date.today()
    fake = SimpleFaker()

from app_repository.models import OEM, Customer, ProjectRepository
from app_material.models.material import (
    MaterialType, ApplicationScenario, MetricCategory, TestConfig, 
    MaterialLibrary, MaterialDataPoint, MaterialCharacteristic
)
from app_project.models import Project, ProjectNode, ProjectStage
from app_raw_material.models import RawMaterialType, Supplier, RawMaterial
from app_formula.models import LabFormula, FormulaBOM, FormulaTestResult

def create_test_configs():
    cat_phys, _ = MetricCategory.objects.get_or_create(name="物理性能", defaults={'order': 10})
    cat_mech, _ = MetricCategory.objects.get_or_create(name="机械性能", defaults={'order': 20})
    
    # ISO 标准
    configs_iso = [
        (cat_phys, "密度", "ISO 1183", "23℃", "g/cm³"),
        (cat_phys, "熔融指数", "ISO 1133", "230℃/2.16kg", "g/10min"),
        (cat_mech, "拉伸强度", "ISO 527", "50mm/min", "MPa"),
        (cat_mech, "弯曲模量", "ISO 178", "2mm/min", "MPa"),
    ]
    
    # ASTM 标准
    configs_astm = [
        (cat_phys, "密度", "ASTM D792", "23℃", "g/cm³"),
        (cat_phys, "熔融指数", "ASTM D1238", "230℃/2.16kg", "g/10min"),
        (cat_mech, "拉伸强度", "ASTM D638", "50mm/min", "MPa"),
        (cat_mech, "弯曲模量", "ASTM D790", "1.3mm/min", "MPa"),
    ]
    
    iso_objs = []
    for cat, name, std, cond, unit in configs_iso:
        obj, _ = TestConfig.objects.get_or_create(
            name=name, standard=std, 
            defaults={'category': cat, 'condition': cond, 'unit': unit}
        )
        iso_objs.append(obj)
        
    astm_objs = []
    for cat, name, std, cond, unit in configs_astm:
        obj, _ = TestConfig.objects.get_or_create(
            name=name, standard=std, 
            defaults={'category': cat, 'condition': cond, 'unit': unit}
        )
        astm_objs.append(obj)
        
    return iso_objs, astm_objs

@transaction.atomic
def run():
    print(f"🚀 开始生成基于自定义 User 模型的全量伪数据...")
    
    # 0. 确保超级管理员
    admin_user = User.objects.filter(is_superuser=True).first()
    if not admin_user:
        admin_user = User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
        admin_user.user_type = User.UserType.ADMIN
        admin_user.save()
    
    iso_configs, astm_configs = create_test_configs()
    material_types = list(MaterialType.objects.all())
    scenarios = list(ApplicationScenario.objects.all())
    raw_types = list(RawMaterialType.objects.all())

    if not material_types:
        print("❌ 错误: 数据库中没有 MaterialType，请先运行 init_configs 脚本。")
        return

    # 1. 生成内部人员
    print("   -> 生成内部员工账号...")
    engineers = []
    for i in range(COUNT_ENGINEER):
        u_name = f"engineer_{i}"
        user, _ = User.objects.get_or_create(
            username=u_name,
            defaults={
                'email': fake.email(), 'user_type': User.UserType.ENGINEER,
                'first_name': f"研发-{fake.name()}", 'company': "技术研发部",
                'phone': fake.phone_number(), 'job_title': "高级工程师",
                'is_staff': True
            }
        )
        user.set_password('Sunwill@123')
        user.save()
        engineers.append(user)

    salespersons = []
    for i in range(COUNT_SALESPERSON):
        u_name = f"sales_{i}"
        user, _ = User.objects.get_or_create(
            username=u_name,
            defaults={
                'email': fake.email(), 'user_type': User.UserType.SALES,
                'first_name': f"销售-{fake.name()}", 'company': "华南销售部",
                'phone': fake.phone_number(), 'job_title': "大客户经理",
                'is_staff': True
            }
        )
        user.set_password('Sunwill@123')
        user.save()
        salespersons.append(user)

    # 2. 生成客户实体
    print("   -> 生成客户实体与关联账号...")
    customers = []
    for i in range(COUNT_CUSTOMER_ENTITIES):
        c_name = fake.company()
        cust, _ = Customer.objects.get_or_create(
            company_name=c_name,
            defaults={
                'short_name': c_name[:4], 'email': fake.email(), 
                'contact_name': fake.name(), 'phone': fake.phone_number()
            }
        )
        customers.append(cust)

    # 3. 生成 OEM 实体
    print("   -> 生成 OEM 实体与关联账号...")
    oems = []
    for i in range(COUNT_OEM_ENTITIES):
        o_name = f"OEM-{fake.company()[:4]}"
        oem, _ = OEM.objects.get_or_create(
            name=o_name,
            defaults={'short_name': o_name[:4], 'contact_name': fake.name()}
        )
        oems.append(oem)

    # 4. 生成材料库
    print("   -> 生成物料档案 (ISO/ASTM 区分)...")
    materials = []
    for i in range(COUNT_MATERIAL):
        mt = random.choice(material_types)
        is_iso = i < (COUNT_MATERIAL // 2)
        std_suffix = "ISO" if is_iso else "ASTM"
        configs = iso_configs if is_iso else astm_configs
        
        mat = MaterialLibrary.objects.create(
            grade_name=f"{mt.name}-{std_suffix}-SF{random.randint(100,999)}",
            manufacturer=fake.company(),
            category=mt,
            is_published=True,
            description=f"这是一个全 {std_suffix} 标准性能测试的材料牌号。"
        )
        mat.scenarios.set(random.sample(scenarios, k=min(2, len(scenarios))))
        
        for tc in configs:
            MaterialDataPoint.objects.create(
                material=mat, 
                test_config=tc, 
                value=Decimal(random.uniform(1, 100)).quantize(Decimal("0.001"))
            )
        materials.append(mat)

    # 5. 生成原材料
    suppliers = [Supplier.objects.create(name=fake.company()) for _ in range(COUNT_SUPPLIER)]
    raw_materials = []
    for _ in range(COUNT_RAW_MATERIAL):
        rt = random.choice(raw_types) if raw_types else None
        if not rt: continue
        rm = RawMaterial.objects.create(
            name=f"RM-{rt.code}-{random.randint(100,999)}", 
            category=rt, 
            supplier=random.choice(suppliers), 
            cost_price=Decimal(random.uniform(5, 50))
        )
        raw_materials.append(rm)

    # 6. 生成项目
    print("   -> 生成项目并模拟进度...")
    stages_list = [s[0] for s in ProjectStage.choices if s[0] != 'FEEDBACK']
    for i in range(COUNT_PROJECT):
        target_stage = random.choice(stages_list)
        # 信号自动创建 nodes 和 repository
        proj = Project.objects.create(
            name=f"{random.choice(['吉利','长城','华为','美的'])} - {fake.name()} 选型项目", 
            manager=random.choice(engineers),
            current_stage=target_stage
        )
        
        # 更新档案关联
        repo = proj.repository
        repo.customer = random.choice(customers)
        repo.oem = random.choice(oems)
        repo.salesperson = random.choice(salespersons)
        repo.material = random.choice(materials)
        repo.product_name = f"零部件-{random.randint(100,999)}"
        repo.save()
        
        # 根据随机分配的阶段，更新 nodes 状态
        target_index = stages_list.index(target_stage)
        for node in proj.nodes.all():
            if node.stage in stages_list:
                node_idx = stages_list.index(node.stage)
                if node_idx < target_index:
                    node.status = 'DONE'
                elif node_idx == target_index:
                    node.status = 'DOING'
                else:
                    node.status = 'PENDING'
                node.remark = f"自动更新为 {node.status} 状态。"
                node.save()
        
        # 此时 project 信号会根据 node.save() 自动重新计算百分比和 current_stage

    # 7. 生成配方
    print("   -> 生成实验配方...")
    for i in range(COUNT_FORMULA):
        formula = LabFormula.objects.create(
            name=f"研发配方-EXP{random.randint(1000,9999)}", 
            material_type=random.choice(material_types), 
            creator=random.choice(engineers)
        )
        if raw_materials:
            for raw in random.sample(raw_materials, k=min(len(raw_materials), 4)):
                FormulaBOM.objects.create(formula=formula, raw_material=raw, percentage=Decimal(random.randint(1, 50)))
        
        for tc in random.sample(iso_configs, k=min(len(iso_configs), 3)):
            FormulaTestResult.objects.create(formula=formula, test_config=tc, value=Decimal(random.uniform(1, 150)))

    print(f"\n✅ 数据生成完成！")

if __name__ == '__main__':
    run()
