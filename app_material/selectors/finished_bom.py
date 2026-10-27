"""成品材料下的项目、阶段、实验单和 BOM 行。给发布页一次取完。"""

from collections import defaultdict

from django.db.models import Prefetch

from common_utils.formatting import exact_decimal

from app_formula.models import ColorPowderBOM, ColorPowderBOMEntry, FormulaBOM, LabFormula
from app_material.models import MaterialLibrary
from app_raw_material.models import Plant

_LINE_ORDER = (
    "feeding_port",
    "weighing_scale",
    "raw_material__category__order",
    "raw_material__name",
    "pk",
)


def list_active_plants() -> list[dict]:
    """启用中的工厂，按代码排序。"""
    return [
        {"code": plant.code, "name": plant.name}
        for plant in Plant.objects.filter(is_active=True).order_by("code")
    ]


def get_finished_bom_tree(sap_code: str) -> dict | None:
    """按成品 SAP 编码取出左树。编码不存在返回 None。

    项目来自 ``MaterialLibrary.projects``。配方挂在项目上；没挂阶段节点的
    归到该项目的「未关联阶段」。没挂项目的配方不出现。
    """
    material = MaterialLibrary.objects.filter(sap_material_code=sap_code).first()
    if material is None:
        return None

    formulas = list(_formulas(material))
    by_project = defaultdict(list)
    for formula in formulas:
        by_project[formula.project_id].append(formula)

    projects = material.projects.order_by("code", "pk")
    return {
        "material": {
            "id": material.pk,
            "grade_name": material.grade_name,
            "sap_material_code": material.sap_material_code,
        },
        "projects": [
            _project_payload(project, by_project.get(project.pk, []))
            for project in projects
        ],
    }


def _formulas(material):
    bom_lines = FormulaBOM.objects.select_related(
        "raw_material", "raw_material__category",
    ).order_by(*_LINE_ORDER)
    color_lines = ColorPowderBOMEntry.objects.select_related(
        "raw_material", "raw_material__category",
    ).order_by(*_LINE_ORDER)
    return (
        LabFormula.objects.filter(project__material=material)
        .select_related("project", "project_node")
        .prefetch_related(
            Prefetch("bom_lines", queryset=bom_lines),
            Prefetch("color_powder_bom__entries", queryset=color_lines),
        )
        .order_by("code", "version", "pk")
    )


def _project_payload(project, formulas) -> dict:
    staged = defaultdict(list)
    unassigned = []
    for formula in formulas:
        node = formula.project_node
        if node is None or node.project_id != project.pk:
            unassigned.append(formula)
        else:
            staged[node.pk].append(formula)

    nodes = []
    seen = {}
    for formula in formulas:
        node = formula.project_node
        if node is None or node.project_id != project.pk or node.pk in seen:
            continue
        seen[node.pk] = node
    ordered = sorted(seen.values(), key=lambda node: (node.order, node.round, node.pk))
    for node in ordered:
        nodes.append({
            "id": node.pk,
            "label": f"{node.get_stage_display()}（第{node.round}轮）",
            "stage": node.stage,
            "round": node.round,
            "order": node.order,
            "unassigned": False,
            "formulas": _group_formulas(staged[node.pk]),
        })
    if unassigned:
        nodes.append({
            "id": None,
            "label": "未关联阶段",
            "stage": "",
            "round": None,
            "order": None,
            "unassigned": True,
            "formulas": _group_formulas(unassigned),
        })
    return {
        "id": project.pk,
        "code": project.code,
        "name": project.name,
        "nodes": nodes,
    }


def _group_formulas(formulas) -> list[dict]:
    """同一实验单号的多个版本合成一组。组名用版本号最大的那条。"""
    groups = {}
    order = []
    for formula in sorted(formulas, key=lambda item: (item.code, item.version, item.pk)):
        group = groups.get(formula.code)
        if group is None:
            group = {"code": formula.code, "name": formula.name, "versions": []}
            groups[formula.code] = group
            order.append(formula.code)
        group["name"] = formula.name
        group["versions"].append(_version_payload(formula))
    return [groups[code] for code in order]


def _version_payload(formula) -> dict:
    color_lines = _color_lines(formula)
    return {
        "id": formula.pk,
        "version": formula.version,
        "name": formula.name,
        "is_mature": formula.is_mature,
        "has_color_bom": color_lines is not None,
        "main_lines": [_entry_payload(entry) for entry in formula.bom_lines.all()],
        "color_lines": color_lines or [],
    }


def _color_lines(formula):
    try:
        bom = formula.color_powder_bom
    except ColorPowderBOM.DoesNotExist:
        return None
    return [_entry_payload(entry, precise=True) for entry in bom.entries.all()]


def _entry_payload(entry, *, precise=False) -> dict:
    raw = entry.raw_material
    code = (raw.warehouse_code or "").strip()
    percentage = exact_decimal(entry.percentage) if precise else f"{entry.percentage:.3f}"
    return {
        "name": raw.name,
        "model_name": raw.model_name,
        "category_name": raw.category.name if raw.category_id else "",
        "warehouse_code": code,
        "percentage": percentage,
        "feeding_port": entry.feeding_port,
        "feeding_port_label": entry.get_feeding_port_display(),
        "weighing_scale": entry.weighing_scale,
        "weighing_scale_label": entry.get_weighing_scale_display(),
        "missing_sap_code": not code,
    }
