import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Django_manage.settings')
django.setup()


from app_sap_services import sap
from app_sap_services.definitions.bom import MaterialBomLinkQuery

rows = sap.rfc(MaterialBomLinkQuery).filter(
    s_matnr__eq="A02006000027",
    s_werks__eq="3011",
).collect()

print(rows)
# print("物料编号", "工厂", "BOM用途", "物料单", "可选的BOM", "从批量", "到批量", "日期记录创建于", "创建记录的用户", "最后更改日期", "更改对象用户的名称", "标志: 配置物料(物料变式)")
# for row in rows:
#     print(row.MATNR, row.WERKS, row.STLAN, row.STLNR, row.STLAL, row.LOSVN, row.LOSBS, row.ANDAT, row.ANNAM, row.AEDAT, row.AENAM, row.CSLTY)