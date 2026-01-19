import os
import sys
import django
import random
import uuid
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from faker import Faker

# ================= 配置区域 =================
# 请将 'Django_manage.settings' 替换为你实际的 settings 路径
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Django_manage.settings')
django.setup()

from django.contrib.auth.models import User
from app_project.models import Project, ProjectNode, ProjectStage
from app_repository.models import (
    MaterialType, ApplicationScenario, MaterialLibrary,
    Customer, OEM, Salesperson, ProjectRepository,
    MetricCategory, TestConfig, MaterialDataPoint,
    MaterialFile, ProjectFile
)

# 参数设置
NUM_USERS = 5
NUM_CUSTOMERS = 50
NUM_OEMS = 20
NUM_SALES = 10
NUM_MATERIALS = 500
NUM_PROJECTS = 500
BATCH_SIZE = 500

fake = Faker('zh_CN')

def print_step(msg):
    print(f"🔹 {msg}")

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
    # 随机返回一个，或者返回默认
    return random.choice(remarks.get(stage_code, ["进行中...", "阶段推进中"]))

def init_users():
    print_step("初始化用户 (Users)...")
    users = []
    # 创建管理员
    admin, _ = User.objects.get_or_create(username='admin', defaults={'is_staff': True, 'is_superuser': True})
    if _:
        admin.set_password('admin123')
        admin.save()
    users.append(admin)

    # 创建普通项目经理
    for i in range(1, NUM_USERS + 1):
        u, created = User.objects.get_or_create(username=f'manager{i}')
        if created:
            u.set_password('123456')
            u.save()
            # 信号会自动创建 UserProfile，我们更新它
            if hasattr(u, 'profile'):
                u.profile.department = "研发部"
                u.profile.phone = fake.phone_number()
                u.profile.save()
        users.append(u)
    return users

def init_configs():
    print_step("初始化基础配置 (Configs)...")
    
    # 1. 场景
    scenarios = ['汽车内饰', '新能源电池包', '消费电子', '医疗器械', '光伏储能', '高铁航空', '智能家居', '工业连接器']
    scenario_objs = [ApplicationScenario.objects.get_or_create(name=name)[0] for name in scenarios]

    # 2. 材料类型
    mat_types = ['PA66', 'PC', 'ABS', 'PBT', 'POM', 'PP', 'PEI', 'PPS', 'PC/ABS', 'LCP', 'PEEK']
    type_objs = [MaterialType.objects.get_or_create(name=name)[0] for name in mat_types]

    # 3. 指标分类 & 测试配置
    # 注意：这里不再手动创建，而是依赖 init_configs.py 已经初始化的数据
    # 我们只负责查询出来用
    test_configs = list(TestConfig.objects.all())
    
    if not test_configs:
        print("⚠️ 警告：未找到测试配置，请先运行 init_configs.py！")
        # 简单兜底，防止报错
        cat, _ = MetricCategory.objects.get_or_create(name='物理性能')
        tc, _ = TestConfig.objects.get_or_create(category=cat, name='密度', standard='ISO 1183', unit='g/cm³')
        test_configs = [tc]

    return scenario_objs, type_objs, test_configs

def create_business_data():
    print_step("生成商业数据 (CRM)...")
    
    # 客户
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
    all_customers = list(Customer.objects.all())

    # OEM
    oem_names = ['比亚迪', '特斯拉', '吉利', '奇瑞', '长城', '大众', '丰田', '本田', '蔚来', '理想', '小鹏', '小米', '华为', '宝马', '奔驰']
    oems = [OEM(name=name, short_name=name) for name in oem_names]
    OEM.objects.bulk_create(oems, ignore_conflicts=True)
    all_oems = list(OEM.objects.all())

    # 业务员
    sales = [Salesperson(name=fake.name(), phone=fake.phone_number(), email=fake.email()) for _ in range(NUM_SALES)]
    Salesperson.objects.bulk_create(sales, ignore_conflicts=True)
    all_sales = list(Salesperson.objects.all())

    return all_customers, all_oems, all_sales

