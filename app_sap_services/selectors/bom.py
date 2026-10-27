"""
SAP BOM 只读查询。

列表走 MAST 关系链，详情走 BOM 展开。两个函数都不补工厂、不补备选。
"""

from datetime import date
from decimal import Decimal

from app_sap_services import sap
from app_sap_services.definitions.bom import MaterialBomLinkQuery, MaterialBomQuery


def list_bom_links(*, matnr: str, werks: str) -> list[dict]:
    """
    某物料在某工厂挂了哪些 BOM。

    「查询不到相关数据」是空列表，不是错误。其它 E/A 仍抛 SAPBusinessError。
    """
    rows = sap.call(
        MaterialBomLinkQuery,
        s_matnr__eq=matnr,
        s_werks__eq=werks,
    )
    return [_link_row(row) for row in rows]


def get_bom(
    *,
    matnr: str,
    werks: str,
    stlan: str,
    stlal: str,
    datuv: date,
    emeng: Decimal | None = None,
) -> dict | None:
    """
    展开一张 BOM 的组件行。

    读取函数没有用途入参，不存在的备选又会静默退回另一张。
    所以这里按返回行的 STLAN、STLAL 再滤一次，对不上就当没有。
    同一条 RFC 连接会把这个展开留在函数组里。页面一直复用连接，
    新建后仍退回旧备选；新进程立刻能读到。对不上就关掉再查一次。
    同一项目号的替代组保留多行，不合并。
    """
    rows = _query(matnr=matnr, werks=werks, stlal=stlal, datuv=datuv, emeng=emeng)
    matched = _match(rows, stlan, stlal)
    if not matched:
        sap.close()
        rows = _query(matnr=matnr, werks=werks, stlal=stlal, datuv=datuv, emeng=emeng)
        matched = _match(rows, stlan, stlal)
    if not matched:
        return None

    return {
        "matnr": matnr,
        "werks": werks,
        "stlan": stlan,
        "stlal": stlal,
        "datuv": datuv.isoformat(),
        "emeng": None if emeng is None else format(emeng, "f"),
        "stlnr": matched[0].STLNR,
        "items": [_item_row(row) for row in matched],
    }


def _query(*, matnr: str, werks: str, stlal: str, datuv: date, emeng: Decimal | None):
    params = {
        "i_matnr": matnr,
        "i_werks": werks,
        "i_stalt": stlal,
        "i_datuv": datuv.strftime("%Y%m%d"),
    }
    if emeng is not None:
        params["i_emeng"] = emeng
    return sap.call(MaterialBomQuery, **params)


def _match(rows, stlan: str, stlal: str) -> list:
    return [
        row for row in rows
        if _same(row.STLAL, stlal) and _same(row.STLAN, stlan)
    ]


def _same(raw, expected: str) -> bool:
    return (raw or "").strip() == expected.strip()


def _iso(value):
    if value is None:
        return None
    return value.isoformat()


def _link_row(row) -> dict:
    return {
        "matnr": row.MATNR,
        "werks": row.WERKS,
        "stlan": row.STLAN,
        "stlnr": row.STLNR,
        "stlal": row.STLAL,
        "losvn": row.LOSVN,
        "losbs": row.LOSBS,
        "andat": _iso(row.ANDAT),
        "annam": row.ANNAM,
        "aedat": _iso(row.AEDAT),
        "aenam": row.AENAM,
        "cslty": row.CSLTY,
    }


def _item_row(row) -> dict:
    return {
        "stlnr": row.STLNR,
        "stlan": row.STLAN,
        "stlal": row.STLAL,
        "werks": row.WERKS,
        "posnr": row.POSNR,
        "postp": row.POSTP,
        "idnrk": row.IDNRK,
        "menge": row.MENGE,
        "meins": row.MEINS,
        "ausch": row.AUSCH,
        "potx1": row.POTX1,
        "ewahr": row.EWAHR,
        "alpgr": row.ALPGR,
        "datuv": _iso(row.DATUV),
    }
