import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Django_manage.settings')
django.setup()

from app_sap_services import sap
from app_sap_services.definitions.bom import MaterialBomDelete

result = sap.call_structured(
    MaterialBomDelete,
    i_matnr="A02006000027",
    i_werks="3011",
    i_stlan="1",
    i_stalt="05",
)
print(result["E_RTYPE"], result["E_RTMSG"])