def create_materials(type_objs, scenario_objs, test_configs):
    print_step(f"生成材料库 ({NUM_MATERIALS} 条)...")
    
    materials = []
    manufacturers = ['BASF', 'Covestro', 'Dupont', 'Sabic', 'LG Chem', 'Toray', 'Asahi', 'Kingfa', 'Wanhua']
    
    for _ in range(NUM_MATERIALS):
        cat = random.choice(type_objs)
        grade = f"{cat.name}-{fake.word().upper()}{random.randint(100, 999)}"
        # 唯一性处理
        grade = f"{grade}-{uuid.uuid4().hex[:4]}"
        
        mat = MaterialLibrary(
            grade_name=grade,
            manufacturer=random.choice(manufacturers),
            category=cat,
            flammability=random.choice(['HB', 'V-0', 'V-2', '5VB', '5VA']),
            description=fake.sentence(nb_words=15),
            created_at=timezone.now() - timedelta(days=random.randint(0, 700))
        )
        materials.append(mat)
    
    MaterialLibrary.objects.bulk_create(materials, batch_size=BATCH_SIZE)
    all_mats = list(MaterialLibrary.objects.all().order_by('-id')[:NUM_MATERIALS])

    # 关联场景 & 性能数据 & 附件
    m2m_rels = []
    data_points = []
    mat_files = []
    ThroughModel = MaterialLibrary.scenarios.through

    # 预处理 test_configs，按名称分类，方便查找
    # 格式: {'密度': [tc_iso, tc_astm], '拉伸强度': [...]}
    config_map = {}
    for tc in test_configs:
        # 简化名称匹配，去掉括号等
        key = tc.name.split(' ')[0] 
        if key not in config_map:
            config_map[key] = []
        config_map[key].append(tc)

    # 核心指标列表 (确保这些指标大概率被录入)
    core_metrics = ['密度', '熔融指数', '拉伸强度', '弯曲模量', 'Izod', '热变形温度', '阻燃等级']

    for mat in all_mats:
        # 1. 场景
        for s in random.sample(scenario_objs, k=random.randint(1, 3)):
            m2m_rels.append(ThroughModel(materiallibrary_id=mat.id, applicationscenario_id=s.id))
        
        # 2. 性能数据
        # 策略：遍历核心指标，随机决定录入 ISO、ASTM 或两者
        # 另外再随机录入一些非核心指标
        
        # 确定该材料的“市场偏好” (0: ISO为主, 1: ASTM为主, 2: 混合)
        market_pref = random.choice([0, 1, 2]) 

        for key, tcs in config_map.items():
            # 核心指标 80% 概率录入，非核心 30%
            is_core = any(k in key for k in core_metrics)
            if not is_core and random.random() > 0.3:
                continue
            if is_core and random.random() > 0.9: # 偶尔缺失核心数据
                continue

            # 筛选符合偏好的标准
            selected_tcs = []
            iso_tcs = [t for t in tcs if 'ISO' in t.standard]
            astm_tcs = [t for t in tcs if 'ASTM' in t.standard]
            other_tcs = [t for t in tcs if 'ISO' not in t.standard and 'ASTM' not in t.standard]

            if market_pref == 0 and iso_tcs:
                selected_tcs.extend(iso_tcs)
            elif market_pref == 1 and astm_tcs:
                selected_tcs.extend(astm_tcs)
            else:
                # 混合模式，或者该指标只有一种标准
                selected_tcs.extend(iso_tcs)
                selected_tcs.extend(astm_tcs)
            
            selected_tcs.extend(other_tcs) # 其他标准(如UL, IEC)总是录入

            # 生成数据
            for tc in selected_tcs:
                val = 0.0
                remark = ""
                
                # 根据指标名生成合理范围的随机值
                if '密度' in tc.name or '比重' in tc.name:
                    val = random.uniform(1.05, 1.65)
                elif '熔融' in tc.name:
                    val = random.uniform(5.0, 80.0)
                elif '收缩' in tc.name:
                    val = random.uniform(0.2, 1.8)
                elif '吸水' in tc.name:
                    val = random.uniform(0.1, 1.5)
                elif '灰分' in tc.name:
                    val = random.uniform(10, 50)
                
                elif '拉伸强度' in tc.name:
                    val = random.uniform(40.0, 200.0)
                elif '断裂伸长率' in tc.name:
                    val = random.uniform(2.0, 150.0)
                elif '拉伸模量' in tc.name:
                    val = random.uniform(2000, 15000)
                elif '弯曲强度' in tc.name:
                    val = random.uniform(60, 280)
                elif '弯曲模量' in tc.name:
                    val = random.uniform(2000, 12000)
                elif '冲击' in tc.name:
                    if 'kJ' in tc.unit: # ISO
                        val = random.uniform(3.0, 80.0)
                    else: # ASTM J/m
                        val = random.uniform(30, 800)
                elif '硬度' in tc.name:
                    val = random.uniform(50, 120)

                elif '热变形' in tc.name or 'HDT' in tc.name:
                    val = random.uniform(80, 280)
                elif '维卡' in tc.name:
                    val = random.uniform(90, 290)
                elif '熔点' in tc.name:
                    val = random.uniform(220, 340)
                elif '膨胀' in tc.name: # CLTE
                    val = random.uniform(2, 8)
                elif 'RTI' in tc.name:
                    val = random.uniform(80, 150)

                elif '阻燃' in tc.name:
                    # 阻燃等级通常是文本，但 value 字段是 float
                    # 这里我们假设 value 存 0，remark 存等级
                    val = 0
                    remark = random.choice(['HB', 'V-2', 'V-0', '5VB'])
                elif '灼热丝' in tc.name: # GWIT/GWFI
                    val = random.choice([650, 750, 850, 960])
                elif 'CTI' in tc.name:
                    val = random.choice([175, 250, 400, 600])
                elif '电阻' in tc.name:
                    val = random.uniform(10, 16) # 指数
                    remark = "10^" + str(int(val))
                elif '介电' in tc.name:
                    val = random.uniform(15, 30)
                
                elif '老化' in tc.name or '耐候' in tc.name:
                    val = random.uniform(70, 95) # 保持率
                elif 'VOC' in tc.name:
                    val = random.uniform(10, 100)
                elif '气味' in tc.name:
                    val = random.uniform(2.5, 4.0)

                # 写入数据
                data_points.append(MaterialDataPoint(
                    material=mat,
                    test_config=tc,
                    value=round(val, 2),
                    remark=remark
                ))
            
        # 附件 (模拟)
        if random.random() < 0.3:
            mat_files.append(MaterialFile(
                material=mat,
                file_type=random.choice(['UL', 'TDS', 'COC']),
                description=f"{mat.grade_name} 相关文件",
                file="uploads/sample.pdf" # 假路径
            ))

    MaterialDataPoint.objects.bulk_create(data_points, batch_size=5000)
    ThroughModel.objects.bulk_create(m2m_rels, batch_size=5000, ignore_conflicts=True)
    MaterialFile.objects.bulk_create(mat_files, batch_size=5000)

    return all_mats

