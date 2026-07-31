import os, django

from app_sap_services import sap
from app_sap_services.definitions import MaterialStockQuery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Django_manage.settings')
django.setup()

result = sap.rfc(MaterialStockQuery) \
    .collect()

print(result)