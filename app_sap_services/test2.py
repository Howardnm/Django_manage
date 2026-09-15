import os, django

from app_sap_services import sap
from app_sap_services.definitions import MaterialStockQuery, MaterialQuery, MaterialPriceQuery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Django_manage.settings')
django.setup()

result = sap.rfc(MaterialPriceQuery) \
    .filter(p_lfgja="2026", p_lfmon="09") \
    .call()

for row in result:
    if row.MATNR == "A01005000057":
        unit_price = row.VERPR / row.PEINH if row.PEINH else None
        print(f"{row.MATNR}: {unit_price} CNY/kg")
