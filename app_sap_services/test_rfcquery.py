"""RfcQuery 全方法可用性测试 — 带结果输出"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Django_manage.settings')
django.setup()

import polars as pl
from app_sap_services import sap, DoesNotExist, MultipleObjectsReturned, SAPFilterError
from app_sap_services.definitions.material import MaterialQuery

B = '\033[1m'
G = '\033[32m'
R = '\033[31m'
Y = '\033[33m'
N = '\033[0m'
OK = f'{G}OK{N}'
NG = f'{R}NG{N}'

q = sap.rfc(MaterialQuery).filter(mta_range__eq='ROH')
failed = 0; passed = 0

def check(desc, actual, expected=None, validator=None):
    global passed, failed
    if validator:
        ok = validator(actual)
    elif expected is not None:
        ok = actual == expected
    else:
        ok = bool(actual)
    ok_str = OK if ok else NG
    actual_str = str(actual)[:120]
    print(f'  {ok_str} {desc}')
    print(f'       {Y}result{N}: {actual_str}')
    if not ok:
        failed += 1
        if expected is not None:
            print(f'       {R}expected{N}: {expected}')
    else:
        passed += 1

print(f'{B}============================================================{N}')
print(f'{B}RfcQuery 全方法可用性测试 (MaterialQuery / MTART=ROH){N}')
print(f'{B}============================================================{N}')

# ====================================================================
# 1. filter
# ====================================================================
print(f'\n{B}--- 1. filter ---{N}')
r = q.clone().filter(mat_range__cp='A01*').limit(5).call()
check('filter(mat_range__cp="A01*") 返回 5 条', len(r), 5)
check('  首条 MATNR 以 A01 开头', r[0].MATNR.startswith('A01'), True)

r = q.clone().filter(mat_range__eq='A01001000101').call()
check('filter(mat_range__eq) 精确匹配 = 1 条', len(r), 1)
check('  MATNR = A01001000101', r[0].MATNR == 'A01001000101', True)

# ====================================================================
# 2. exclude
# ====================================================================
print(f'\n{B}--- 2. exclude ---{N}')
r = sap.rfc(MaterialQuery).filter(mta_range__eq='ROH').exclude(mat_range__cp='A01*').limit(5).call()
check('exclude A01* 后首条不以 A01 开头', r[0].MATNR.startswith('A01'), False)
check(f'  首条 MATNR={r[0].MATNR}', True, True)

try:
    q.clone().exclude(bad__eq='X').call()
    check('exclude 无效参数应抛异常', False, True)
except SAPFilterError:
    check('exclude 无效参数 -> SAPFilterError', True, True)

# ====================================================================
# 3. order_by
# ====================================================================
print(f'\n{B}--- 3. order_by ---{N}')
r = q.clone().order_by('MATNR').limit(10).call()
check(f'order_by MATNR 升序: 首={r[0].MATNR} <= 尾={r[-1].MATNR}', r[0].MATNR <= r[-1].MATNR, True)

r = q.clone().order_by('-MATNR').limit(10).call()
check(f'order_by -MATNR 降序: 首={r[0].MATNR} >= 尾={r[-1].MATNR}', r[0].MATNR >= r[-1].MATNR, True)

r = q.clone().order_by('MTART', '-MATNR').limit(10).call()
check(f'order_by 多字段: 10 条, 首条 MATNR={r[0].MATNR}', len(r), 10)

# ====================================================================
# 4. limit
# ====================================================================
print(f'\n{B}--- 4. limit ---{N}')
check('limit(5)', len(q.clone().limit(5).call()), 5)
check('limit(0)', len(q.clone().limit(0).call()), 0)
check('limit(None) 取消 = 全量', len(q.clone().limit(None).call()), 16883)

# ====================================================================
# 5. offset
# ====================================================================
print(f'\n{B}--- 5. offset ---{N}')
r1 = q.clone().order_by('MATNR').limit(3).call()
r2 = q.clone().order_by('MATNR').offset(1).limit(3).call()
check(f'offset(1): 跳过 {r1[0].MATNR}, 新首={r2[0].MATNR}', r1[1].MATNR == r2[0].MATNR, True)

r = q.clone().order_by('MATNR').offset(-5).limit(3).call()
check(f'offset(-5) -> 自动截断为0, 3 条', len(r), 3)

r = q.clone().order_by('MATNR').offset(20000).call()
check('offset(20000) 超总量 -> 空', len(r), 0)

# ====================================================================
# 6. select
# ====================================================================
print(f'\n{B}--- 6. select ---{N}')
r = q.clone().select('MATNR', 'MAKTX').limit(3).call()
check('select MATNR,MAKTX: 字段集合正确', set(r[0]._data.keys()), {'MATNR', 'MAKTX'})
check(f'  值: MATNR={r[0].MATNR}, MAKTX={r[0].MAKTX[:30]}...', True, True)

# ====================================================================
# 7. group_by
# ====================================================================
print(f'\n{B}--- 7. group_by ---{N}')
g = q.clone().limit(100).group_by('MTART').call()
check(f'group_by MTART: {len(g)} 组, key={list(g.keys())}', isinstance(g, dict) and ('ROH',) in g, True)
check(f'  ROH 组有 {len(g[("ROH",)])} 条', len(g[('ROH',)]) >= 1, True)

g = q.clone().limit(100).group_by('MTART', 'WERKS').call()
check(f'group_by MTART+WERKS: {len(g)} 组', isinstance(g, dict) and len(g) > 0, True)

# ====================================================================
# 8. agg
# ====================================================================
print(f'\n{B}--- 8. agg ---{N}')
r = q.clone().group_by('MTART').agg(count='count').call()
check(f'agg count: {r}', len(r) == 1 and r[0]['count'] == 16883, True)

r = q.clone().group_by('MTART').agg(count='cnt').call()
check(f'agg 自定义列名 cnt: {r}', r[0]['cnt'] == 16883, True)

r = q.clone().limit(10).agg(count='count').call()
check('agg 无 group_by -> []', r, [])

# ====================================================================
# 9. having
# ====================================================================
print(f'\n{B}--- 9. having ---{N}')
r = q.clone().group_by('MTART').agg(count='count').having(count__gt=5000).call()
check(f'having count__gt=5000 -> {len(r)} 组', len(r), 1)

r = q.clone().group_by('MTART').agg(count='count').having(count__gt=20000).call()
check('having count__gt=20000 -> []', len(r), 0)

r = q.clone().group_by('MTART').agg(count='count').having(count__ge=16883, count__le=16883).call()
check(f'having ge+le -> {len(r)} 组', len(r), 1)

# ====================================================================
# 10. call
# ====================================================================
print(f'\n{B}--- 10. call ---{N}')
r = q.clone().limit(3).call()
check('call() -> List[OutputRecord]', isinstance(r, list) and len(r) == 3 and hasattr(r[0], 'MATNR'), True)

r = q.clone().group_by('MTART').call()
check('call() + group_by -> Dict', isinstance(r, dict), True)

r = q.clone().group_by('MTART').agg(count='count').call()
check('call() + agg -> List[Dict]', isinstance(r, list) and isinstance(r[0], dict), True)

# ====================================================================
# 11. collect / to_polars
# ====================================================================
print(f'\n{B}--- 11. collect / to_polars ---{N}')
df = q.clone().limit(5).collect()
check(f'collect(): height={df.height}, cols={df.columns}', isinstance(df, pl.DataFrame) and df.height == 5, True)

df = q.clone().limit(5).to_polars()
check(f'to_polars(): height={df.height}', isinstance(df, pl.DataFrame) and df.height == 5, True)

df = q.clone().group_by('MTART').agg(count='count').collect()
check(f'collect() after agg: {df.to_dicts()}', isinstance(df, pl.DataFrame) and df.height == 1, True)

df = q.clone().group_by('MTART').agg(count='count').having(count__gt=0).collect()
check(f'collect() agg+having: height={df.height}', df.height > 0, True)

# ====================================================================
# 12. first / last
# ====================================================================
print(f'\n{B}--- 12. first / last ---{N}')
f = q.clone().first()
check(f'first(): MATNR={f.MATNR}', f is not None, True)

f = q.clone().order_by('MATNR').first()
check(f'first()+order_by: MATNR={f.MATNR}', f is not None, True)

f = q.clone().filter(mat_range__eq='ZZZZ').first()
check('first() 无匹配 -> None', f is None, True)

l = q.clone().order_by('MATNR').limit(100).last()
check(f'last(): MATNR={l.MATNR}', l is not None, True)

l = q.clone().filter(mat_range__eq='ZZZZ').last()
check('last() 无匹配 -> None', l is None, True)

# ====================================================================
# 13. get
# ====================================================================
print(f'\n{B}--- 13. get ---{N}')
m = q.clone().get(mat_range__eq='A01001000101')
check(f'get(): MATNR={m.MATNR}', m.MATNR == 'A01001000101', True)

try:
    q.clone().get(mat_range__eq='ZZZZ')
    check('get 无匹配应抛 DoesNotExist', False, True)
except DoesNotExist:
    check('get 无匹配 -> DoesNotExist', True, True)

try:
    q.clone().get(mat_range__cp='A01*')
    check('get 多条应抛 MultipleObjectsReturned', False, True)
except MultipleObjectsReturned:
    check('get 多条 -> MultipleObjectsReturned', True, True)

# ====================================================================
# 14. count / exists
# ====================================================================
print(f'\n{B}--- 14. count / exists ---{N}')
check('count() 全量', q.clone().count(), 16883)
check('count() + limit(5)', q.clone().limit(5).count(), 5)
check('exists() True', q.clone().filter(mat_range__eq='A01001000101').exists(), True)
check('exists() False', q.clone().filter(mat_range__eq='ZZZZ').exists(), False)
check('count() after agg', q.clone().group_by('MTART').agg(count='count').count(), 1)

# ====================================================================
# 15. all
# ====================================================================
print(f'\n{B}--- 15. all ---{N}')
check('all() = call()', len(q.clone().limit(3).all()) == 3, True)

# ====================================================================
# 16. values
# ====================================================================
print(f'\n{B}--- 16. values ---{N}')
v = q.clone().limit(3).values('MATNR', 'MAKTX')
check(f'values("MATNR","MAKTX"): {v}', len(v) == 3 and isinstance(v[0], dict) and 'MATNR' in v[0], True)

v = q.clone().limit(3).values()
check(f'values() 无参: {len(v)} 行 x {len(v[0])} 字段', len(v) == 3 and len(v[0]) == 12, True)

v = q.clone().filter(mat_range__eq='ZZZZ').values()
check('values() 空结果 -> []', v, [])

# ====================================================================
# 17. values_list
# ====================================================================
print(f'\n{B}--- 17. values_list ---{N}')
vl = q.clone().limit(3).values_list('MATNR', flat=True)
check(f'values_list flat: {vl}', len(vl) == 3 and isinstance(vl[0], str), True)

vl = q.clone().limit(3).values_list('MATNR', 'MAKTX')
check(f'values_list 元组: {vl}', len(vl) == 3 and isinstance(vl[0], tuple), True)

vl = q.clone().filter(mat_range__eq='ZZZZ').values_list('MATNR')
check('values_list 空结果 -> []', vl, [])

# ====================================================================
# 18. iterator
# ====================================================================
print(f'\n{B}--- 18. iterator ---{N}')
chunk = next(q.clone().iterator(100))
check(f'iterator(100): {len(chunk)} 条, 首={chunk[0].MATNR}', len(chunk), 100)

try:
    list(q.clone().iterator(0))
    check('iterator(0) 应抛 ValueError', False, True)
except ValueError:
    check('iterator(0) -> ValueError', True, True)

# ====================================================================
# 19. clone
# ====================================================================
print(f'\n{B}--- 19. clone ---{N}')
base = q.clone().order_by('MATNR')
a = base.clone().filter(mat_range__cp='A01*').limit(3).call()
b = base.clone().filter(mat_range__cp='A03*').limit(3).call()
check(f'clone 独立: A01*首={a[0].MATNR}, A03*首={b[0].MATNR}', a[0].MATNR != b[0].MATNR, True)
check(f'  原 base 未污染: {len(base.call())} 条 (应 > 100)', len(base.call()) > 100, True)

# ====================================================================
# 20. none
# ====================================================================
print(f'\n{B}--- 20. none ---{N}')
nq = sap.rfc(MaterialQuery).filter(mta_range__eq='ROH').none()
check('none().call() = []', nq.call(), [])
check('none().count() = 0', nq.count(), 0)
check('none().exists() = False', nq.exists(), False)
check('none().first() = None', nq.first() is None, True)
check('none().collect().is_empty() = True', nq.collect().is_empty(), True)

# ====================================================================
# 21. explain
# ====================================================================
print(f'\n{B}--- 21. explain ---{N}')
e = q.clone().order_by('MATNR').offset(0).limit(10).explain()
check(f'explain:\n{e}', 'RfcQuery' in e and 'Order by' in e and 'Limit' in e, True)

e = q.clone().none().explain()
check(f'explain EMPTY:\n{e}', 'EMPTY' in e, True)

# ====================================================================
# 22. show
# ====================================================================
print(f'\n{B}--- 22. show ---{N}')
print(f'  {Y}show(3) output:{N}')
q.clone().order_by('MATNR').limit(3).show(3, 'MATNR', 'MAKTX', 'MTART')
check('show(3) 执行无异常', True, True)

print(f'  {Y}show empty output:{N}')
q.clone().filter(mat_range__eq='ZZZZ').show()
check('show empty 执行无异常', True, True)

# ====================================================================
# 23. __repr__
# ====================================================================
print(f'\n{B}--- 23. __repr__ ---{N}')
r = repr(q.clone().order_by('MATNR'))
check(f'__repr__: {r}', 'RfcQuery' in r and 'ZRFC_MATERIAL_MESN' in r, True)

# ====================================================================
# 结果汇总
# ====================================================================
print(f'\n{B}============================================================{N}')
print(f'总计: {G}{passed + failed}{N} 项, {G}{passed} PASS{N}, {R}{failed} FAIL{N}')
print(f'{B}============================================================{N}')
