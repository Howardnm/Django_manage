"""
共享工具模块：FakeContext、Faker 配置、常量、辅助函数

每个 app 脚本通过 `from ._base import ...` 引用此模块中的工具。
"""

import random
import datetime
from decimal import Decimal
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# 配置常量
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
COUNT_NOTIFICATIONS = 30
COUNT_PRODUCTION_ORDERS = 8
COUNT_MOLD_TYPES = 6

# ---------------------------------------------------------------------------
# Faker 初始化
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
    """从列表中随机取一个元素"""
    return random.choice(items) if items else None


def pick(items, k=1):
    """从列表中随机取 k 个不重复元素"""
    if not items:
        return []
    return random.sample(items, min(k, len(items)))


def rand_decimal(min_v=0, max_v=100, precision=2):
    """生成随机 Decimal"""
    return Decimal(f"{random.uniform(min_v, max_v):.{precision}f}")


def rand_date(days_back=365):
    """生成随机日期（过去 days_back 天内）"""
    return datetime.date.today() - datetime.timedelta(days=random.randint(0, days_back))


# ---------------------------------------------------------------------------
# FakeContext — 跨脚本共享上下文
# ---------------------------------------------------------------------------
@dataclass
class FakeContext:
    """
    承载所有脚本间共享的数据。

    每个 app 脚本通过 ctx.<field> 读取上游脚本产出的数据，
    并将自己创建的数据写回 ctx。
    """

    # === 预置种子数据 (Initialize.sh 已导入，只读) ===
    material_types: list = field(default_factory=list)       # MaterialType
    test_configs: list = field(default_factory=list)          # TestConfig
    scenarios: list = field(default_factory=list)             # ApplicationScenario
    metric_categories: list = field(default_factory=list)     # MetricCategory
    raw_material_types: list = field(default_factory=list)    # RawMaterialType
    suppliers: list = field(default_factory=list)             # Supplier
    raw_materials: list = field(default_factory=list)         # RawMaterial
    oem_list: list = field(default_factory=list)              # OEM

    # === 用户与组织 ===
    depts: dict = field(default_factory=dict)                 # {code: Department}
    admin: object = None                                      # User
    rnd_users: list = field(default_factory=list)
    proc_users: list = field(default_factory=list)
    sales_users: list = field(default_factory=list)
    purch_users: list = field(default_factory=list)
    all_internal: list = field(default_factory=list)

    # === 业务基础数据 ===
    characteristics: list = field(default_factory=list)       # MaterialCharacteristic
    grades: list = field(default_factory=list)                # GradeFactor
    customers: list = field(default_factory=list)             # Customer

    # === 材料库 ===
    materials: list = field(default_factory=list)             # MaterialLibrary

    # === 工艺数据 ===
    machines: list = field(default_factory=list)              # MachineModel
    screw_combinations: list = field(default_factory=list)    # ScrewCombination
    process_profiles: list = field(default_factory=list)      # ProcessProfile

    # === 工作流 ===
    workflow_defs: list = field(default_factory=list)         # WorkflowDefinition

    # === 项目 ===
    projects: list = field(default_factory=list)              # Project
    research_projects: list = field(default_factory=list)     # ResearchProject

    # === 配方 ===
    formulas: list = field(default_factory=list)              # LabFormula

    # === 表单 ===
    form_templates: list = field(default_factory=list)        # FormTemplate

    # === 试生产（新增） ===
    production_orders: list = field(default_factory=list)     # ProductionOrder
    mold_types: list = field(default_factory=list)            # MoldType
    injection_orders: list = field(default_factory=list)      # InjectionTask
    testing_orders: list = field(default_factory=list)        # TestingTask

    @classmethod
    def load_seed_data(cls):
        """
        从数据库读取 Initialize.sh 通过 management commands 预置的基础数据。
        返回 ctx 实例，种子数据字段已填充。
        """
        from app_material.models.material import (
            MaterialType, TestConfig, ApplicationScenario, MetricCategory,
        )
        from app_raw_material.models import RawMaterialType, Supplier, RawMaterial
        from app_repository.models import OEM

        ctx = cls()
        ctx.material_types = list(MaterialType.objects.all())
        ctx.test_configs = list(TestConfig.objects.all())
        ctx.scenarios = list(ApplicationScenario.objects.all())
        ctx.metric_categories = list(MetricCategory.objects.all())
        ctx.raw_material_types = list(RawMaterialType.objects.all())
        ctx.suppliers = list(Supplier.objects.all())
        ctx.raw_materials = list(RawMaterial.objects.all())
        ctx.oem_list = list(OEM.objects.all())

        print(f"  Seed data: material_types={len(ctx.material_types)}, "
              f"test_configs={len(ctx.test_configs)}, "
              f"scenarios={len(ctx.scenarios)}, "
              f"metric_categories={len(ctx.metric_categories)}")
        print(f"  Seed data: raw_material_types={len(ctx.raw_material_types)}, "
              f"suppliers={len(ctx.suppliers)}, "
              f"raw_materials={len(ctx.raw_materials)}, "
              f"OEMs={len(ctx.oem_list)}")

        return ctx


