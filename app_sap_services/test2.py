import os, django

from app_sap_services import sap
from app_sap_services.definitions import MaterialStockQuery, MaterialQuery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Django_manage.settings')
django.setup()

result = sap.rfc(MaterialQuery) \
    .filter(mat_range__cp="100*") \
    .limit(50) \
    .collect()

print(result)