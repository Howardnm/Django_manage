import os
import django
import sys

# 初始化 Django 环境
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Django_manage.settings')
django.setup()

from app_raw_material.models import RawMaterialType


def run():
    print("🚀 开始初始化原材料类型数据 (改性塑料行业标准 - 增强版)...")

    # 定义原材料类型数据
    # 格式: (名称, 代码, 排序权重, 描述)
    # 排序逻辑：树脂 -> 弹性体 -> 填充 -> 阻燃 -> 助剂 -> 颜料 -> 其他
    raw_material_types = [
        # --- 1. 基础树脂 (Base Resins) ---
        ('通用塑料树脂', 'RESIN_COMMODITY', 10, '包括PP, PE, PVC, PS, ABS等大宗塑料，用量大，成本低。'),
        ('工程塑料树脂', 'RESIN_ENG', 20, '包括PA, PC, PBT, POM, PPO等，具有优异的机械性能和耐热性。'),
        ('特种工程树脂', 'RESIN_SPECIAL', 30, '包括PEEK, PPS, LCP, PI等，耐高温、耐腐蚀，用于高端领域。'),
        ('生物降解树脂', 'RESIN_BIO', 40, '包括PLA, PBAT, PBS等，可堆肥降解，环保方向。'),
        ('氟塑料树脂', 'RESIN_FLUORO', 50, '包括PTFE, PVDF, FEP等，极佳的耐化学品性和耐候性。'),

        # --- 2. 弹性体/增韧剂 (Elastomers / Impact Modifiers) ---
        ('热塑性弹性体', 'ELASTOMER', 100, '包括TPE, TPU, TPV等，兼具橡胶弹性和塑料加工性。'),
        ('增韧剂', 'IMPACT_MOD', 110, '包括POE, EPDM, MBS, 丙烯酸酯类，用于提高材料的抗冲击强度。'),
        ('硅橡胶/硅胶', 'SILICONE', 120, '用于改善手感、耐高低温或作为超韧改性剂。'),

        # --- 3. 填充与增强 (Fillers & Reinforcements) ---
        ('玻璃纤维', 'GF', 200, '包括短玻纤(SGF)和长玻纤(LGF)，最常用的增强材料，大幅提高强度和模量。'),
        ('碳纤维', 'CF', 210, '高强度、高模量、轻量化，用于高端结构件和导电材料。'),
        ('天然纤维', 'NATURAL_FIBER', 215, '包括麻纤维, 竹纤维, 木粉等，用于WPC木塑复合材料，环保低碳。'),
        ('矿物填充', 'MINERAL', 220, '包括滑石粉, 碳酸钙, 云母, 硅灰石等，用于增刚、降低成本或改善尺寸稳定性。'),
        ('功能性填料', 'FILLER_FUNC', 230, '包括导热粉(氧化铝/氮化硼)、硫酸钡(高光/加重)、玻璃微珠(减重)等。'),
        ('金属粉末/纤维', 'METAL_FILLER', 240, '包括不锈钢纤维, 铜粉等，主要用于EMI电磁屏蔽或加重手感。'),
        ('纳米材料', 'NANO', 250, '包括纳米粘土, 石墨烯, 碳纳米管(CNT)，用于阻隔、导电或增强。'),

        # --- 4. 阻燃剂 (Flame Retardants) ---
        ('卤素阻燃剂', 'FR_HALOGEN', 300, '包括溴系(十溴二苯乙烷等)和氯系，阻燃效率高，但环保压力大。'),
        ('无卤阻燃剂', 'FR_HALOGEN_FREE', 310, '包括磷系(OP), 氮系(MCA), 金属氢氧化物(Mg/Al)，环保趋势首选。'),
        ('阻燃协效剂', 'FR_SYNERGIST', 320, '包括三氧化二锑(Sb2O3), 抑烟剂, 防滴落剂(PTFE)等，配合主阻燃剂使用。'),

        # --- 5. 功能助剂 (Additives) ---
        ('抗氧剂/光稳定剂', 'STABILIZER', 400, '包括主抗氧剂(1010), 辅抗氧剂(168), UV吸收剂, HALS，防止材料老化降解。'),
        ('润滑剂/脱模剂', 'LUBRICANT', 410, '包括硅油, 蜡(PE蜡/EBS), 硬脂酸盐，改善加工流动性和脱模性。'),
        ('分散剂', 'DISPERSANT', 415, '包括EBS, 特殊聚合物蜡，帮助颜料或高填充填料均匀分散。'),
        ('偶联剂/相容剂', 'COUPLING', 420, '包括硅烷, 钛酸酯, 马来酸酐接枝物(MAH)，改善树脂与填料/玻纤的界面结合。'),
        ('增塑剂', 'PLASTICIZER', 425, '包括邻苯类, 柠檬酸酯类，用于降低硬度，提高柔韧性(PVC, PLA, PA)。'),
        ('成核剂', 'NUCLEATING', 430, '包括增透成核剂(Millad), 增刚成核剂，加快结晶速度，提高透明度或刚性。'),
        ('抗静电/导电剂', 'ESD', 440, '包括炭黑, 碳纳米管, 永久抗静电剂，降低表面电阻，防止静电积聚。'),
        ('耐磨/耐刮擦剂', 'WEAR_RESIST', 445, '包括硅酮母粒, 二硫化钼(MoS2), PTFE微粉，降低摩擦系数，提高耐刮擦性。'),
        ('抗菌剂', 'ANTI_BACTERIAL', 450, '包括银离子, 锌离子等无机抗菌剂，用于医疗、家电等领域。'),
        ('镭雕助剂', 'LASER', 455, '激光打标粉，帮助材料吸收激光能量，形成清晰标记。'),
        ('扩链剂', 'CHAIN_EXTENDER', 460, '用于修复回收料或缩聚树脂(PBT, PET, PA)的分子链，恢复粘度。'),
        ('抗水解剂', 'ANTI_HYDROLYSIS', 465, '碳化二亚胺类，防止聚酯/聚氨酯在湿热环境下水解失效。'),
        ('除味剂/吸附剂', 'ODOR_SCAVENGER', 470, '包括沸石, 多孔材料，吸附小分子VOC，用于低气味汽车料。'),
        ('发泡剂', 'BLOWING', 475, '包括化学发泡剂(AC), 物理发泡微球，用于减重或消除缩痕。'),
        ('荧光增白剂', 'BRIGHTENER', 480, '如OB-1, KS等，吸收紫外光发射蓝紫光，显著提高白度。'),
        ('加工助剂', 'PPA', 485, '氟聚合物PPA，用于消除薄膜或挤出时的熔体破裂(鲨鱼皮)，降低模口积料。'),

        # --- 6. 颜料/色母 (Colorants) ---
        ('颜料/染料', 'PIGMENT', 500, '包括钛白粉, 炭黑, 有机颜料, 溶剂染料等粉体着色剂。'),
        ('色母粒', 'MASTERBATCH', 510, '预分散的高浓度颜料颗粒，使用方便，无粉尘污染。'),
        ('特殊效果颜料', 'EFFECT_PIGMENT', 520, '包括珠光粉, 金属粉, 荧光粉，赋予材料特殊的光学外观。'),

        # --- 7. 其他 (Others) ---
        ('回收料/副牌', 'RECYCLED', 900, '包括回收造粒料, 破碎料, 水口料，用于降低成本。'),
        ('其他辅料', 'OTHER', 999, '未归类的其他原材料。'),
    ]

    print(f"\n🔹 正在初始化 {len(raw_material_types)} 种原材料类型...")
    
    count_created = 0
    count_updated = 0

    for name, code, order, description in raw_material_types:
        obj, created = RawMaterialType.objects.get_or_create(
            name=name,
            defaults={
                'code': code,
                'order': order,
                'description': description
            }
        )
        
        if created:
            print(f"   + [新增] {name} (Code: {code})")
            count_created += 1
        else:
            # 检查并更新
            updated = False
            if obj.code != code:
                obj.code = code
                updated = True
            if obj.order != order:
                obj.order = order
                updated = True
            if obj.description != description:
                obj.description = description
                updated = True
            
            if updated:
                obj.save()
                # print(f"   . [更新] {name}")
                count_updated += 1

    print(f"\n✅ 初始化完成！新增: {count_created}, 更新: {count_updated}")


if __name__ == '__main__':
    run()