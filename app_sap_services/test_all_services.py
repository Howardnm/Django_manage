"""
SAP 服务模块 —— 全函数连通性测试脚本。

逐个调用每个域服务的每个 RFC 方法，验证函数是否可连通。
测试策略: 使用最小参数的模糊查询，确保即使无数据也能验证 RFC 调用通路。

用法:
    python manage.py shell < app_sap_services/test_all_services.py

    # Django shell 中
    python manage.py shell
    #>>> exec(open('app_sap_services/test_all_services.py').read())

    # PyCharm 中直接运行此文件即可（自动定位项目根目录）
"""

import os
import sys
import time
from pathlib import Path
from typing import Callable, List, Dict, Any

# ---- 自动定位项目根目录 ----
# 向上查找包含 manage.py 的目录，解决 PyCharm/终端/CI 中 CWD 不同的问题
_script_dir = Path(__file__).resolve().parent
for _p in [_script_dir, *_script_dir.parents]:
    if (_p / 'manage.py').exists():
        _project_root = str(_p)
        break
else:
    _project_root = str(_script_dir.parent)

if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# ---- Django 初始化 ----
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Django_manage.settings')

import django
django.setup()

from app_sap_services import (
    sap_material,
    sap_customer,
    sap_sales,
    sap_price,
    sap_delivery,
    sap_production,
    sap_vendor,
    sap_wms,
    sap_quota,
    sap_health_check,
)


# ======================================================================
# 测试结果收集
# ======================================================================

class TestReport:
    """测试报告收集器"""

    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        self.start_time = time.time()

    def add(self, service: str, function: str, rfc: str,
            passed: bool, duration: float, detail: str = ''):
        self.results.append({
            'service': service,
            'function': function,
            'rfc': rfc,
            'passed': passed,
            'duration': duration,
            'detail': detail,
        })

    def summary(self):
        total = len(self.results)
        passed = sum(1 for r in self.results if r['passed'])
        failed = total - passed
        elapsed = time.time() - self.start_time

        print('\n' + '=' * 80)
        print(f'  测试汇总: {total} 个函数, {passed} 通过, {failed} 失败, 耗时 {elapsed:.1f}s')
        print('=' * 80)

        if failed:
            print('\n  失败列表:')
            for r in self.results:
                if not r['passed']:
                    print(f'    ✗ [{r["service"]}] {r["function"]} ({r["rfc"]})')
                    if r['detail']:
                        print(f'      → {r["detail"]}')

        print()


report = TestReport()


# ======================================================================
# 测试辅助函数
# ======================================================================

def run_test(service_name: str, func_name: str, rfc_name: str,
             func: Callable, *args, **kwargs):
    """
    执行单个 RFC 函数测试。

    - 连接成功但无数据 → 算通过（RFC 通路正常）
    - 连接成功有数据   → 算通过，记录条数
    - 权限/函数不存在  → 算失败
    - 连接超时         → 算失败
    """
    print(f'  ▶ [{service_name}] {func_name} (RFC: {rfc_name}) ...', end=' ', flush=True)
    t0 = time.time()
    try:
        result = func(*args, **kwargs)
        elapsed = time.time() - t0

        if isinstance(result, list):
            count = len(result)
            detail = f'返回 {count} 条记录'
            print(f'✓ 通过 ({elapsed:.1f}s, {count} 条)')
        elif isinstance(result, dict):
            # 统计字典中的表记录数
            table_counts = {
                k: len(v) for k, v in result.items()
                if isinstance(v, list)
            }
            if table_counts:
                detail = f'返回表: {table_counts}'
            else:
                detail = '返回 dict (非表结构)'
            print(f'✓ 通过 ({elapsed:.1f}s, {detail})')
        else:
            detail = f'返回类型: {type(result).__name__}'
            print(f'✓ 通过 ({elapsed:.1f}s)')

        report.add(service_name, func_name, rfc_name, True, elapsed, detail)

    except Exception as e:
        elapsed = time.time() - t0
        msg = str(e)[:200]
        # 判断失败原因类型
        if 'RFC_ERROR' in str(type(e).__name__).upper() or 'RFCError' in str(type(e)):
            detail = f'RFC 错误: {msg}'
            print(f'✗ RFC 错误 ({elapsed:.1f}s)')
        elif 'CONNECTION' in str(type(e).__name__).upper():
            detail = f'连接错误: {msg}'
            print(f'✗ 连接错误 ({elapsed:.1f}s)')
        elif 'AUTHORITY' in msg.upper() or 'AUTH' in msg.upper():
            detail = f'权限不足: {msg}'
            print(f'✗ 权限不足 ({elapsed:.1f}s)')
        elif 'NOT_FOUND' in msg.upper() or 'not found' in msg.lower():
            detail = f'函数不存在: {msg}'
            print(f'✗ 函数不存在 ({elapsed:.1f}s)')
        else:
            detail = f'{type(e).__name__}: {msg}'
            print(f'✗ 失败 ({elapsed:.1f}s)')

        report.add(service_name, func_name, rfc_name, False, elapsed, detail)


# ======================================================================
# 测试入口
# ======================================================================

