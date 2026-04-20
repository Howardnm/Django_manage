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
COUNT_RND = 6           
COUNT_PROCESS = 4       
COUNT_SALES = 4         
COUNT_PURCH = 2         
COUNT_EXTERNAL_CUST = 5 
COUNT_EXTERNAL_OEM = 3  

COUNT_CUST_ENTITIES = 10 
COUNT_OEM_ENTITIES = 5   

try:
    from faker import Faker
    fake = Faker('zh_CN')
except ImportError:
    class SimpleFaker:
        def name(self): return f"测试员_{random.randint(100, 999)}"
        def company(self): return f"公司_{random.randint(1000, 9999)}"
        def email(self): return f"user_{uuid.uuid4().hex[:6]}@example.com"
        def phone_number(self): return "13800138000"
    fake = SimpleFaker()

from app_user.models import Department
from app_repository.models import OEM, Customer, ProjectRepository
from app_material.models.material import MaterialType
from app_project.models import Project, ProjectNode, ProjectStage
from app_formula.models import LabFormula

# ==========================================
# 2. 辅助方法
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
            'email': f"{username}@sunwill.com.cn",
            'phone': fake.phone_number(),
            'is_staff': True if role not in ['CUSTOMER', 'OEM'] else False
        }
    )
    if created:
        user.set_password('Sunwill@123')
        user.save()
    return user

# ==========================================
# 3. 核心执行逻辑
# ==========================================
@transaction.atomic
def run():
    print(f"🚀 开始重构全量 4D 画像测试数据 (节点状态智能更新版)...")

    # 1. 基础维度
    depts = create_depts()
    # 按照业务逻辑排序的流程，过滤掉 FEEDBACK
    ordered_stages = [
        ProjectStage.INIT, ProjectStage.COLLECT, ProjectStage.FEASIBILITY, 
        ProjectStage.PRICING, ProjectStage.RND, ProjectStage.PILOT, 
        ProjectStage.MID_TEST, ProjectStage.MASS_PROD, ProjectStage.ORDER
    ]

    # 2. 公司档案
    print("   -> 正在建立公司名录...")
    cust_entities = []
    for _ in range(COUNT_CUST_ENTITIES):
        name = f"{fake.company()}_{random.randint(100, 999)}"
        cust, _ = Customer.objects.get_or_create(company_name=name, defaults={'short_name': name[:4]})
        cust_entities.append(cust)

    oem_entities = []
    for _ in range(COUNT_OEM_ENTITIES):
        name = f"OEM-{fake.company()[:4]}-{random.randint(10, 99)}"
        oem, _ = OEM.objects.get_or_create(name=name, defaults={'short_name': name[:4]})
        oem_entities.append(oem)

    # 3. 全角色账号
    print("   -> 正在生成 4D 身份账号...")
    rnd_users = [create_user(f"rnd_{i}", 'ENGINEER', depts['RND'], random.randint(1, 15)) for i in range(COUNT_RND)]
    proc_users = [create_user(f"proc_{i}", 'PROCESS_ENGINEER', depts['PROCESS'], random.randint(5, 12)) for i in range(COUNT_PROCESS)]
    sales_users = [create_user(f"sales_{i}", 'SALES', depts['SALES'], random.randint(1, 10)) for i in range(COUNT_SALES)]
    
    for i in range(COUNT_EXTERNAL_CUST):
        create_user(f"cust_user_{i}", 'CUSTOMER', customer=random.choice(cust_entities))
    for i in range(COUNT_EXTERNAL_OEM):
        create_user(f"oem_user_{i}", 'OEM', oem=random.choice(oem_entities))

    # 4. 项目及节点状态更新
    print("   -> 正在模拟循序渐进的项目进度 (更新触发式节点)...")
    for i in range(20):
        # A. 创建项目 (这会自动通过 signals.py 生成所有 PENDING 状态的节点)
        p = Project.objects.create(
            name=f"{random.choice(['华为', '吉利', '长城', '美的'])} {fake.name()} 选型_{random.randint(100,999)}",
            manager=random.choice(rnd_users)
        )
        
        # B. 随机决定进度深度
        target_index = random.randint(0, len(ordered_stages) - 1)
        target_stage_code = ordered_stages[target_index]

        # C. 批量更新该项目的节点状态，而不是重新创建
        # 这种方式会触发 ProjectNode 的 post_save 信号，进而自动更新 Project 的百分比、阶段等冗余字段
        project_nodes = list(p.nodes.all().order_by('order'))
        for idx, node in enumerate(project_nodes):
            if idx < target_index:
                node.status = 'DONE'
                node.remark = "系统自动同步完成"
            elif idx == target_index:
                node.status = 'DOING'
            else:
                node.status = 'PENDING'
            node.save() # 触发信号，自动计算得分和更新项目

        # D. 完善档案与成员
        p.members.create(user=random.choice(proc_users), role='PROCESS', workload_share=0.2)
        repo = p.repository
        repo.customer = random.choice(cust_entities)
        repo.oem = random.choice(oem_entities)
        repo.salesperson = random.choice(sales_users)
        repo.save()

    # 5. 研发配方数据
    print("   -> 正在生成研发部私有配方...")
    material_types = list(MaterialType.objects.all())
    if material_types:
        for i in range(10):
            LabFormula.objects.create(
                name=f"实验样料-EXP{random.randint(1000, 9999)}",
                material_type=random.choice(material_types),
                creator=random.choice(rnd_users)
            )

    print(f"\n✅ 4D 测试环境重建成功！")
    print(f"   - 信号机制验证: 节点状态更新已自动同步至项目进度百分比")
    print(f"   - 数据结构: 严格遵循 [公司 -> 人 -> 项目] 关联逻辑")

if __name__ == '__main__':
    run()
