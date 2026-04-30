from app_user.mixins import IdentityConfig

class MenuModule:
    """定义各业务模块的菜单项"""

    @staticmethod
    def get_dashboard():
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
        return {
            "name": "项目管理中心",
            "icon": "ti-subtask",
            "visible_to": IdentityConfig.INTERNAL_STAFF,
            "url_name": "project_list",
            "sub_items": [
                {"name": "项目列表", "url_name": "project_list"},
                {"name": "成员绩效看板", "url_name": "project_performance_list"},
            ]
        }

    @staticmethod
    def get_workflow():
        """【新增】工作流审批中心"""
        return {
            "name": "流程审批中心",
            "icon": "ti-git-pull-request",
            "visible_to": IdentityConfig.INTERNAL_STAFF,
            "url_name": "workflow_my_tasks",
            "sub_items": [
                {"name": "我的待办任务", "url_name": "workflow_my_tasks"},
                {"name": "我的已办任务", "url_name": "workflow_completed_tasks"}, # 新增
                {"name": "流程定义管理", "url_name": "workflow_definition_list"},
            ]
        }

    @staticmethod
    def get_repository():
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
    def get_admin():
        return {
            "name": "系统管理设置",
            "icon": "ti-settings",
            "visible_to": [IdentityConfig.R_ADMIN],
            "url_name": "project_score_rule_list",
            "sub_items": [
                {"name": "项目绩效评分规则", "url_name": "project_score_rule_list"},
                {"name": "项目等级因子设置", "url_name": "repo_grade_factor_list"},
                {"name": "进入底层管理", "url_name": "admin:index"},
            ]
        }
