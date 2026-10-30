import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Django_manage.settings')
django.setup()
import polars as pl
# 全局展开所有行和列
pl.Config.set_tbl_rows(-1)        # -1 表示显示所有行（无限制）
pl.Config.set_tbl_cols(-1)        # -1 表示显示所有列（无限制）
pl.Config.set_tbl_width_chars(-1) # 取消总字符宽度限制（避免列因为终端过窄被截断）

from decimal import Decimal
from app_sap_services import sap
from app_sap_services.definitions.bom import MaterialBomQuery

rows = sap.rfc(MaterialBomQuery).filter(
    i_matnr="A02006000098",
    i_werks="3011",
    i_stalt="01",
    i_datuv="20261030",
).collect()

print(rows)
