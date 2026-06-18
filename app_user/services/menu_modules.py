"""菜单模块定义。为每个业务区域提供静态菜单配置。

导出: MenuModule。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 数据结构约定
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

■ 顶级模块字典 (每个 get_*() 方法的返回值)
  {
      "name":       str,              # 必填 · 模块显示名称（中文）
      "icon":       str,              # 必填 · Tabler Icons 图标类名（不含 "ti-" 前缀）
      "visible_to": list[UserType],   # 必填 · L1 角色白名单，控制整个模块的可见性
      "url_name":   str,              # 必填 · Django URL name，用于 reverse() 解析
      "sub_items":  list[dict],       # 可选 · 子菜单项列表（见下方）
  }

■ 子菜单项字典 (sub_items 中的每一项)
  {
      "name":        str,                    # 必填 · 子菜单显示名称
      "url_name":    str,                    # 必填 · Django URL name
      "visible_to":  list[UserType],         # 可选 · L1 角色白名单（缺省 → 继承父模块）
      "min_level":   int,                    # 可选 · L2 用户等级门槛（缺省 → 不检查）
      "permissions": list[str],              # 可选 · L3 Django 权限码（缺省 → 不检查）
  }

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 三层可见性控制 (L1 → L2 → L3，短路求值)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  L1 visible_to   角色白名单。
                  · 子项声明时使用自身的角色列表
                  · 子项未声明时自动继承父模块的 visible_to
                  · 值来源: IdentityConfig 中的预定义分组，或自行拼接列表

  L2 min_level    用户等级门槛。
                  · 要求 user.user_level >= min_level
                  · 典型场景: 管理类功能限制高职级人员
                  · 与视图层 UnifiedAccessMixin.min_level_required 对齐

  L3 permissions  Django 原生权限码列表。
                  · 要求 user.has_perms(permissions) 全部通过
                  · 权限码格式: "{app_label}.{action}_{model}"
                  · 由 init_permissions 命令按角色组预设，管理员可在 Django Admin 调整
                  · 适合动态控制：不改代码，通过调整权限组即可改变菜单可见性

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 使用示例
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. 所有内部人员可见（继承父模块 INTERNAL_STAFF）:
     {"name": "项目列表", "url_name": "project_list"}

  2. 限制特定角色（L1）:
     {"name": "排产总览", "url_name": "trial_production_dashboard", "visible_to": IdentityConfig.RND_ONLY}

  3. 自定义角色并集（L1）:
     {"name": "配色任务", "url_name": "trial_color_matching_list", "visible_to": IdentityConfig.TECH_CORE + [IdentityConfig.R_COLOR_OP]}

  4. 等级门槛（L2）:
     {"name": "项目评分规则", "url_name": "project_score_rule_list", "min_level": 15}

  5. 权限码控制（L3），管理员可通过后台动态调整:
     {"name": "流程定义管理", "url_name": "workflow_definition_list", "permissions": ["app_workflow.view_workflowdefinition"]}

  6. 组合使用（L1 + L2 + L3 全部通过才可见）:
     {"name": "项目评分规则", "url_name": "project_score_rule_list", "min_level": 15, "permissions": ["app_project.change_project"]}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 注意事项
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  · 超级用户 (is_superuser=True) 绕过所有三层检查，始终可见
  · 若某模块的所有子项均被过滤，整个模块自动隐藏（不显示空壳）
  · 子项的 visible_to 与父模块是 **独立** 关系（覆盖而非交集）
  · permissions 中若包含不存在的权限码，has_perms() 返回 False，子项隐藏
  · url_name 解析失败 (NoReverseMatch) 的子项也会被静默跳过
"""

from app_user.mixins import IdentityConfig


