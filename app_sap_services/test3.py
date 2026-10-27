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
        "MATNR": "A02006000027",
        "WERKS": "3011",
        "STLAN": "1",
        "STLAL": "05",
        "BMENG": "1000",
        "STLST": "1",
        "POSNR": "0010",
        "POSTP": "L",
        "IDNRK": "A01005000044",
        "MENGE": "88.800",
        "MEINS": "G",
        "AUSCH": "1",
        "DATUV": "2026-10-26",
    },{
        "MATNR": "A02006000027",
        "WERKS": "3011",
        "STLAN": "1",
        "STLAL": "05",
        "BMENG": "1000",
        "STLST": "1",
        "POSNR": "0020",
        "POSTP": "L",
        "IDNRK": "A01005000039",
        "MENGE": "55.800",
        "MEINS": "G",
        "AUSCH": "1",
        "DATUV": "2026-10-26",
    },{
        "MATNR": "A02006000027",
        "WERKS": "3011",
        "STLAN": "1",
        "STLAL": "05",
        "BMENG": "1000",
        "STLST": "1",
        "POSNR": "0030",
        "POSTP": "L",
        "IDNRK": "A01005000039",
        "MENGE": "40.800",
        "MEINS": "G",
        "AUSCH": "1",
        "DATUV": "2026-10-26",
    }],
).call()
for msg in msgs:
    print(msg.TYPE, msg.MESSAGE)
