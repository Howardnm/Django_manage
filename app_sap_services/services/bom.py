"""
SAP BOM 写入。

新建和修改都是整表提交。I_TYPE='M' 时，没传的行 SAP 会不会删，这里不知道，
所以不先读、不合并，客户端给什么行就传什么行。
维护日期是 10 位字符串，不改写成读取接口的 8 位 YYYYMMDD。
"""

from app_sap_services import sap
from app_sap_services.definitions.bom import MaterialBomDelete, MaterialBomMaintain
from app_sap_services.schemas.messages import FATAL_TYPES, normalize_type


# 行上允许出现的字段。抬头四个由参数写入，行内同名值作废。
_LINE_FIELDS = {
    "BMENG", "POSNR", "POSTP", "IDNRK", "MENGE", "MEINS", "POTX1",
    "EWAHR", "STKTX", "ZTEXT", "STLST", "AUSCH", "DATUV",
}
_LINE_ALIASES = {name.lower(): name for name in _LINE_FIELDS}


class BomMaintainError(Exception):
    """维护接口返回了 E/A。messages 是全部 T_MSG，不只有失败的那几条。"""

    def __init__(self, messages: list[dict]):
        self.messages = messages
        fatal = next((m for m in messages if m.get("type") in FATAL_TYPES), None)
        text = (fatal or {}).get("text") or "SAP 拒绝了这次维护"
        super().__init__(text)


def create_bom(*, matnr: str, werks: str, stlan: str, stlal: str, lines: list[dict]) -> list[dict]:
    """新建。I_TYPE='N'。"""
    return _maintain("N", matnr=matnr, werks=werks, stlan=stlan, stlal=stlal, lines=lines)


def update_bom(*, matnr: str, werks: str, stlan: str, stlal: str, lines: list[dict]) -> list[dict]:
    """修改。I_TYPE='M'。不回读现有组件。"""
    return _maintain("M", matnr=matnr, werks=werks, stlan=stlan, stlal=stlal, lines=lines)


def delete_bom(*, matnr: str, werks: str, stlan: str, stlal: str) -> dict:
    """
    删除一张 BOM。

    没有返回表，必须走 call_structured，否则成功文案会被丢掉。
    E/A 由 schema 抛 SAPBusinessError。
    """
    try:
        result = sap.call_structured(
            MaterialBomDelete,
            i_matnr=matnr,
            i_werks=werks,
            i_stlan=stlan,
            i_stalt=stlal,
        )
    finally:
        # 同一条连接再去展开，会继续退回删掉之前的那张。
        sap.close()
    return {
        "rtype": result.get("E_RTYPE") or "",
        "rtmsg": result.get("E_RTMSG") or "",
    }


def _maintain(i_type: str, *, matnr: str, werks: str, stlan: str, stlal: str, lines: list[dict]) -> list[dict]:
    t_main = [
        _t_main_row(matnr, werks, stlan, stlal, line)
        for line in lines
    ]
    try:
        msgs = sap.rfc(MaterialBomMaintain).filter(i_type=i_type, t_main=t_main).call()
        parsed = [_message(row) for row in msgs]
        if any(row["type"] in FATAL_TYPES for row in parsed):
            raise BomMaintainError(parsed)
        return parsed
    finally:
        # 写入走的是 BDC。这条连接接着展开时，函数组仍退回写入前的备选。
        sap.close()


def _t_main_row(matnr: str, werks: str, stlan: str, stlal: str, line: dict) -> dict:
    """只放有值的列。

    空串也会进 BDC。组件一填，屏幕先带出基本单位；空的项目文本、使用可能性
    把光标带跑后，传入的 MEINS 盖不上去，CS03 里单位就停在 KG。
    和能在 CS03 查到 G 的调用一样：没填的列不出现在行里。
    """
    row = {}
    for key, value in line.items():
        sap_name = _LINE_ALIASES.get(key, key if key in _LINE_FIELDS else None)
        if sap_name is None or value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        row[sap_name] = text
    row["MATNR"] = matnr
    row["WERKS"] = werks
    row["STLAN"] = stlan
    row["STLAL"] = stlal
    return row


def _message(row) -> dict:
    number = row.NUMBER
    line_no = row.ROW
    return {
        "type": normalize_type(row.TYPE),
        "id": row.ID or "",
        "number": number,
        "text": row.MESSAGE or "",
        "row": line_no,
        "field": row.FIELD or None,
    }
