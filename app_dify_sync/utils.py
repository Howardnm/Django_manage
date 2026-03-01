from app_project.models import Project
from app_repository.models import MaterialLibrary
from app_raw_material.models import RawMaterial
from app_formula.models import LabFormula
from app_process.models import ProcessProfile

# --- 为每个模型定义独立的格式化函数 ---

def _format_project(instance: Project):
    name = f"项目 - {instance.name}"
    
    repo = getattr(instance, 'repository', None)
    
    info_lines = [f"- **项目ID**: {instance.pk}", f"- **负责人**: {instance.manager.username}"]
    if repo:
        if repo.customer: info_lines.append(f"- **客户**: {repo.customer.company_name}")
        if repo.oem: info_lines.append(f"- **主机厂**: {repo.oem.name}")
        if repo.material: info_lines.append(f"- **选用材料**: {repo.material.grade_name}")

    nodes_string = ""
    nodes = instance.nodes.order_by('order').all()
    if nodes:
        node_lines = []
        for node in nodes:
            node_lines.append(
                f"### {node.get_stage_display()} (第{node.round}轮)\n"
                f"- **状态**: {node.get_status_display()}\n"
                f"- **更新于**: {node.updated_at.strftime('%Y-%m-%d %H:%M')}\n"
                f"- **备注**: {node.remark or '无'}\n"
            )
        nodes_string = "\n---\n".join(node_lines)
    else:
        nodes_string = "暂无进度记录。"

    text = f"""
# 项目报告: {instance.name}
## 基础信息
{chr(10).join(info_lines)}
## 项目描述
{instance.description or '无'}
## 进度历史
{nodes_string}
"""
    return name, text.strip()

def _format_material_library(instance: MaterialLibrary):
    name = f"材料 - {instance.grade_name}"
    
    formulas_string = "\n".join([f"- {f.code}: {f.name}" for f in instance.formulas.all()]) or "无"
    
    properties_string = ""
    grouped_props = instance.get_grouped_properties()
    if grouped_props:
        prop_sections = []
        for group in grouped_props:
            items_str = "\n".join([f"  - {item['name']}: {item['value']} {item['unit']}" for item in group['items']])
            prop_sections.append(f"### {group['category_name']}\n{items_str}")
        properties_string = "\n".join(prop_sections)
    else:
        properties_string = "无性能数据。"

    text = f"""
# 材料: {instance.grade_name}
- **材料ID**: {instance.pk}
- **类型**: {instance.category.name}
- **生产厂家**: {instance.manufacturer}
- **阻燃等级**: {instance.flammability}
## 特性描述
{instance.description or '无'}
## 关联的实验配方
{formulas_string}
## 性能数据
{properties_string}
"""
    return name, text.strip()

def _format_raw_material(instance: RawMaterial):
    name = f"原材料 - {instance.name} {instance.model_name}"
    text = f"""
# 原材料: {instance.name} {instance.model_name}
- **原材料ID**: {instance.pk}
- **类型**: {instance.category.name}
- **供应商**: {instance.supplier.name if instance.supplier else 'N/A'}
- **内部编码**: {instance.warehouse_code or 'N/A'}
- **参考成本**: {instance.cost_price or 'N/A'} 元/kg
- **购入日期**: {instance.purchase_date or 'N/A'}
## 使用方法/描述
{instance.usage_method or '无'}
"""
    return name, text.strip()

def _format_lab_formula(instance: LabFormula):
    bom_string = "\n".join([f"- {line.raw_material.name} ({line.raw_material.model_name}): {line.percentage}%" for line in instance.bom_lines.select_related('raw_material').all()]) or "无"
    
    results_string = "\n".join([f"- {res.test_config.name}: {res.value or res.value_text} {res.test_config.unit}" for res in instance.test_results.select_related('test_config').all()]) or "无"

    name = f"配方 - {instance.name} - 基材【{instance.material_type.name}】"
    text = f"""
# 配方: {instance.name}
- **配方ID**: {instance.pk}
- **编码**: {instance.code}
- **创建者**: {instance.creator.username}
- **材料体系**: {instance.material_type.name}
- **关联工艺**: {instance.process.name if instance.process else '未指定'}
## 描述
{instance.description or '无'}
## BOM (配方明细)
{bom_string}
## 性能测试结果
{results_string}
"""
    return name, text.strip()

def _format_process_profile(instance: ProcessProfile):
    temps = [instance.temp_zone_1, instance.temp_zone_2, instance.temp_zone_3, instance.temp_zone_4, 
             instance.temp_zone_5, instance.temp_zone_6, instance.temp_zone_7, instance.temp_zone_8, 
             instance.temp_zone_9, instance.temp_zone_10, instance.temp_zone_11, instance.temp_zone_12]
    temp_str = " -> ".join(map(str, [t for t in temps if t > 0]))
    
    params = [
        f"- 温度设置: {temp_str} -> 机头({instance.temp_head}°C)",
        f"- 螺杆转速: {instance.screw_speed} rpm",
        f"- 主机扭矩: {instance.torque}%",
        f"- 总产量: {instance.throughput} kg/h",
    ]
    params_string = "\n".join(params)

    name = f"工艺 - {instance.name}"
    text = f"""
# 工艺方案: {instance.name}
- **工艺ID**: {instance.pk}
- **适用机台**: {instance.machine.model_name if instance.machine else '未指定'}
- **螺杆组合**: {instance.screw_combination.name if instance.screw_combination else '未指定'}
## 描述
{instance.description or '无'}
## 工艺参数
{params_string or '无'}
"""
    return name, text.strip()

# --- 主调用函数 ---

FORMATTER_MAP = {
    Project: _format_project,
    MaterialLibrary: _format_material_library,
    RawMaterial: _format_raw_material,
    LabFormula: _format_lab_formula,
    ProcessProfile: _format_process_profile,
}

def get_document_content(instance) -> (str, str):
    formatter = FORMATTER_MAP.get(type(instance))
    
    if formatter:
        return formatter(instance)
    
    name = f"对象: {str(instance)}"
    text = f"这是一个类型为 {type(instance).__name__} 的对象，ID为 {instance.pk}。"
    return name, text
