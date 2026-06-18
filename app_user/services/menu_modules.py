"""菜单模块定义。为每个业务区域提供静态菜单配置。

导出: MenuModule。
"""

from app_user.mixins import IdentityConfig

class MenuModule:
    """定义各业务模块的菜单项"""

    @staticmethod
    def get_dashboard():
        """返回看板工作台菜单定义。"""
        return {
            "name": "看板工作台",
            "icon": "ti-smart-home",
            "visible_to": IdentityConfig.INTERNAL_STAFF,
            "url_name": "panel_home",
            "sub_items": [
                {"name": "系统资源看板", "url_name": "panel_home"},
                {"name": "项目全景看板", "url_name": "project_overview"},
                {"name": "项目统计看板", "url_name": "project_statistics"},
                {"name": "客户行为分析", "url_name": "customer_activity_overview"},
                {"name": "成员绩效榜单", "url_name": "user_performance_list"},
            ]
        }

    @staticmethod
    def get_project():
        """返回项目管理中心菜单定义。"""
        return {
            "name": "项目管理中心",
            "icon": "ti-subtask",
            "visible_to": IdentityConfig.INTERNAL_STAFF,
            "url_name": "project_list",
            "sub_items": [
                {"name": "项目列表", "url_name": "project_list"},
                {"name": "成员绩效看板", "url_name": "project_performance_list"},
                {"name": "项目评分规则", "url_name": "project_score_rule_list"},
            ]
        }

    @staticmethod
    def get_form_management():
        """返回表单管理中心菜单定义。"""
        return {
            "name": "表单管理中心",
            "icon": "ti-forms",
            "visible_to": IdentityConfig.INTERNAL_STAFF,
            "url_name": "form_template_list",
            "sub_items": [
                {"name": "创建表单", "url_name": "form_create_wizard"},
                {"name": "我的表单草稿", "url_name": "my_drafts"},
                {"name": "我的表单提交", "url_name": "my_submissions"},
                {"name": "表单模板管理", "url_name": "form_template_list"},
            ]
        }

    @staticmethod
    def get_workflow():
        """返回流程审批中心菜单定义。"""
        return {
            "name": "流程审批中心",
            "icon": "ti-git-pull-request",
            "visible_to": IdentityConfig.INTERNAL_STAFF,
            "url_name": "workflow_my_tasks",
            "sub_items": [
                {"name": "我的待办任务", "url_name": "workflow_my_tasks"},
                {"name": "我的已办任务", "url_name": "workflow_completed_tasks"},
                {"name": "我发起的流程", "url_name": "workflow_initiated_list"},
                {"name": "流程定义管理", "url_name": "workflow_definition_list"},
            ]
        }

    @staticmethod
    def get_repository():
        """返回客户档案中心菜单定义。"""
        return {
            "name": "客户档案中心",
            "icon": "ti-archive",
            "visible_to": IdentityConfig.INTERNAL_STAFF,
            "url_name": "repo_customer_list",
            "sub_items": [
                {"name": "客户资料库", "url_name": "repo_customer_list"},
                {"name": "客户评分排行", "url_name": "repo_customer_ranking"},
                {"name": "主机厂(OEM)库", "url_name": "repo_oem_list"},
            ]
        }

    @staticmethod
    def get_basic_research():
        """返回基础预研中心菜单定义。"""
        return {
            "name": "基础预研中心",
            "icon": "ti-flask",
            "visible_to": IdentityConfig.RND_ONLY,
            "url_name": "basic_research_list",
            "sub_items": [
                {"name": "预研项目管理", "url_name": "basic_research_list"},
            ]
        }

    @staticmethod
    def get_material():
        """返回材料成品库菜单定义。"""
        return {
            "name": "材料成品库",
            "icon": "ti-database",
            "visible_to": IdentityConfig.INTERNAL_STAFF,
            "url_name": "material_list",
            "sub_items": [
                {"name": "成品材料列表", "url_name": "material_list"},
                {"name": "材料类型分类", "url_name": "type_list"},
                {"name": "材料特性分类", "url_name": "characteristic_list"},
                {"name": "应用场景分类", "url_name": "scenario_list"},
                {"name": "测试标准配置", "url_name": "test_config_list"},
            ]
        }

    @staticmethod
    def get_formula():
        """返回实验配方库菜单定义。"""
        return {
            "name": "实验配方库",
            "icon": "ti-test-pipe",
            "visible_to": IdentityConfig.RND_ONLY,
            "url_name": "formula_list",
            "sub_items": [
                {"name": "实验配方列表", "url_name": "formula_list"},
            ]
        }

    @staticmethod
    def get_process():
        """返回生产工艺库菜单定义。"""
        return {
            "name": "生产工艺库",
            "icon": "ti-settings-automation",
            "visible_to": IdentityConfig.TECH_CORE,
            "url_name": "process_profile_list",
            "sub_items": [
                {"name": "工艺方案列表", "url_name": "process_profile_list"},
                {"name": "机台型号管理", "url_name": "process_machine_list"},
                {"name": "螺杆组合管理", "url_name": "process_screw_list"},
            ]
        }

    @staticmethod
    def get_raw_material():
        """返回原材料/供应商菜单定义。"""
        return {
            "name": "原材料/供应商",
            "icon": "ti-packages",
            "visible_to": IdentityConfig.INTERNAL_STAFF,
            "url_name": "raw_material_list",
            "sub_items": [
                {"name": "原材料列表", "url_name": "raw_material_list"},
                {"name": "原材料类型分类", "url_name": "raw_type_list"},
                {"name": "供应商资料库", "url_name": "raw_supplier_list"},
            ]
        }

    @staticmethod
    def get_trial_production():
        """返回试验排产中心菜单定义。"""
        return {
            "name": "试验排产中心",
            "icon": "ti-building-factory",
            "visible_to": IdentityConfig.INTERNAL_STAFF,
            "url_name": "trial_production_dashboard",
            "sub_items": [
                {"name": "排产总览", "url_name": "trial_production_dashboard"},
                {"name": "挤出任务", "url_name": "trial_production_order_list"},
                {"name": "配色任务", "url_name": "trial_color_matching_list"},
                {"name": "注塑任务", "url_name": "trial_injection_list"},
                {"name": "测试任务", "url_name": "trial_testing_list"},
                {"name": "样品库存", "url_name": "trial_sample_inventory"},
                {"name": "模具台账", "url_name": "trial_mold_type_list"},
                {"name": "排产配置", "url_name": "trial_production_config"},
            ]
        }

    @staticmethod
    def get_admin():
        """返回系统管理设置菜单定义。"""
        return {
            "name": "系统管理设置",
            "icon": "ti-settings",
            # visible_to 限制为管理员角色；非 ADMIN 的超级用户通过 menu_service.py 中的
            # is_superuser 显式检查绕过此限制
            "visible_to": [IdentityConfig.R_ADMIN],
            "url_name": "project_config",
            "sub_items": [
                {"name": "项目全局配置", "url_name": "project_config"},
                {"name": "项目等级因子设置", "url_name": "repo_grade_factor_list"},
                {"name": "进入底层管理", "url_name": "admin:index"},
            ]
        }
