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
COUNT_MATERIAL = 20
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
from app_material.models.material import MaterialType, ApplicationScenario, MetricCategory, TestConfig, MaterialLibrary, MaterialDataPoint
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
    print(f"🚀 开始生成纯净版伪数据...")
    users = list(User.objects.all()) or [User.objects.create_superuser('admin', 'admin@example.com', 'admin123')]
    test_configs = create_test_configs()
    material_types = list(MaterialType.objects.all())
    scenarios = list(ApplicationScenario.objects.all())
    raw_types = list(RawMaterialType.objects.all())

    # 1. 生成业务员和客户
    salespersons = [Salesperson.objects.create(name=fake.name()) for _ in range(COUNT_SALESPERSON)]
    customers = [Customer.objects.create(company_name=fake.company()) for _ in range(COUNT_CUSTOMER)]

    # 2. 生成材料库
    materials = []
    for _ in range(COUNT_MATERIAL):
        mt = random.choice(material_types)
        mat = MaterialLibrary.objects.create(
            grade_name=f"{mt.name}-G{random.randint(10,50)}",
            manufacturer=fake.company(),
            category=mt,
            description=fake.sentence()
        )
        mat.scenarios.set(random.sample(scenarios, k=min(2, len(scenarios))))
        for tc in test_configs:
            MaterialDataPoint.objects.create(material=mat, test_config=tc, value=Decimal(random.uniform(1, 50)).quantize(Decimal("0.01")))
        materials.append(mat)

    # 3. 生成原材料与供应
    suppliers = [Supplier.objects.create(name=fake.company()) for _ in range(COUNT_SUPPLIER)]
    raw_materials = []
    for _ in range(COUNT_RAW_MATERIAL):
        rt = random.choice(raw_types)
        rm = RawMaterial.objects.create(name=f"RM-{rt.code}-{random.randint(100,999)}", category=rt, supplier=random.choice(suppliers), cost_price=Decimal(random.uniform(5, 20)))
        raw_materials.append(rm)

    # 4. 生成工艺
    machines = [MachineModel.objects.create(brand="Coperion", model_name=f"EXT-{random.randint(26,90)}") for _ in range(COUNT_MACHINE)]
    screws = [ScrewCombination.objects.create(name=f"SC-{i}") for i in range(COUNT_SCREW)]
    profiles = [ProcessProfile.objects.create(name=f"PP-{i}", machine=random.choice(machines), screw_combination=random.choice(screws)) for i in range(COUNT_PROFILE)]

    # 5. 生成项目
    for i in range(COUNT_PROJECT):
        proj = Project.objects.create(name=f"研发项目-{i}", manager=random.choice(users), current_stage=ProjectStage.RND)
        repo, _ = ProjectRepository.objects.get_or_create(project=proj)
        repo.customer = random.choice(customers)
        repo.material = random.choice(materials)
        repo.save()

    # 6. 生成配方
    for i in range(COUNT_FORMULA):
        formula = LabFormula.objects.create(name=f"配方-{i}", material_type=random.choice(material_types), process=random.choice(profiles), creator=random.choice(users))
        for raw in random.sample(raw_materials, k=3):
            FormulaBOM.objects.create(formula=formula, raw_material=raw, percentage=Decimal(random.randint(5, 30)))
        for tc in random.sample(test_configs, k=2):
            FormulaTestResult.objects.create(formula=formula, test_config=tc, value=Decimal(random.uniform(1, 100)))

    print(f"✅ 数据生成完成！")

if __name__ == '__main__':
    run()
