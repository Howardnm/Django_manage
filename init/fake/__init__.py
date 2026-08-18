"""
伪数据生成编排器

按依赖顺序调用各 app 模块的伪数据脚本。
每个脚本通过 FakeContext 共享上游产出数据。

用法:
    from init.fake import run_all
    run_all()
"""

from ._base import FakeContext, print_summary


def run_all():
    print("=" * 60)
    print("  Fake Data Generator (refactored)")
    print("=" * 60)

    # 0. 加载预置种子数据
    ctx = FakeContext.load_seed_data()

    # 按依赖顺序执行各 app 脚本
    from .app_user import run as run_app_user
    from .app_repository import run as run_app_repository
    from .app_material import run as run_app_material
    from .app_raw_material import run as run_app_raw_material
    from .app_process import run as run_app_process
    from .app_workflow import run as run_app_workflow
    from .app_project import run as run_app_project
    from .app_basic_research import run as run_app_basic_research
    from .app_formula import run as run_app_formula
    from .app_trial_production import run as run_app_trial_production
    from .app_mold_injection import run as run_app_mold_injection
    from .app_color_center import run as run_app_color_center
    from .app_material_testing import run as run_app_material_testing
    from .app_form_management import run as run_app_form_management
    from .app_notification import run as run_app_notification

    run_app_user(ctx)              # 1. 用户与部门
    run_app_repository(ctx)        # 2. 客户与等级因子
    run_app_material(ctx)          # 3. 材料库
    run_app_raw_material(ctx)      # 4. 原材料属性
    run_app_process(ctx)           # 5. 工艺数据
    run_app_workflow(ctx)          # 6. 工作流定义
    run_app_project(ctx)           # 7. 商业项目
    run_app_basic_research(ctx)    # 8. 预研项目
    run_app_formula(ctx)           # 9. 配方 + BOM + 色粉配比 + 颜色字段

    # 按工序流水线依赖顺序
    run_app_trial_production(ctx)  # 10. 排产工单 + 挤出任务 + 颗粒样品
    run_app_mold_injection(ctx)    # 11. 模具台账 + 注塑任务 + 样条样品
    run_app_color_center(ctx)      # 12. 配色任务
    run_app_material_testing(ctx)  # 13. 测试任务 + 测试结果

    run_app_form_management(ctx)   # 14. 表单模板与提交
    run_app_notification(ctx)      # 15. 通知 + 审批实例

    print_summary(ctx)
