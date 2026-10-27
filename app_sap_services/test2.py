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

from decimal import Decimal
from app_sap_services import sap
from app_sap_services.definitions.bom import MaterialBomQuery

rows = sap.rfc(MaterialBomQuery).filter(
    i_matnr="A02006000027",
    i_werks="3011",
    i_stalt="03",
    i_datuv="2026-10-20",
    i_emeng=Decimal("1000"),
).call()
for row in rows:
    print(row.STLAL, row.POSNR, row.IDNRK, row.MENGE, row.MEINS, row.BAUSF, row.MNGLG, row.MNGKO)
