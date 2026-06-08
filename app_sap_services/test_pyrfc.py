import os

# 【极其重要】必须在 import pyrfc 之前执行这句！
# 请把下面的路径替换为你实际存放 nwrfcsdk\lib 的完整路径
# 注意路径前面的 r 不要丢掉（代表原生字符串，防止斜杠转义）

# 这里的路径请一定要替换成你电脑上真实的 nwrfcsdk\lib 的绝对路径！
sap_lib_path = r"D:\SAP_SDK\win-nwrfc750P_6-70002755\nwrfcsdk\lib"

# 1. 解决 Python 3.8+ 找不到主 DLL 的问题
os.add_dll_directory(sap_lib_path)

# 2. 【新增这行】解决 SAP 内部找不到 ICU (多语言) 依赖包的问题
os.environ['PATH'] = sap_lib_path + os.pathsep + os.environ.get('PATH', '')

# 然后再去导入 pyrfc
from pyrfc import Connection, RFCError

# 1. 配置 SAP 连接参数 (请替换为真实数据)
sap_config = {
    'ashost': '192.168.103.181',  # 替换: SAP服务器IP
    'sysnr': '00',  # 替换: 系统编号
    'client': '400',  # 替换: 客户端号
    'user': 'RFC07',  # 替换: SAP账号
    'passwd': 'Saite@2026',  # 替换: 密码
    'lang': 'ZH'              # 可选: 语言(中文)
}


def fetch_specific_materials():
    try:
        conn = Connection(**sap_config)
        print(">>> 1. SAP 系统连接成功！开始拉取数据...")

        # 2. 核心调整：精准过滤条件
        # 我们用 MAT_RANGE 使用 'CP' (包含模式)，类似 SQL 的 LIKE 'A01001*'
        mat_range = [{
            'SIGN': 'I',
            'OPTION': 'CP',  # CP 代表 Contains Pattern (支持通配符)
            'LOW': 'A01001*',  # 抓取 A01001 开头的所有物料
            'HIGH': ''
        }]

        # 限制物料类型为 ROH (原材料)
        mta_range = [{
            'SIGN': 'I',
            'OPTION': 'EQ',
            'MTART_LOW': 'ROH',  # 注意这个字段名是 MTART_LOW
            'MTART_HIGH': ''
        }]

        # （注意：我故意注释掉了 DAT_RANGE 和 WEK_RANGE，
        # 这样就不会因为日期或工厂不对而导致查不到这几条数据）

        print(">>> 2. 正在向 SAP 发送查询请求 (模糊查询 A01001* )...")
        result = conn.call(
            'ZRFC_MATERIAL_MESN',
            MAT_RANGE=mat_range,  # 传人物料编号条件
            MTA_RANGE=mta_range  # 传入物料类型条件
        )

        # 3. 解析返回结果 ZMARC
        materials = result.get('ZMARC', [])
        print(f">>> 3. 查询成功！共拉取到 {len(materials)} 条符合条件的数据。\n")

        # 4. 完美对齐打印格式 (模仿你发来的 SAP 表格)
        print(f"{'物料编号':<15} | {'物料描述':<20} | {'类型'} | {'物料组'} | {'单位'} | {'标准/旧料号':<12} | {'图号':<10} | {'工厂'}")
        print("-" * 105)

        for mat in materials:
            mat_id = mat.get('MATNR', '')
            mat_desc = mat.get('MAKTX', '')
            mat_type = mat.get('MTART', '')
            mat_group = mat.get('MATKL', '')
            unit = mat.get('MEINS', '')
            normt = mat.get('NORMT', '')  # 91.01.00029
            fig_no = mat.get('ZZFIGURE_NO', '')  # 0630027
            plant = mat.get('WERKS', '')

            # 清理物料号前导零 (如果 SAP 传过来的是 0000000A01001000003，把它变成 A01...)
            clean_mat_id = mat_id.lstrip('0') if mat_id else mat_id

            # 截断超长描述以保持表格整齐
            short_desc = (mat_desc[:18] + '..') if len(mat_desc) > 18 else mat_desc

            print(f"{clean_mat_id:<18} | {short_desc:<20} | {mat_type:<4} | {mat_group:<6} | {unit:<4} | {normt:<14} | {fig_no:<10} | {plant}")

        print("-" * 105)
        conn.close()

    except RFCError as e:
        print("\n❌ SAP 调用失败：", e)
    except Exception as e:
        print("\n❌ 发生其他错误：", e)


if __name__ == '__main__':
    fetch_specific_materials()