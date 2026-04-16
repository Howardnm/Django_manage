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
# 配置生成数量
# ==========================================
COUNT_SALESPERSON = 5
COUNT_CUSTOMER = 10
COUNT_MATERIAL = 30 # 增加一些材料
COUNT_SUPPLIER = 5
COUNT_RAW_MATERIAL = 30
COUNT_MACHINE = 5
COUNT_SCREW = 10
COUNT_PROFILE = 10
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

from django.contrib.auth.models import User
from app_repository.models import OEM, Salesperson, Customer, ProjectRepository
from app_material.models.material import MaterialType, ApplicationScenario, MetricCategory, TestConfig, MaterialLibrary, MaterialDataPoint, MaterialCharacteristic
from app_project.models import Project, ProjectNode, ProjectStage
from app_raw_material.models import RawMaterialType, Supplier, RawMaterial, RawMaterialProperty
from app_process.models import MachineModel, ScrewCombination, ProcessProfile
from app_formula.models import LabFormula, FormulaBOM, FormulaTestResult

def create_test_configs():
    cat_phys, _ = MetricCategory.objects.get_or_create(name="物理性能", defaults={'order': 10})
    cat_mech, _ = MetricCategory.objects.get_or_create(name="机械性能", defaults={'order': 20})
    configs_iso = [
        (cat_phys, "密度", "ISO 1183", "23℃", "g/cm³"),
        (cat_phys, "熔融指数", "ISO 1133", "230℃/2.16kg", "g/10min"),
        (cat_mech, "拉伸强度", "ISO 527", "50mm/min", "MPa"),
        (cat_mech, "弯曲模量", "ISO 178", "2mm/min", "MPa"),
    ]
    created = []
    for cat, name, std, cond, unit in configs_iso:
        obj, _ = TestConfig.objects.get_or_create(name=name, standard=std, defaults={'category': cat, 'condition': cond, 'unit': unit})
        created.append(obj)
    return created

def run():
    print(f"🚀 开始生成支持分布式账号与镜像体系的伪数据...")
    
    # 确保有管理员
    admin_user = User.objects.filter(is_superuser=True).first()
    if not admin_user:
        admin_user = User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
    
    test_configs = create_test_configs()
    material_types = list(MaterialType.objects.all())
    scenarios = list(ApplicationScenario.objects.all())
    characteristics = list(MaterialCharacteristic.objects.all())
    raw_types = list(RawMaterialType.objects.all())

    # 1. 生成业务员 (关联 Staff 账号)
    print("   -> 生成业务员账号...")
    salespersons = []
    for i in range(COUNT_SALESPERSON):
        u_name = f"staff_test_{i}"
        user, _ = User.objects.get_or_create(
            username=u_name,
            defaults={'email': fake.email(), 'is_staff': True, 'first_name': fake.name()}
        )
        user.set_password('Sunwill@123')
        user.save()
        
        sp, _ = Salesperson.objects.get_or_create(
            user=user,
            defaults={'name': user.first_name, 'phone': fake.phone_number(), 'email': user.email}
        )
        salespersons.append(sp)

    # 2. 生成客户 (由信号自动触发 User 创建)
    print("   -> 生成客户镜像账号...")
    customers = []
    for _ in range(COUNT_CUSTOMER):
        c_name = fake.company()
        cust, created = Customer.objects.get_or_create(
            company_name=c_name,
            defaults={'short_name': c_name[:4], 'email': fake.email(), 'is_active': True}
        )
        customers.append(cust)

    # 3. 生成材料库 (包含发布状态)
    print("   -> 生成物料档案并同步...")
    materials = []
    for i in range(COUNT_MATERIAL):
        mt = random.choice(material_types)
        # 随机设置 70% 的材料为对外发布
        is_pub = random.random() < 0.7
        
        mat = MaterialLibrary.objects.create(
            grade_name=f"{mt.name}-SF{random.randint(100,999)}",
            manufacturer=fake.company(),
            category=mt,
            is_published=is_pub,
            description=fake.text(max_nb_chars=200)
        )
        mat.scenarios.set(random.sample(scenarios, k=min(2, len(scenarios))))
        if characteristics:
            mat.characteristics.set(random.sample(characteristics, k=min(3, len(characteristics))))
            
        for tc in test_configs:
            MaterialDataPoint.objects.create(
                material=mat, 
                test_config=tc, 
                value=Decimal(random.uniform(1, 50)).quantize(Decimal("0.01"))
            )
        materials.append(mat)

    # 4. 生成原材料与供应
    suppliers = [Supplier.objects.create(name=fake.company()) for _ in range(COUNT_SUPPLIER)]
    raw_materials = []
    for _ in range(COUNT_RAW_MATERIAL):
        rt = random.choice(raw_types)
        rm = RawMaterial.objects.create(name=f"RM-{rt.code}-{random.randint(100,999)}", category=rt, supplier=random.choice(suppliers), cost_price=Decimal(random.uniform(5, 20)))
        raw_materials.append(rm)

    # 5. 生成项目
    print("   -> 关联项目档案...")
    for i in range(COUNT_PROJECT):
        proj = Project.objects.create(name=f"选型项目-{fake.name()}", manager=random.choice(User.objects.filter(is_staff=True)), current_stage=ProjectStage.RND)
        repo = proj.repository # 信号自动创建的
        repo.customer = random.choice(customers)
        repo.material = random.choice(materials)
        repo.salesperson = random.choice(salespersons)
        repo.save()

    # 6. 生成配方
    print("   -> 生成实验配方...")
    for i in range(COUNT_FORMULA):
        formula = LabFormula.objects.create(name=f"配方-{i}", material_type=random.choice(material_types), process=None, creator=admin_user)
        for raw in random.sample(raw_materials, k=3):
            FormulaBOM.objects.create(formula=formula, raw_material=raw, percentage=Decimal(random.randint(5, 30)))
        for tc in random.sample(test_configs, k=2):
            FormulaTestResult.objects.create(formula=formula, test_config=tc, value=Decimal(random.uniform(1, 100)))

    print(f"\n✅ 数据生成完成！")
    print(f"   - 业务员登录密码统一为: Sunwill@123")
    print(f"   - 客户账号请在后台查看，默认密码格式为: Sunwill@ID")

if __name__ == '__main__':
    run()
