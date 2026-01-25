import os
import django
import sys

# 初始化 Django 环境
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Django_manage.settings')
django.setup()

from app_repository.models import MetricCategory, TestConfig


def run():
    print("🚀 开始初始化改性塑料行业测试标准库 (ISO/ASTM)...")

    # 1. 定义分类 (按行业习惯排序)
    categories = {
        '物理性能': 10,
        '机械性能': 20,
        '热学性能': 30,
        '阻燃/电气': 40,
        '老化/耐候': 50,
        '其他性能': 60,
    }

    cat_objs = {}
    for name, order in categories.items():
        obj, created = MetricCategory.objects.get_or_create(name=name, defaults={'order': order})
        cat_objs[name] = obj
        if created: print(f"   + 创建分类: {name}")

    # 2. 定义配置项 (指标 | 标准 | 条件 | 单位 | 分类 | 排序 | 数据类型 | 选项配置)
    # 数据类型: 'NUMBER' (默认), 'TEXT', 'SELECT'
    # 选项配置: 仅当类型为 SELECT 时有效，逗号分隔
    configs = [
        # =========================================================
        # A. 物理性能 (Physical)
        # =========================================================
        ('密度', 'ISO 1183', '23℃', 'g/cm³', '物理性能', 10, 'NUMBER', ''),
        ('比重', 'ASTM D792', '23℃', '', '物理性能', 11, 'NUMBER', ''),
        ('熔融指数 (MFR)', 'ISO 1133', '230℃/2.16kg', 'g/10min', '物理性能', 21, 'NUMBER', ''),
        ('熔融指数 (MFR)', 'ASTM D1238', '230℃/2.16kg', 'g/10min', '物理性能', 22, 'NUMBER', ''),
        ('熔融指数 (MFR)', 'ISO 1133', '300℃/1.2kg', 'g/10min', '物理性能', 23, 'NUMBER', ''), # PC常用
        ('成型收缩率 (流动方向)', 'ISO 294-4', '23℃/48h', '%', '物理性能', 30, 'NUMBER', ''),
        ('成型收缩率 (垂直方向)', 'ISO 294-4', '23℃/48h', '%', '物理性能', 31, 'NUMBER', ''),
        ('成型收缩率', 'ASTM D955', 'Flow', '%', '物理性能', 32, 'NUMBER', ''),
        ('吸水率', 'ISO 62', '23℃, 24h', '%', '物理性能', 40, 'NUMBER', ''),
        ('吸水率', 'ASTM D570', '23℃, 24h', '%', '物理性能', 41, 'NUMBER', ''),
        ('灰分', 'ISO 3451', '600℃/30min', '%', '物理性能', 50, 'NUMBER', ''),
        ("灰分", "ASTM D5630", "600℃", "%", '物理性能', 51, 'NUMBER', ''),

        # =========================================================
        # B. 机械性能 (Mechanical)
        # =========================================================
        # 拉伸
        ('拉伸强度', 'ISO 527', '50mm/min', 'MPa', '机械性能', 10, 'NUMBER', ''),
        ('拉伸强度', 'ASTM D638', '50mm/min', 'MPa', '机械性能', 12, 'NUMBER', ''),
        ('断裂伸长率', 'ISO 527', '50mm/min', '%', '机械性能', 13, 'NUMBER', ''),
        ('断裂伸长率', 'ASTM D638', '50mm/min', '%', '机械性能', 14, 'NUMBER', ''),
        ('拉伸模量', 'ISO 527', '1mm/min', 'MPa', '机械性能', 15, 'NUMBER', ''),
        
        # 弯曲
        ('弯曲强度', 'ISO 178', '2mm/min', 'MPa', '机械性能', 20, 'NUMBER', ''),
        ('弯曲强度', 'ASTM D790', '1.3mm/min', 'MPa', '机械性能', 21, 'NUMBER', ''),
        ('弯曲模量', 'ISO 178', '2mm/min', 'MPa', '机械性能', 22, 'NUMBER', ''),
        ('弯曲模量', 'ASTM D790', '1.3mm/min', 'MPa', '机械性能', 23, 'NUMBER', ''),

        # 冲击 (ISO 简支梁/悬臂梁 vs ASTM 悬臂梁)
        ('简支梁缺口冲击', 'ISO 179/1eA', '23℃', 'kJ/m²', '机械性能', 30, 'NUMBER', ''),
        ('简支梁缺口冲击', 'ISO 179/1eA', '-30℃', 'kJ/m²', '机械性能', 31, 'NUMBER', ''),
        ('简支梁无缺口冲击', 'ISO 179/1eU', '23℃', 'kJ/m²', '机械性能', 32, 'NUMBER', ''),
        ('悬臂梁缺口冲击', 'ISO 180/1A', '23℃', 'kJ/m²', '机械性能', 35, 'NUMBER', ''),
        ('悬臂梁缺口冲击', 'ISO 180/1A', '-30℃', 'kJ/m²', '机械性能', 36, 'NUMBER', ''),
        ('悬臂梁缺口冲击', 'ASTM D256', '23℃', 'J/m', '机械性能', 37, 'NUMBER', ''), # 注意单位差异
        ('悬臂梁缺口冲击', 'ASTM D256', '-30℃', 'J/m', '机械性能', 38, 'NUMBER', ''),

        # 硬度
        ('洛氏硬度', 'ISO 2039-2', 'R Scale', '-', '机械性能', 40, 'TEXT', ''), # 硬度有时带字母，可设为文本
        ('洛氏硬度', 'ASTM D785', 'R Scale', '-', '机械性能', 41, 'TEXT', ''),
        ('邵氏硬度', 'ISO 868', 'Shore D', '-', '机械性能', 42, 'NUMBER', ''),

        # =========================================================
        # C. 热学性能 (Thermal)
        # =========================================================
        ('热变形温度 (HDT)', 'ISO 75', '1.80 MPa', '℃', '热学性能', 10, 'NUMBER', ''),
        ('热变形温度 (HDT)', 'ISO 75', '0.45 MPa', '℃', '热学性能', 11, 'NUMBER', ''),
        ('热变形温度 (HDT)', 'ASTM D648', '1.82 MPa', '℃', '热学性能', 12, 'NUMBER', ''),
        ('热变形温度 (HDT)', 'ASTM D648', '0.45 MPa', '℃', '热学性能', 13, 'NUMBER', ''),
        ('维卡软化点 (Vicat)', 'ISO 306', 'B50 (50N, 50℃/h)', '℃', '热学性能', 20, 'NUMBER', ''),
        ('维卡软化点 (Vicat)', 'ASTM D1525', 'B50', '℃', '热学性能', 21, 'NUMBER', ''),
        ('熔点', 'ISO 11357', 'DSC, 10℃/min', '℃', '热学性能', 30, 'NUMBER', ''),
        ('线性热膨胀系数 (CLTE)', 'ISO 11359', 'Flow', '10⁻⁵/K', '热学性能', 40, 'NUMBER', ''),
        ('线性热膨胀系数 (CLTE)', 'ASTM D696', 'Flow', '10⁻⁵/K', '热学性能', 41, 'NUMBER', ''),
        ('RTI (Elec)', 'UL 746B', '', '℃', '热学性能', 50, 'NUMBER', ''),
        ('RTI (Imp)', 'UL 746B', '', '℃', '热学性能', 51, 'NUMBER', ''),
        ('RTI (Str)', 'UL 746B', '', '℃', '热学性能', 52, 'NUMBER', ''),

        # =========================================================
        # D. 阻燃/电气 (Flammability & Electrical)
        # =========================================================
        # 【修改】阻燃等级改为 SELECT 类型，并配置选项
        ('阻燃等级', 'UL 94', '0.8mm', 'Class', '阻燃/电气', 10, 'SELECT', 'HB,V-2,V-1,V-0,5VB,5VA'),
        ('阻燃等级', 'UL 94', '1.6mm', 'Class', '阻燃/电气', 11, 'SELECT', 'HB,V-2,V-1,V-0,5VB,5VA'),
        ('阻燃等级', 'UL 94', '3.2mm', 'Class', '阻燃/电气', 12, 'SELECT', 'HB,V-2,V-1,V-0,5VB,5VA'),
        ('5V 阻燃', 'UL 94', '5VB/5VA', 'Class', '阻燃/电气', 13, 'SELECT', '5VB,5VA'),
        
        ('灼热丝起燃温度 (GWIT)', 'IEC 60695-2-13', '2.0mm', '℃', '阻燃/电气', 20, 'NUMBER', ''),
        ('灼热丝可燃指数 (GWFI)', 'IEC 60695-2-12', '2.0mm', '℃', '阻燃/电气', 21, 'NUMBER', ''),
        ('相比漏电起痕指数 (CTI)', 'IEC 60112', '', 'V', '阻燃/电气', 30, 'NUMBER', ''),
        ('体积电阻率', 'IEC 60093', '', 'Ω·cm', '阻燃/电气', 40, 'NUMBER', ''),
        ('表面电阻率', 'IEC 60093', '', 'Ω', '阻燃/电气', 41, 'NUMBER', ''),
        ('介电强度', 'IEC 60243-1', '', 'kV/mm', '阻燃/电气', 50, 'NUMBER', ''),

        # =========================================================
        # E. 老化/耐候 (Aging & Weathering) - 汽车/户外常用
        # =========================================================
        ('UV老化 (色差 ΔE)', 'ISO 4892-2', '1000h', '-', '老化/耐候', 10, 'NUMBER', ''),
        ('UV老化 (力学保持率)', 'ISO 4892-2', '1000h', '%', '老化/耐候', 11, 'NUMBER', ''),
        ('热老化 (力学保持率)', 'ISO 188', '150℃/1000h', '%', '老化/耐候', 20, 'NUMBER', ''),
        ('耐水解 (力学保持率)', 'Internal', '85℃/85%RH/1000h', '%', '老化/耐候', 30, 'NUMBER', ''),
        ('气味等级', 'VDA 270', 'C3', 'Grade', '老化/耐候', 40, 'NUMBER', ''), # 汽车内饰常用
        ('总碳挥发 (VOC)', 'VDA 277', '', 'µgC/g', '老化/耐候', 41, 'NUMBER', ''),
    ]

    count = 0
    for name, std, cond, unit, cat_name, order, dtype, opts in configs:
        # 使用 get_or_create 防止重复添加
        obj, created = TestConfig.objects.get_or_create(
            category=cat_objs[cat_name],
            name=name,
            standard=std,
            condition=cond,
            defaults={
                'unit': unit,
                'order': order,
                'data_type': dtype,
                'options_config': opts
            }
        )
        if created:
            count += 1
            print(f"   + [新增] {cat_name}: {name} ({std}) - {dtype}")
        else:
            # 如果已存在，更新排序、单位、数据类型和选项配置，确保配置是最新的
            obj.order = order
            obj.unit = unit
            obj.data_type = dtype
            obj.options_config = opts
            obj.save()
            # print(f"   . [更新] {name}")

    print(f"\n✅ 初始化完成！共新增 {count} 条标准，更新了现有标准。")


if __name__ == '__main__':
    run()