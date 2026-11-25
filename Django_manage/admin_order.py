"""Django Admin 首页应用分组顺序。

默认按分组名的 Unicode 码点排序，中文对不上业务链路。
这里只重排分组，组内模型仍由 Django 按名称排序。
"""

# 研发到生产的主链在前，支撑功能其次，权限管控沉底。
ADMIN_APP_ORDER = (
    "app_project",
    "app_repository",
    "app_basic_research",
    "app_raw_material",
    "app_formula",
    "app_material",
    "app_process",
    "app_trial_production",
    "app_color_center",
    "app_mold_injection",
    "app_material_testing",
    "app_workflow",
    "app_form_management",
    "app_notification",
    "app_attachment",
    "app_external_api",
    "app_user",
)

_RANK = {label: index for index, label in enumerate(ADMIN_APP_ORDER)}
_FALLBACK = len(_RANK)


def sort_admin_apps(app_list):
    """按 ADMIN_APP_ORDER 稳定排序。清单外的分组保持原相对顺序，排在后面。"""
    return sorted(
        app_list,
        key=lambda app: _RANK.get(app["app_label"], _FALLBACK),
    )


def install_admin_app_order(site):
    """替换站点的 get_app_list。单个应用页不重排。"""
    original = site.get_app_list

    def get_app_list(request, app_label=None):
        app_list = original(request, app_label)
        if app_label:
            return app_list
        return sort_admin_apps(app_list)

    site.get_app_list = get_app_list
