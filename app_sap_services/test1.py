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
from app_sap_services.definitions.material import MaterialQuery

# 链式调用
result = sap.rfc(MaterialQuery) \
    .filter(mat_range__cp="A01*") \
    .filter(mta_range__eq="ROH") \
    .filter(wek_range__eq="1010") \
    .limit(50) \
    .call()

# 快捷调用
result = sap.call(MaterialQuery, mat_range__cp="A01*", mta_range__eq="ROH")

for row in result:
    print(row.MATNR, row.WERKS, row.MAKTX, row.MTART, row.MATKL)
