"""
手工 smoke test: ZRFC_GET_MBEWH 历史价格查询。

⚠️ 这是一个**会被 Django 测试发现机制 import** 的模块（文件名以 test 开头），
   所以它必须能在 import 期无副作用地跑完 —— 不要在这里做写库、不要用
   unittest 的断言。运行方式:

       python -m app_sap_services.test2        # 或直接跑本文件

   它连接真实 SAP，用于核对接口字段语义。CI 环境无 SAP 时应跳过。
"""

import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Django_manage.settings')
django.setup()

from app_sap_services import sap
from app_sap_services.definitions.bom import MaterialBomMaintain

msgs = sap.rfc(MaterialBomMaintain).filter(
    i_type="M",
    t_main=[{
        "MATNR": "A02006000027",   # 物料编号
        "WERKS": "3011",   # 工厂
        "STLAN": "1",   # BOM 用途
        "STLAL": "05",   # 可选的 BOM
        "BMENG": "1000",   # 基准数量(BTCI)
        "STLST": "1",
        "POSNR": "0010",   # BOM 项目号
        "POSTP": "L",   # 项目类别（物料单）
        "IDNRK": "A01005000044",   # 带有转换MATN2的组件(BTCI)
        "MENGE": "88.800",   # 组件数量 (BTCI)
        "MEINS": "G",   # 组件计量单位
        "AUSCH": "1",
        "DATUV": "2026-10-26",
    }],
).call()
for msg in msgs:
    print(msg.TYPE, msg.MESSAGE)
