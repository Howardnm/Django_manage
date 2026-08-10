"""菜单模块定义 — 作为 SidebarModule / SidebarSubItem DB 表的代码定义源。

通过 `python manage.py sync_menus` 同步到 DB：

    - code / name / icon / url_name / sub_items.* — 代码覆盖（编程时确定）
    - sort_order / is_active / sub_items.role_groups — 保留 DB 值（管理员可调整）

数据结构约定:
    顶级模块 dict:
        { "code", "name", "icon", "url_name", "module_access_code", "sub_items" }
    其中 module_access_code 对应 ModuleAccessConfig.module_code，用于关联 L1 角色权限。

    子菜单 dict:
        { "name", "url_name", "permissions" }
        子项默认继承父模块的 ModuleAccessConfig 角色配置。

导出: MenuModule。
"""


class MenuModule:
    """定义各业务模块的菜单项。每个 get_*() 静态方法返回一个顶级模块字典。

    新增菜单模块时:
        1. 在此类添加 get_xxx() 方法
        2. 运行 python manage.py sync_menus 同步到 DB
    """

    @staticmethod
    def get_dashboard():
        return {
            "code": "dashboard",
            "name": "看板工作台",
            "icon": "smart-home",
            "url_name": "panel_home",
            "module_access_code": "panel",
            "sub_items": [
                {"name": "个人工作台", "url_name": "personal_workspace"},
                {"name": "系统总览", "url_name": "system_overview",
                 "permissions": ["app_project.view_project"]},
                {"name": "项目全景看板", "url_name": "project_overview",
                 "permissions": ["app_project.view_project"]},
                {"name": "项目统计看板", "url_name": "project_statistics",
                 "permissions": ["app_project.view_project"]},
                {"name": "客户行为分析", "url_name": "customer_activity_overview",
                 "permissions": ["app_repository.view_customer"]},
                {"name": "排产日历", "url_name": "scheduling_calendar"},
            ],
        }

    @staticmethod
    def get_project():
        return {
            "code": "project",
            "name": "项目管理中心",
            "icon": "subtask",
            "url_name": "project_list",
            "module_access_code": "project",
            "sub_items": [
                {"name": "项目列表", "url_name": "project_list"},
                {"name": "成员绩效看板", "url_name": "project_performance_list",
                 "permissions": ["app_project.view_project"]},
                {"name": "项目评分规则", "url_name": "project_score_rule_list",
                 "permissions": ["app_project.change_project"]},
                {"name": "不合格原因类型", "url_name": "failure_reason_list",
                 "permissions": ["app_project.change_project"]},
                {"name": "客户意见类型", "url_name": "feedback_type_list",
                 "permissions": ["app_project.change_project"]},
            ],
        }

    @staticmethod
    def get_repository():
        return {
            "code": "repository",
            "name": "客户档案中心",
            "icon": "archive",
            "url_name": "repo_customer_list",
            "module_access_code": "repository",
            "sub_items": [
                {"name": "客户资料库", "url_name": "repo_customer_list"},
                {"name": "客户评分排行", "url_name": "repo_customer_ranking"},
                {"name": "主机厂(OEM)库", "url_name": "repo_oem_list"},
            ],
        }

    @staticmethod
    def get_basic_research():
        return {
            "code": "basic_research",
            "name": "基础预研中心",
            "icon": "flask",
            "url_name": "basic_research_list",
            "module_access_code": "basic_research",
            "sub_items": [
                {"name": "预研项目管理", "url_name": "basic_research_list"},
            ],
        }

    @staticmethod
    def get_material():
        return {
            "code": "material",
            "name": "材料成品库",
            "icon": "database",
            "url_name": "material_list",
            "module_access_code": "material",
            "sub_items": [
                {"name": "成品材料列表", "url_name": "material_list"},
                {"name": "材料类型分类", "url_name": "type_list"},
                {"name": "材料特性分类", "url_name": "characteristic_list"},
                {"name": "应用场景分类", "url_name": "scenario_list"},
                {"name": "测试标准配置", "url_name": "test_config_list"},
            ],
        }

    @staticmethod
    def get_formula():
        return {
            "code": "formula",
            "name": "实验配方库",
            "icon": "test-pipe",
            "url_name": "formula_list",
            "module_access_code": "formula",
            "sub_items": [
                {"name": "实验配方列表", "url_name": "formula_list"},
            ],
        }

    @staticmethod
    def get_trial_production():
        return {
            "code": "trial_production",
            "name": "试验排产中心",
            "icon": "building-factory",
            "url_name": "trial_dashboard",
            "module_access_code": "trial_production",
            "sub_items": [
                {"name": "排产总览", "url_name": "trial_dashboard"},
            ],
        }

    @staticmethod
    def get_extrusion_production():
        return {
            "code": "extrusion_production",
            "name": "挤出排产中心",
            "icon": "stack",
            "url_name": "trial_extrusion_board",
            "module_access_code": "trial_production",
            "sub_items": [
                {"name": "排产工作台", "url_name": "trial_extrusion_board"},
                {"name": "挤出任务", "url_name": "trial_extrusion_task_list"},
                {"name": "成品颗粒库存", "url_name": "trial_sample_list"},
            ],
        }

    @staticmethod
    def get_color_center():
        return {
            "code": "color_center",
            "name": "材料配色中心",
            "icon": "palette",
            "url_name": "color_center:list",
            "module_access_code": "color_center",
            "sub_items": [
                {"name": "配色任务", "url_name": "color_center:list"},
                {"name": "产品项目", "url_name": "color_center:project_list"},
            ],
        }

    @staticmethod
    def get_mold_injection():
        return {
            "code": "mold_injection",
            "name": "模具注塑中心",
            "icon": "template",
            "url_name": "mold_injection:task_list",
            "module_access_code": "mold_injection.task",
            "sub_items": [
                {"name": "注塑任务", "url_name": "mold_injection:task_list"},
                {"name": "样品库存", "url_name": "mold_injection:sample_list"},
                {"name": "模具台账", "url_name": "mold_injection:mold_list"},
            ],
        }

    @staticmethod
    def get_material_testing():
        return {
            "code": "material_testing",
            "name": "材料测试中心",
            "icon": "test-pipe",
            "url_name": "material_testing:list",
            "module_access_code": "material_testing",
            "sub_items": [
                {"name": "测试任务", "url_name": "material_testing:list"},
                {"name": "样条库存", "url_name": "material_testing:specimens"},
            ],
        }

    @staticmethod
    def get_process():
        return {
            "code": "process",
            "name": "生产工艺库",
            "icon": "settings-automation",
            "url_name": "process_profile_list",
            "module_access_code": "process",
            "sub_items": [
                {"name": "工艺方案列表", "url_name": "process_profile_list"},
                {"name": "机台型号管理", "url_name": "process_machine_list"},
                {"name": "螺杆组合管理", "url_name": "process_screw_list"},
            ],
        }

    @staticmethod
    def get_raw_material():
        return {
            "code": "raw_material",
            "name": "原材料/供应商",
            "icon": "packages",
            "url_name": "raw_material_list",
            "module_access_code": "raw_material",
            "sub_items": [
                {"name": "原材料列表", "url_name": "raw_material_list"},
                {"name": "原材料类型分类", "url_name": "raw_type_list"},
                {"name": "供应商资料库", "url_name": "raw_supplier_list"},
            ],
        }

    @staticmethod
    def get_form_management():
        return {
            "code": "form_management",
            "name": "表单管理中心",
            "icon": "forms",
            "url_name": "form_template_list",
            "module_access_code": "form_management",
            "sub_items": [
                {"name": "创建表单", "url_name": "form_create_wizard"},
                {"name": "我的表单草稿", "url_name": "my_drafts"},
                {"name": "我的表单提交", "url_name": "my_submissions"},
                {"name": "表单模板管理", "url_name": "form_template_list"},
            ],
        }

    @staticmethod
    def get_workflow():
        return {
            "code": "workflow",
            "name": "流程审批中心",
            "icon": "git-pull-request",
            "url_name": "workflow_my_tasks",
            "module_access_code": "workflow",
            "sub_items": [
                {"name": "我的待办任务", "url_name": "workflow_my_tasks",
                 "permissions": ["app_workflow.view_workflowtask"]},
                {"name": "我的已办任务", "url_name": "workflow_completed_tasks",
                 "permissions": ["app_workflow.view_workflowtask"]},
                {"name": "我发起的流程", "url_name": "workflow_initiated_list",
                 "permissions": ["app_workflow.view_workflowinstance"]},
                {"name": "流程定义管理", "url_name": "workflow_definition_list",
                 "permissions": ["app_workflow.view_workflowdefinition"]},
            ],
        }

    @staticmethod
    def get_admin():
        return {
            "code": "admin",
            "name": "系统管理设置",
            "icon": "settings",
            "url_name": "admin:index",
            "module_access_code": None,  # 仅超管可见
            "sub_items": [
                {"name": "项目全局配置",
                 "url_name": "admin:app_project_projectconfig_changelist"},
                {"name": "排产配置",
                 "url_name": "admin:app_trial_production_trialproductionconfig_changelist"},
                {"name": "项目等级因子设置", "url_name": "repo_grade_factor_list"},
                {"name": "进入底层管理", "url_name": "admin:index"},
            ],
        }
