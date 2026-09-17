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

from app_sap_services import sap  # noqa: E402
from app_sap_services.definitions import MaterialPriceQuery  # noqa: E402


TARGET_MATNR = "A01005000057"


def main():
    rows = sap.rfc(MaterialPriceQuery).filter(s_matnr__eq=TARGET_MATNR).call()

    if not rows:
        print(f"{TARGET_MATNR}: 无数据")
        return

    print(f"\n{TARGET_MATNR} 共 {len(rows)} 个期间")
    periods = sorted((r.BDATJ, r.POPER) for r in rows)
    print(f"期间跨度: {periods[0][0]}-{periods[0][1]:02d} → "
          f"{periods[-1][0]}-{periods[-1][1]:02d}")
    print(f"工厂: {sorted({r.BWKEY for r in rows})}")
    print(f"币种: {sorted({r.WAERS for r in rows})}")
    print(f"VPRSV: {sorted({r.VPRSV for r in rows})}")

    print(f"\n{'期间':<10} {'工厂':<6} {'VPRSV':<6} {'PEINH':>7} "
          f"{'VERPR':>12} {'单价(元/kg)':>12}")
    for r in sorted(rows, key=lambda x: (x.BDATJ, x.POPER)):
        unit_price = r.VERPR / r.PEINH if r.PEINH else None
        print(f"{r.BDATJ}-{r.POPER:02d}   {r.BWKEY:<6} {r.VPRSV:<6} {r.PEINH:>7} "
              f"{r.VERPR:>12} {unit_price if unit_price is not None else '-':>12}")


if __name__ == "__main__":
    main()