def main():
    print('=' * 80)
    print('  SAP 服务模块 —— 全函数连通性测试')
    print('=' * 80)

    # ---- 0. 健康检查 ----
    print('\n[0] 连接健康检查')
    health = sap_health_check()
    if health.get('status') != 'healthy':
        print(f'  ✗ SAP 连接不可用: {health}')
        print('\n请检查 SAP 服务是否正常运行后重试。')
        return
    print(f'  ✓ 连接正常: ashost={health.get("ashost")}, client={health.get("client")}')

    # ---- 1. 物料服务 ----
    print('\n[1] MaterialService — 物料主数据')
    run_test('Material', 'query_materials', 'ZRFC_MATERIAL_MESN',
             sap_material.query_materials, mat_nr='A01*', max_results=3)
    run_test('Material', 'check_material', 'ZFG_CHECK_MATERIAL',
             sap_material.check_material, '000000000000000000')
    run_test('Material', 'query_materials_advanced', 'ZRFC_MATERIAL_MESN',
             sap_material.query_materials_advanced,
             mat_filters=[{'SIGN': 'I', 'OPTION': 'CP', 'LOW': 'A01*', 'HIGH': ''}])

    # ---- 2. 客户服务 ----
    print('\n[2] CustomerService — 客户主数据')
    run_test('Customer', 'get_customer', 'ZRFC_GET_CUSTOMER',
             sap_customer.get_customer, partner='00001*')
    run_test('Customer', 'get_customer_material', 'ZRFC_GET_KNMT',
             sap_customer.get_customer_material, customer_nr='00001*', max_results=3)
    # modify_customer 是写入操作，仅做连通性测试（不传数据，预期报参数错误但不影响连通性验证）
    print('  ▶ [Customer] modify_customer (RFC: ZRFC_MODIFY_CUSTOMER) ... ⊘ 跳过 (写入操作)')

    # ---- 3. 销售服务 ----
    print('\n[3] SalesService — 销售订单')
    run_test('Sales', 'get_price_list', 'ZRFC_GET_SALES_PRICE_LIST',
             sap_sales.get_price_list, material_nr='A01*')
    run_test('Sales', 'get_sale_orders', 'ZRFC_GET_SALE_ORDERS',
             sap_sales.get_sale_orders, material_nr='A01*')
    print('  ▶ [Sales] create_sale_orders (RFC: ZRFC_CREATE_SALE_ORDERS) ... ⊘ 跳过 (写入操作)')

    # ---- 4. 价格服务 ----
    print('\n[4] PriceService — 价格查询')
    run_test('Price', 'get_material_valuation', 'ZRFC_GET_MBEW',
             sap_price.get_material_valuation, 'A01001000003')
    run_test('Price', 'get_last_invoice_price', 'ZRFC_GET_LAST_INVOICE_PRICE',
             sap_price.get_last_invoice_price, 'A01001000003')

    # ---- 5. 交货单服务 ----
    print('\n[5] DeliveryService — 交货单')
    print('  ▶ [Delivery] create_delivery (RFC: ZRFC_CREATE_OUTB_DELIVERY) ... ⊘ 跳过 (写入操作)')
    print('  ▶ [Delivery] update_delivery (RFC: ZRFC_UPDATE_OUTB_DELIVERY) ... ⊘ 跳过 (写入操作)')

    # ---- 6. 生产服务 ----
    print('\n[6] ProductionService — 生产工单/计件工资')
    run_test('Production', 'get_open_production_orders', 'ZIF_MES_GET_OPEN_PROD',
             sap_production.get_open_production_orders, plant='1010')
    run_test('Production', 'get_machine_describe', 'ZIF_MES_GET_MACHINE_DESCRIBE',
             sap_production.get_machine_describe, plant='1010')
    run_test('Production', 'get_order_data', 'ZIF_JJGZ_GET_ORDER_DATA',
             sap_production.get_order_data)
    print('  ▶ [Production] create_production_confirmation ... ⊘ 跳过 (写入操作)')
    print('  ▶ [Production] cancel_production_confirmation ... ⊘ 跳过 (写入操作)')

    # ---- 7. 供应商服务 ----
    print('\n[7] VendorService — 供应商校验')
    run_test('Vendor', 'check_vendor', 'ZFG_CHECK_VENDOR',
             sap_vendor.check_vendor, '0000000000')

    # ---- 8. WMS 服务 ----
    print('\n[8] WMSService — 领料数据')
    run_test('WMS', 'get_material_order_issue_data', 'ZRFC_GET_MAT_ORDER_ISSUE_DATA',
             sap_wms.get_material_order_issue_data, 'A01001000003', plant='1010')

    # ---- 9. 配额服务 ----
    print('\n[9] QuotaService — 配额协议')
    print('  ▶ [Quota] create_quota (RFC: ZRFC_QUOTA_CREATE) ... ⊘ 跳过 (写入操作)')
    print('  ▶ [Quota] copy_condition (RFC: ZRFC_RV_CONDITION_COPY) ... ⊘ 跳过 (写入操作)')

    # ---- 汇总 ----
    report.summary()


if __name__ == '__main__':
    main()
