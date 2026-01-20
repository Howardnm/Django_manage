import os
import django
import sys

# 初始化 Django 环境
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Django_manage.settings')
django.setup()

from app_repository.models import OEM


def run():
    print("🚀 开始初始化主机厂 (OEM) 数据 (全球改性塑料行业下游)...")

    # 定义主机厂数据
    # 格式: (名称, 简称, 描述)
    # 涵盖：汽车、电子电气、家电、新能源、医疗等主要改性塑料应用领域
    oem_data = [
        # --- 1. 汽车主机厂 (Automotive OEMs) ---
        # 欧美系
        ('Tesla Motors', '特斯拉', '全球新能源汽车领导者，对轻量化、阻燃材料要求极高。'),
        ('Volkswagen Group', '大众', '大众集团，包括大众、奥迪、保时捷等，标准体系严谨 (VW 50180等)。'),
        ('General Motors', '通用', '通用汽车，包括别克、雪佛兰、凯迪拉克，GMW标准体系。'),
        ('Ford Motor Company', '福特', '福特汽车，WSS标准体系。'),
        ('BMW Group', '宝马', '宝马集团，对内饰气味、环保材料有高标准。'),
        ('Mercedes-Benz Group', '奔驰', '梅赛德斯-奔驰，豪华车标杆，对表面处理和质感要求高。'),
        ('Stellantis N.V.', '斯特兰蒂斯', '包括标致、雪铁龙、Jeep、菲亚特等。'),
        
        # 日韩系
        ('Toyota Motor Corporation', '丰田', '丰田汽车，TSM标准，强调成本与性能平衡，供应链稳定。'),
        ('Honda Motor Co., Ltd.', '本田', '本田汽车，HES标准。'),
        ('Nissan Motor Co., Ltd.', '日产', '日产汽车，NES标准。'),
        ('Hyundai Motor Group', '现代起亚', '现代起亚集团，MS标准。'),

        # 国内自主品牌 & 新势力
        ('BYD Auto', '比亚迪', '新能源龙头，垂直整合能力强，电池包材料需求大。'),
        ('Geely Auto Group', '吉利', '吉利汽车，包括吉利、领克、极氪，沃尔沃技术协同。'),
        ('Great Wall Motor', '长城', '长城汽车，哈弗、坦克、欧拉，SUV市场为主。'),
        ('Changan Automobile', '长安', '长安汽车，研发实力强。'),
        ('Chery Automobile', '奇瑞', '奇瑞汽车，出口量大。'),
        ('SAIC Motor', '上汽', '上汽集团，包括荣威、名爵、智己。'),
        ('GAC Group', '广汽', '广汽集团，传祺、埃安。'),
        ('NIO Inc.', '蔚来', '高端纯电，对免喷涂、环保材料有创新需求。'),
        ('Li Auto', '理想', '增程/纯电，家庭用车定位。'),
        ('XPeng Motors', '小鹏', '智能化标签。'),
        ('Xiaomi Auto', '小米', '生态链整合，对消费电子级外观要求高。'),
        ('Leapmotor', '零跑', '全域自研，性价比高。'),
        ('Seres', '赛力斯', '华为智选车合作伙伴 (问界)。'),

        # --- 2. 电子电气/通讯 (E&E / Telecom) ---
        ('Apple Inc.', '苹果', '消费电子风向标，对外观、环保(无卤)、再生材料要求极严。'),
        ('Huawei Technologies', '华为', '通讯基站、手机、智选车，对5G材料、散热材料需求大。'),
        ('Samsung Electronics', '三星', '手机、家电、半导体。'),
        ('Dell Technologies', '戴尔', 'PC/服务器，大量使用PCR回收材料。'),
        ('HP Inc.', '惠普', '打印机/PC，环保材料先行者。'),
        ('Lenovo Group', '联想', 'PC全球第一。'),
        ('Sony Group', '索尼', '游戏机、视听设备，阻燃材料需求大。'),
        ('ZTE Corporation', '中兴', '通讯设备。'),
        ('Foxconn (Hon Hai)', '富士康', '全球最大代工厂，连接器/结构件用量巨大。'),
        ('Luxshare Precision', '立讯精密', '连接器龙头，Apple核心供应商。'),
        ('Amphenol Corporation', '安费诺', '全球连接器巨头。'),
        ('TE Connectivity', '泰科', '连接器/传感器，汽车/工业应用为主。'),
        ('Molex', '莫仕', '连接器巨头。'),
        ('DJI', '大疆', '无人机全球霸主，对轻量化、高强度材料有特殊需求。'),

        # --- 3. 家电 (Home Appliances) ---
        ('Midea Group', '美的', '白电、小家电，对PP、ABS、AS用量极大。'),
        ('Haier Group', '海尔', '海尔智家，冰洗空，全球化布局。'),
        ('Gree Electric', '格力', '格力电器，空调为主，自建模具/注塑能力强。'),
        ('Hisense Group', '海信', '电视、白电。'),
        ('TCL Technology', 'TCL', '电视、面板。'),
        ('Dyson', '戴森', '吸尘器/吹风机，对高光泽、耐摔、耐热材料有特殊要求。'),
        ('Panasonic', '松下', '综合家电。'),
        ('Whirlpool', '惠而浦', '欧美白电巨头。'),
        ('Ecovacs Robotics', '科沃斯', '扫地机器人，对耐磨、防静电材料有需求。'),
        ('Roborock', '石头科技', '扫地机器人。'),
        ('Joyoung', '九阳', '小家电，豆浆机/破壁机，食品接触级材料。'),
        ('Supor', '苏泊尔', '炊具/小家电，SEB集团旗下。'),

        # --- 4. 新能源/储能/光伏 (New Energy / PV) ---
        ('CATL', '宁德时代', '动力电池全球第一，电池包支架/端板/绝缘件。'),
        ('Sungrow Power', '阳光电源', '光伏逆变器，耐候/阻燃材料。'),
        ('Enphase Energy', 'Enphase', '微型逆变器。'),
        ('Ginlong (Solis)', '锦浪', '逆变器。'),
        ('GoodWe', '固德威', '逆变器。'),
        ('Pylontech', '派能', '户用储能。'),
        ('Trina Solar', '天合光能', '光伏组件，接线盒材料。'),
        ('Longi Green Energy', '隆基', '光伏组件。'),

        # --- 5. 电动工具/园林工具 (Power Tools) ---
        ('TTI Group', '创科实业', 'Milwaukee, Ryobi，全球电动工具巨头，对尼龙增强材料需求大。'),
        ('Stanley Black & Decker', '史丹利百得', 'DeWalt，电动工具。'),
        ('Bosch Power Tools', '博世', '博世电动工具。'),
        ('Makita', '牧田', '牧田电动工具。'),
        ('Chervon', '泉峰', 'EGO，高端园林工具。'),
        ('Globe Tools', '格力博', 'Greenworks，园林工具。'),

        # --- 6. 医疗器械 (Medical) ---
        ('Mindray', '迈瑞', '监护仪/超声，对耐化学品(消毒液)材料要求高。'),
        ('Philips Healthcare', '飞利浦医疗', '医疗设备。'),
        ('GE Healthcare', 'GE医疗', '医疗设备。'),
        ('Siemens Healthineers', '西门子医疗', '医疗设备。'),
        ('Yuwell', '鱼跃', '家用医疗器械。'),
    ]

    print(f"\n🔹 正在初始化 {len(oem_data)} 家主机厂 (OEM)...")
    
    count_created = 0
    count_updated = 0

    for name, short_name, description in oem_data:
        obj, created = OEM.objects.get_or_create(
            name=name,
            defaults={
                'short_name': short_name,
                'description': description
            }
        )
        
        if created:
            print(f"   + [新增] {short_name} ({name})")
            count_created += 1
        else:
            # 检查并更新
            updated = False
            if obj.short_name != short_name:
                obj.short_name = short_name
                updated = True
            if obj.description != description:
                obj.description = description
                updated = True
            
            if updated:
                obj.save()
                # print(f"   . [更新] {short_name}")
                count_updated += 1

    print(f"\n✅ 初始化完成！新增: {count_created}, 更新: {count_updated}")


if __name__ == '__main__':
    run()