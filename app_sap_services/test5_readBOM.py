import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Django_manage.settings')
django.setup()

from decimal import Decimal
from app_sap_services import sap
from app_sap_services.definitions.bom import MaterialBomQuery

rows = sap.rfc(MaterialBomQuery).filter(
    i_matnr="A02006000098",
    i_werks="3011",
    i_stalt="01",
    i_datuv="20261026",
).call()
for row in rows:
    print(row.STLAL, row.POSNR, row.IDNRK, row.MENGE, row.MEINS)