class MenuModule:
    """定义各业务模块的菜单项。

    每个 get_*() 静态方法返回一个顶级模块字典，结构与字段约定见文件头注释。
    新增菜单模块时：
        1. 在此类添加 get_xxx() 方法
        2. 在 menu_service.py 的 raw_modules 列表中注册调用
    """

    @staticmethod
    def get_dashboard():
        """返回看板工作台菜单定义。

        模块级: INTERNAL_STAFF（内部全员可见）
        子项: 除系统资源看板外均要求 L3 权限码，
              确保用户只看到自己有数据权限的看板入口。
        """
        return {
            "name": "看板工作台",
            "icon": "ti-smart-home",
            "visible_to": IdentityConfig.INTERNAL_STAFF,
            "url_name": "panel_home",
            "sub_items": [
                {"name": "系统资源看板", "url_name": "panel_home"},
                {"name": "项目全景看板", "url_name": "project_overview", "permissions": ["app_project.view_project"]},
                {"name": "项目统计看板", "url_name": "project_statistics", "permissions": ["app_project.view_project"]},
                {"name": "客户行为分析", "url_name": "customer_activity_overview", "permissions": ["app_repository.view_customer"]},
                {"name": "成员绩效榜单", "url_name": "user_performance_list", "permissions": ["app_project.view_project"]},
            ]
        }

    @staticmethod
    def get_project():
        """返回项目管理中心菜单定义。

        模块级: INTERNAL_STAFF
        子项: 评分规则使用 L2 等级 + L3 权限码双重限制，
              对齐 PerformanceManagementMixin.min_level_required=15。
        """
        return {
            "name": "项目管理中心",
            "icon": "ti-subtask",
            "visible_to": IdentityConfig.INTERNAL_STAFF,
            "url_name": "project_list",
            "sub_items": [
                {"name": "项目列表", "url_name": "project_list"},
                {"name": "成员绩效看板", "url_name": "project_performance_list", "permissions": ["app_project.view_project"]},
                # 仅高等级管理人员可见（对齐 PerformanceManagementMixin.min_level_required=15）
                {"name": "项目评分规则", "url_name": "project_score_rule_list", "min_level": 15, "permissions": ["app_project.change_project"]},
            ]
        }

    @staticmethod
    def get_form_management():
        """返回表单管理中心菜单定义。

        模块级: INTERNAL_STAFF
        子项: 全部继承父模块，无额外限制。
              表单系统面向全员开放，具体数据隔离在视图层处理。
        """
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
        """返回流程审批中心菜单定义。

        模块级: INTERNAL_STAFF
        子项: 全部使用 L3 权限码控制。
              权限由 init_permissions 按角色组分配，管理员可通过后台动态调整。
        """
        return {
            "name": "流程审批中心",
            "icon": "ti-git-pull-request",
            "visible_to": IdentityConfig.INTERNAL_STAFF,
            "url_name": "workflow_my_tasks",
            "sub_items": [
                {"name": "我的待办任务", "url_name": "workflow_my_tasks", "permissions": ["app_workflow.view_workflowtask"]},
                {"name": "我的已办任务", "url_name": "workflow_completed_tasks", "permissions": ["app_workflow.view_workflowtask"]},
                {"name": "我发起的流程", "url_name": "workflow_initiated_list", "permissions": ["app_workflow.view_workflowinstance"]},
                {"name": "流程定义管理", "url_name": "workflow_definition_list", "permissions": ["app_workflow.view_workflowdefinition"]},
            ]
        }

    @staticmethod
    def get_repository():
        """返回客户档案中心菜单定义。

        模块级: INTERNAL_STAFF
        子项: 全部继承父模块，无额外限制。
              数据隔离（部门级 L4）在视图层 RepositoryAccessMixin 中处理。
        """
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
        """返回基础预研中心菜单定义。

        模块级: RND_ONLY（仅研发工程师 + 管理员）
        子项: 仅一项，继承父模块。
        """
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
        """返回材料成品库菜单定义。

        模块级: INTERNAL_STAFF
        子项: 全部继承父模块。
              材料库为共享资源库，所有内部人员均可浏览；
              编辑权限在视图层通过 L3 权限码控制。
        """
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
        """返回实验配方库菜单定义。

        模块级: RND_ONLY（仅研发工程师 + 管理员）
        子项: 仅一项，继承父模块。
        """
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
        """返回生产工艺库菜单定义。

        模块级: TECH_CORE（研发 + 工艺 + 管理员）
        子项: 全部继承父模块。
        """
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
        """返回原材料/供应商菜单定义。

        模块级: TECH_CORE + 采购（对齐 RawMaterialAccessMixin）
        子项: 全部继承父模块。
              Sales 和操作员角色在模块级即被排除。
        """
        return {
            "name": "原材料/供应商",
            "icon": "ti-packages",
            "visible_to": IdentityConfig.TECH_CORE + [IdentityConfig.R_PURCHASING],
            "url_name": "raw_material_list",
            "sub_items": [
                {"name": "原材料列表", "url_name": "raw_material_list"},
                {"name": "原材料类型分类", "url_name": "raw_type_list"},
                {"name": "供应商资料库", "url_name": "raw_supplier_list"},
            ]
        }

    @staticmethod
    def get_trial_production():
        """返回试验排产中心菜单定义。

        模块级: TECH_CORE + 四位操作员 + 采购（对齐 TrialProductionAccessMixin 并集）
              Sales 在模块级排除（无排产业务职能）。
        子项: 差异最大——排产总览/配置限 RND，
              配色/注塑/测试任务限 TECH_CORE + 对应操作员，
              挤出/样品/模具继承模块级权限。
        """
        return {
            "name": "试验排产中心",
            "icon": "ti-building-factory",
            "visible_to": IdentityConfig.TECH_CORE + [
                IdentityConfig.R_EXTRUSION_OP, IdentityConfig.R_COLOR_OP,
                IdentityConfig.R_INJECTION_OP, IdentityConfig.R_TESTING_OP,
                IdentityConfig.R_PURCHASING,
            ],
            "url_name": "trial_production_dashboard",
            "sub_items": [
                # 对齐 DashboardAccessMixin.identity_required
                {"name": "排产总览", "url_name": "trial_production_dashboard", "visible_to": IdentityConfig.RND_ONLY},
                {"name": "挤出任务", "url_name": "trial_production_order_list"},
                # 对齐 ColorTaskAccessMixin
                {"name": "配色任务", "url_name": "trial_color_matching_list", "visible_to": IdentityConfig.TECH_CORE + [IdentityConfig.R_COLOR_OP]},
                # 对齐 InjectionTaskAccessMixin
                {"name": "注塑任务", "url_name": "trial_injection_list", "visible_to": IdentityConfig.TECH_CORE + [IdentityConfig.R_INJECTION_OP]},
                # 对齐 TestingTaskAccessMixin
                {"name": "测试任务", "url_name": "trial_testing_list", "visible_to": IdentityConfig.TECH_CORE + [IdentityConfig.R_TESTING_OP]},
                {"name": "样品库存", "url_name": "trial_sample_inventory"},
                {"name": "模具台账", "url_name": "trial_mold_type_list"},
                # 对齐 TrialConfigView（L1 RND_ONLY + L3 配置编辑权限）
                {"name": "排产配置", "url_name": "trial_production_config", "visible_to": IdentityConfig.RND_ONLY, "permissions": ["app_trial_production.change_trialproductionconfig"]},
            ]
        }

    @staticmethod
    def get_admin():
        """返回系统管理设置菜单定义。

        模块级: 仅 ADMIN 角色（超级用户通过 is_superuser 绕过）。
        子项: 全部继承父模块。
        """
        return {
            "name": "系统管理设置",
            "icon": "ti-settings",
            "visible_to": [IdentityConfig.R_ADMIN],
            "url_name": "project_config",
            "sub_items": [
                {"name": "项目全局配置", "url_name": "project_config"},
                {"name": "项目等级因子设置", "url_name": "repo_grade_factor_list"},
                {"name": "进入底层管理", "url_name": "admin:index"},
            ]
        }
