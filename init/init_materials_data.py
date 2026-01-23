import os
import django
import sys

# 初始化 Django 环境
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Django_manage.settings')
django.setup()

from app_repository.models import MaterialType, ApplicationScenario


def run():
    print("🚀 开始初始化材料数据库基础信息 (全球塑料行业标准版)...")

    # 1. 初始化材料类型 (MaterialType)
    # 格式: (名称, 描述, 归类)
    # 归类代码: COMMODITY, ENGINEERING, SPECIAL, FLUORINE, ELASTOMER, BIO, ALLOY, OTHER
    material_types = [
        # --- 通用塑料 (Commodity Plastics) ---
        ('PP', '聚丙烯 (Polypropylene)，低密度、耐化学品、耐疲劳、成本低，改性应用最广', 'COMMODITY'),
        ('PE', '聚乙烯 (Polyethylene)，包括LDPE/HDPE/LLDPE，优异的电绝缘性、耐低温、耐化学品', 'COMMODITY'),
        ('PVC', '聚氯乙烯 (Polyvinyl Chloride)，阻燃、耐化学腐蚀、机械强度高，分软硬两种', 'COMMODITY'),
        ('PS', '聚苯乙烯 (Polystyrene)，高透明、刚性好、易加工，但脆性大', 'COMMODITY'),
        ('ABS', '丙烯腈-丁二烯-苯乙烯，综合力学性能优良，高光泽，易涂装电镀', 'COMMODITY'),
        ('HIPS', '高抗冲聚苯乙烯，比普通PS韧性更好，常用于家电外壳', 'COMMODITY'),
        ('SAN', '苯乙烯-丙烯腈 (AS)，比PS耐热、耐化学性更好，高透明', 'COMMODITY'),
        ('ASA', '丙烯腈-苯乙烯-丙烯酸酯，耐候性极佳，类似ABS但适合户外使用', 'COMMODITY'),
        ('PMMA', '聚甲基丙烯酸甲酯 (亚克力)，极高透明度(92%)，耐候性好，高硬度', 'COMMODITY'),

        # --- 泛用工程塑料 (General Engineering Plastics) ---
        ('PA6', '尼龙6 (Polyamide 6)，韧性好、表面光泽佳、易加工，吸湿性较大', 'ENGINEERING'),
        ('PA66', '尼龙66 (Polyamide 66)，高强度、耐热性优于PA6，耐磨损，改性首选', 'ENGINEERING'),
        ('PC', '聚碳酸酯 (Polycarbonate)，高透明、高抗冲、尺寸稳定、耐热性好', 'ENGINEERING'),
        ('POM', '聚甲醛 (Acetal/Delrin)，高结晶、高硬度、自润滑、耐疲劳，"赛钢"', 'ENGINEERING'),
        ('PBT', '聚对苯二甲酸丁二醇酯，结晶快、耐化学品、电性能优异，尺寸稳定', 'ENGINEERING'),
        ('PET', '聚对苯二甲酸乙二醇酯，高强度、耐热、电性能好，常需玻纤增强', 'ENGINEERING'),
        ('PPO', '聚苯醚 (PPE)，低吸水、尺寸稳定、介电性能极佳，常与PS共混(MPPO)', 'ENGINEERING'),

        # --- 高级/特种工程塑料 (High Performance Plastics) ---
        ('PA12', '尼龙12，长碳链尼龙，极低吸水率、耐低温、尺寸稳定，用于油管/光缆', 'SPECIAL'),
        ('PA46', '尼龙46，极高结晶度，耐高温、高刚性，用于电子/汽车耐热件', 'SPECIAL'),
        ('PPA', '高温尼龙 (Polyphthalamide)，耐高温(HDT>280℃)、低吸湿、耐化学品', 'SPECIAL'),
        ('PPS', '聚苯硫醚 (Polyphenylene Sulfide)，耐高温、阻燃、耐化学品，"塑料黄金"', 'SPECIAL'),
        ('LCP', '液晶聚合物 (Liquid Crystal Polymer)，超高流动、耐高温、尺寸精密，连接器首选', 'SPECIAL'),
        ('PEI', '聚醚酰亚胺 (Ultem)，耐高温、高强度、固有阻燃、透波性好', 'SPECIAL'),
        ('PEEK', '聚醚醚酮，超高性能，耐高温(260℃长期)、耐磨、耐腐蚀、耐辐射', 'SPECIAL'),
        ('PSU', '聚砜 (Polysulfone)，耐高温、耐水解、高强度透明', 'SPECIAL'),
        ('PES', '聚醚砜 (Polyethersulfone)，比PSU耐热性更高，优异的尺寸稳定性', 'SPECIAL'),
        ('PPSU', '聚苯砜，极高的耐冲击性和耐水解性，可反复蒸汽灭菌', 'SPECIAL'),
        ('PAI', '聚酰胺-酰亚胺 (Torlon)，极高的机械强度和耐磨性，耐高温', 'SPECIAL'),
        ('PI', '聚酰亚胺，耐极高温(>300℃)、耐磨、绝缘', 'SPECIAL'),

        # --- 氟塑料 (Fluoropolymers) ---
        ('PTFE', '聚四氟乙烯 (Teflon)，"塑料王"，耐腐蚀、低摩擦、不粘、耐高低温', 'FLUORINE'),
        ('PVDF', '聚偏二氟乙烯，耐化学品、耐候、压电性能，用于锂电粘结剂/隔膜', 'FLUORINE'),

        # --- 热塑性弹性体 (Elastomers) ---
        ('TPE', '热塑性弹性体 (General)，触感柔软、高回弹、易加工', 'ELASTOMER'),
        ('TPU', '热塑性聚氨酯，高耐磨、高弹性、耐油、耐低温', 'ELASTOMER'),
        ('TPV', '热塑性硫化橡胶，耐高温、耐油、耐候性接近EPDM橡胶', 'ELASTOMER'),
        ('TPEE', '热塑性聚酯弹性体，高强度、高回弹、耐疲劳', 'ELASTOMER'),

        # --- 生物降解塑料 (Biodegradable) ---
        ('PLA', '聚乳酸，生物基，可堆肥降解，高硬度但脆', 'BIO'),
        ('PBAT', '聚己二酸/对苯二甲酸丁二醇酯，生物降解，柔韧性好，常与PLA共混', 'BIO'),

        # --- 塑料合金 (Alloys/Blends) ---
        ('PC/ABS', 'PC与ABS合金，结合了PC的高抗冲/耐热和ABS的易加工/低温韧性', 'ALLOY'),
        ('PC/PBT', 'PC与PBT合金，结合了PC的韧性和PBT的耐化学品/流动性', 'ALLOY'),
        ('PA/ABS', '尼龙与ABS合金，哑光效果，改善尼龙吸湿和ABS耐热', 'ALLOY'),
    ]

    print(f"\n🔹 正在初始化 {len(material_types)} 种材料类型...")
    for name, desc, classification in material_types:
        obj, created = MaterialType.objects.get_or_create(
            name=name,
            defaults={
                'description': desc,
                'classification': classification
            }
        )
        if created:
            print(f"   + [新增] {name} ({classification})")
        else:
            # 如果已存在，更新描述和归类
            updated = False
            if obj.description != desc:
                obj.description = desc
                updated = True
            if obj.classification != classification:
                obj.classification = classification
                updated = True
            
            if updated:
                obj.save()
                # print(f"   . [更新] {name}")

    # 2. 初始化应用场景 (ApplicationScenario)
    # 格式: (名称, 要求描述)
    scenarios = [
        ('汽车内饰', '低气味、低VOC、耐刮擦、抗紫外线、哑光美观'),
        ('汽车外饰', '耐候性、高抗冲、喷涂性好、尺寸稳定'),
        ('汽车引擎盖下', '耐高温、耐油、耐化学品、高强度、抗振动'),
        ('新能源电池包', 'V-0阻燃、高CTI、耐高压、尺寸稳定、耐老化'),
        ('充电桩', '耐候阻燃、耐低温冲击、电绝缘性、耐UV'),
        ('消费电子', '薄壁成型、高流动、外观绚丽、环保阻燃、高模量'),
        ('智能穿戴', '亲肤、耐汗液、抗过敏、轻量化、耐脏污'),
        ('医疗器械', '生物相容性、耐辐射/高温灭菌、耐化学品、透明'),
        ('光伏储能', '耐户外老化(f1)、RTI高、耐低温冲击、耐酸碱'),
        ('高铁航空', '轻量化、高强度、阻燃烟毒低(EN45545)、耐疲劳'),
        ('智能家居', '食品接触级(FDA)、抗菌、美观、高光泽'),
        ('工业连接器', '高流动、耐插拔、耐高温焊接(SMT)、高绝缘'),
        ('电动工具', '高强度、耐跌落、耐油污、减震吸能'),
        ('LED照明', '高反射率、导热、耐黄变、遮光'),
        ('5G通讯', '低介电常数(Dk)、低介电损耗(Df)、尺寸精密'),
        ('运动器材', '高回弹、耐低温、耐冲击、轻量化'),
    ]

    print(f"\n🔹 正在初始化 {len(scenarios)} 种应用场景...")
    for name, req in scenarios:
        obj, created = ApplicationScenario.objects.get_or_create(
            name=name,
            defaults={'requirements': req}
        )
        if created:
            print(f"   + [新增] {name}")
        else:
            if obj.requirements != req:
                obj.requirements = req
                obj.save()

    print("\n✅ 初始化完成！")


if __name__ == '__main__':
    run()