def create_projects(users, customers, oems, sales, materials):
    print_step(f"生成项目数据 ({NUM_PROJECTS} 条)...")
    
    projects_batch = []
    nodes_batch = []
    repos_batch = []
    files_batch = []
    
    stage_codes = [s[0] for s in ProjectStage.choices] # ['INIT', 'COLLECT', ...]
    
    # 批量生成
    for _ in range(NUM_PROJECTS):
        manager = random.choice(users)
        create_dt = timezone.now() - timedelta(days=random.randint(10, 365))
        
        # 随机决定项目状态
        # 80% 正常进行，10% 终止，10% 完成
        rand_status = random.random()
        is_terminated = False
        
        if rand_status < 0.1:
            # 终止
            is_terminated = True
            target_stage_idx = random.randint(0, len(stage_codes) - 2) # 不会在最后阶段终止
            current_stage = stage_codes[target_stage_idx]
        elif rand_status > 0.9:
            # 完成 (所有阶段走完)
            target_stage_idx = len(stage_codes) - 1 # FEEDBACK or ORDER
            current_stage = stage_codes[target_stage_idx]
            is_terminated = False
        else:
            # 进行中
            target_stage_idx = random.randint(0, len(stage_codes) - 1)
            current_stage = stage_codes[target_stage_idx]
            is_terminated = False

        # 创建项目对象
        p = Project(
            name=f"{fake.word()}项目-{uuid.uuid4().hex[:6]}",
            manager=manager,
            description=fake.sentence(),
            created_at=create_dt,
            current_stage=current_stage,
            is_terminated=is_terminated,
            progress_percent=0, # 稍后计算
            latest_remark="" # 稍后计算
        )
        projects_batch.append(p)

    # 1. 批量写入 Project
    Project.objects.bulk_create(projects_batch, batch_size=BATCH_SIZE)
    
    # 2. 重新查询以获取 ID
    new_projects = Project.objects.order_by('-id')[:NUM_PROJECTS]
    
    for p in new_projects:
        # 重新推导逻辑
        try:
            target_stage_idx = stage_codes.index(p.current_stage)
        except ValueError:
            target_stage_idx = 0
            
        is_terminated = p.is_terminated
        
        # 生成节点
        done_count = 0
        total_valid_nodes = 9 # 假设标准9个阶段
        
        for i, code in enumerate(stage_codes):
            status = 'PENDING'
            remark = ""
            
            if i < target_stage_idx:
                status = 'DONE'
                done_count += 1
                # 历史节点也随机生成一点备注
                if random.random() < 0.3:
                    remark = get_random_remark(code, 'DONE')
            elif i == target_stage_idx:
                # 当前节点
                if is_terminated:
                    status = 'TERMINATED'
                else:
                    status = 'DOING'
                    # 偶尔有些是 FAILED
                    if random.random() < 0.1:
                        status = 'FAILED'
                
                # 【核心修改】生成当前节点的备注，并同步给 Project
                remark = get_random_remark(code, status)
                p.latest_remark = remark
                
            else:
                status = 'PENDING'
            
            nodes_batch.append(ProjectNode(
                project=p,
                stage=code,
                order=i + 1,
                round=1,
                status=status,
                remark=remark,
                updated_at=p.created_at + timedelta(days=i*5)
            ))
            
        # 更新进度百分比 (简单估算)
        percent = int((done_count / total_valid_nodes) * 100)
        p.progress_percent = percent
        
        # 生成档案
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

    # 写入节点
    ProjectNode.objects.bulk_create(nodes_batch, batch_size=5000)
    
    # 【核心修改】更新 Project 的 progress_percent 和 latest_remark
    Project.objects.bulk_update(new_projects, ['progress_percent', 'latest_remark'], batch_size=BATCH_SIZE)
    
    # 写入档案
    ProjectRepository.objects.bulk_create(repos_batch, batch_size=BATCH_SIZE)
    
    # 写入项目文件 (需要先查出 Repo ID)
    # 考虑到性能，这里可以简化：只给前 100 个项目生成文件
    recent_repos = ProjectRepository.objects.order_by('-id')[:100]
    for repo in recent_repos:
        files_batch.append(ProjectFile(
            repository=repo,
            file_type='DRAWING_2D',
            description="初始图纸",
            file="uploads/drawing.pdf"
        ))
    ProjectFile.objects.bulk_create(files_batch)

    return

def run():
    print("🚀 开始重新设计的数据生成脚本...")
    with transaction.atomic():
        # 1. 用户
        users = init_users()
        # 2. 配置
        scenario_objs, type_objs, test_configs = init_configs()
        # 3. 商业
        customers, oems, sales = create_business_data()
        # 4. 材料
        materials = create_materials(type_objs, scenario_objs, test_configs)
        # 5. 项目
        create_projects(users, customers, oems, sales, materials)
    
    print("\n✅ 所有数据生成完毕！")

if __name__ == '__main__':
    run()