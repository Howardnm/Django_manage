import os
import sys
import django
import random
import datetime
import uuid
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
# 1. 基础配置
# ==========================================
COUNT_RND = 6           # 研发
COUNT_PROCESS = 4       # 工艺
COUNT_SALES = 4         # 销售
COUNT_PURCH = 2         # 采购
COUNT_EXTERNAL_CUST = 5 # 外部客户账号
COUNT_EXTERNAL_OEM = 3  # 外部主机厂账号

COUNT_CUST_ENTITIES = 10 # 客户公司数
COUNT_OEM_ENTITIES = 5   # 主机厂公司数

try:
    from faker import Faker
    fake = Faker('zh_CN')
except ImportError:
    class SimpleFaker:
        def name(self): return f"测试员_{random.randint(100, 999)}"
        def company(self): return f"公司_{random.randint(1000, 9999)}_{uuid.uuid4().hex[:4]}"
        def email(self): return f"test_{uuid.uuid4().hex[:6]}@example.com"
        def phone_number(self): return f"138{random.randint(10000000, 99999999)}"
    fake = SimpleFaker()

from app_user.models import Department
from app_repository.models import OEM, Customer, ProjectRepository
from app_material.models.material import (
    MaterialType, MetricCategory, TestConfig, MaterialLibrary, MaterialDataPoint
)
from app_project.models import Project, ProjectStage
from app_formula.models import LabFormula

# ==========================================
# 2. 辅助创建方法
# ==========================================

def create_depts():
    data = [("研发中心", "RND"), ("工艺工程部", "PROCESS"), ("销售部", "SALES"), ("供应链中心", "PURCH")]
    return {code: Department.objects.get_or_create(name=name, defaults={'code': code})[0] for name, code in data}

def create_user(username, role, dept=None, level=1, customer=None, oem=None):
    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            'user_type': role,
            'department': dept,
            'user_level': level,
            'associated_customer': customer,
            'associated_oem': oem,
            'first_name': fake.name(),
            'email': fake.email() if hasattr(fake, 'email') else f"{username}@example.com",
            'phone': fake.phone_number(),
            'is_staff': True if role not in ['CUSTOMER', 'OEM'] else False
        }
    )
    if created:
        user.set_password('Sunwill@123')
        user.save()
    else:
        # 如果已存在，则更新关联信息，方便重复测试
        user.user_type = role
        user.department = dept
        user.associated_customer = customer
        user.associated_oem = oem
        user.save()
    return user

# ==========================================
# 3. 核心执行逻辑
# ==========================================
@transaction.atomic
def run():
    print(f"🚀 开始重构全量 4D 画像测试数据 (幂等性修复版)...")

    # 1. 部门准备
    depts = create_depts()

    # 2. 公司实体准备
    print("   -> 正在建立/更新公司档案...")
    cust_entities = []
    for _ in range(COUNT_CUST_ENTITIES):
        c_name = f"{fake.company()}_{random.randint(100, 999)}"
        cust, _ = Customer.objects.get_or_create(
            company_name=c_name,
            defaults={'short_name': c_name[:4]}
        )
        cust_entities.append(cust)

    oem_entities = []
    for _ in range(COUNT_OEM_ENTITIES):
        o_name = f"OEM-{fake.company()[:4]}-{random.randint(100, 999)}"
        oem, _ = OEM.objects.get_or_create(
            name=o_name,
            defaults={'short_name': o_name[:4]}
        )
        oem_entities.append(oem)

    # 3. 账号准备 (分角色)
    print("   -> 正在分发全角色账号...")
    rnd_users = [create_user(f"rnd_{i}", 'ENGINEER', depts['RND'], random.randint(1, 15)) for i in range(COUNT_RND)]
    proc_users = [create_user(f"proc_{i}", 'PROCESS_ENGINEER', depts['PROCESS'], random.randint(5, 12)) for i in range(COUNT_PROCESS)]
    sales_users = [create_user(f"sales_{i}", 'SALES', depts['SALES'], random.randint(1, 10)) for i in range(COUNT_SALES)]
    purch_users = [create_user(f"purch_{i}", 'PURCHASING', depts['PURCH'], random.randint(1, 10)) for i in range(COUNT_PURCH)]
    
    # 外部账号 (绑定公司)
    for i in range(COUNT_EXTERNAL_CUST):
        create_user(f"cust_user_{i}", 'CUSTOMER', customer=random.choice(cust_entities))
    for i in range(COUNT_EXTERNAL_OEM):
        create_user(f"oem_user_{i}", 'OEM', oem=random.choice(oem_entities))

    # 4. 业务数据 (项目、配方)
    print("   -> 正在模拟业务链数据...")
    material_types = list(MaterialType.objects.all())
    if not material_types:
        print("   [!] 警告: 缺少基础分类，请先运行初始化配置脚本。")
        return

    # 项目与协同
    stages = [s[0] for s in ProjectStage.choices if s[0] != 'TERMINATED']
    for i in range(15):
        # 随机生成一个项目
        p_name = f"{random.choice(['华为', '美的', '比亚迪', '吉利'])} {fake.name()} 选型项目_{random.randint(100,999)}"
        p = Project.objects.create(
            name=p_name,
            manager=random.choice(rnd_users),
            current_stage=random.choice(stages)
        )
        # 指派工艺协同 (测试权限穿透)
        p.members.create(user=random.choice(proc_users), role='PROCESS')
        
        # 绑定档案 (signals 已自动创建 Repo，此处仅更新关联)
        repo = p.repository
        repo.customer = random.choice(cust_entities)
        repo.oem = random.choice(oem_entities)
        repo.salesperson = random.choice(sales_users)
        repo.save()

    # 配方 (研发部私有)
    for i in range(10):
        LabFormula.objects.create(
            name=f"实验样料-EXP{random.randint(1000, 9999)}",
            material_type=random.choice(material_types),
            creator=random.choice(rnd_users)
        )

    print(f"\n✅ 4D 测试环境重建成功！")
    print(f"   - 内部账号密码统一: Sunwill@123")
    print(f"   - 企业架构: 建立了独立的【公司】与【人】关联模型")

if __name__ == '__main__':
    run()