# ---------------------------------------------------------------------------
# Summary 打印
# ---------------------------------------------------------------------------
def print_summary(ctx: FakeContext) -> None:
    """打印所有已生成数据的统计汇总"""
    from app_user.models import Department
    from django.contrib.auth import get_user_model
    from app_repository.models import Customer
    from app_material.models.material import MaterialCharacteristic, MaterialLibrary, MaterialDataPoint
    from app_raw_material.models import RawMaterialProperty
    from app_process.models import MachineModel, ScrewCombination, ProcessProfile
    from app_workflow.models import WorkflowDefinition, WorkflowInstance, WorkflowTask, ApprovalHistory
    from app_project.models import Project, ProjectNode
    from app_basic_research.models import ResearchProject
    from app_formula.models import LabFormula, FormulaBOM, FormulaTestResult
    from app_form_management.models import FormTemplate, FormSubmission
    from app_notification.models import Notification
    from app_trial_production.models import (
        ProductionOrder, ProductionOrderFormulaDetail, ExtrusionTask, SampleInventory,
    )
    from app_mold_injection.models import MoldType, InjectionTask, MoldRequirement, MoldRequirementFormulaDetail
    from app_color_center.models import ColorMatchingTask
    from app_material_testing.models import TestingTask, TrialTestResult

    User = get_user_model()

    print("\n" + "=" * 60)
    print("  Fake Data Summary")
    print("=" * 60)
    stats = [
        ("Department", Department.objects.count()),
        ("User", User.objects.count()),
        ("Customer", Customer.objects.count()),
        ("MaterialCharacteristic", MaterialCharacteristic.objects.count()),
        ("GradeFactor", ctx.grades and len(ctx.grades) or 0),
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
        ("MoldType", MoldType.objects.count()),
        ("MoldRequirement", MoldRequirement.objects.count()),
        ("MoldReqFormulaDetail", MoldRequirementFormulaDetail.objects.count()),
        ("ProductionOrder", ProductionOrder.objects.count()),
        ("POFormulaDetail", ProductionOrderFormulaDetail.objects.count()),
        ("ExtrusionTask", ExtrusionTask.objects.count()),
        ("ColorMatchingTask", ColorMatchingTask.objects.count()),
        ("InjectionTask", InjectionTask.objects.count()),
        ("SampleInventory", SampleInventory.objects.count()),
        ("TestingTask", TestingTask.objects.count()),
        ("TrialTestResult", TrialTestResult.objects.count()),
        ("FormTemplate", FormTemplate.objects.count()),
        ("FormSubmission", FormSubmission.objects.count()),
        ("Notification", Notification.objects.count()),
        ("WorkflowInstance", WorkflowInstance.objects.count()),
        ("WorkflowTask", WorkflowTask.objects.count()),
        ("ApprovalHistory", ApprovalHistory.objects.count()),
    ]
    for label, count in stats:
        print(f"  {label:<25} {count}")
    print("=" * 60)
    print("  Done!")
