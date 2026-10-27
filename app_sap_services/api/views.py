"""
SAP BOM CRUD。

身份是 (matnr, werks, stlan, stlal)，不是本地主键。
没有逐行接口：新建和修改都提交整张组件表。

Views:
    SapBomAPIView      — 会话登录基类。未登录 403，错误体统一为 detail/code/messages
    BomListCreateView  — GET 列表、POST 新建
    BomDetailView      — GET 展开、PUT 修改、DELETE 删除

调用前要有登录会话。浏览器写操作还要带 CSRF（Cookie csrftoken + 头 X-CSRFToken）。
各方法的使用示例写在对应函数上。
"""

from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authentication import SessionAuthentication

from app_sap_services.api.exceptions import sap_bom_exception_handler
from app_sap_services.api.serializers import (
    BomDetailQuerySerializer,
    BomKeySerializer,
    BomListQuerySerializer,
    MaterialNameQuerySerializer,
    BomUpdateSerializer,
    BomWriteSerializer,
)
from app_sap_services.selectors.bom import get_bom, list_bom_links
from app_sap_services.selectors.material import material_names
from app_sap_services.services.bom import create_bom, delete_bom, update_bom


class SapBomAPIView(APIView):
    """BOM 接口基类。

    DRF 默认是 AllowAny，还开着 Basic 认证。这里收成只有会话登录，
    避免未登录或用密码头就能改 SAP。错误不走全局异常处理，只在这个基类上
    收成 ``{"detail", "code", "messages"}``。

    未登录返回 403，code 为 ``not_authenticated``，不是 401。
    SessionAuthentication 不设 WWW-Authenticate，DRF 因此给 403。
    """

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        """只用 BOM 这层的错误体，不改 settings 里的全局 EXCEPTION_HANDLER。"""
        return sap_bom_exception_handler


class MaterialNameView(SapBomAPIView):
    """按物料号取物料描述（MAKTX）。

    路由: ``/api/sap/materials/``
    """

    def get(self, request):
        """给出的每个物料号都返回一行。查不到时 maktx 为空字符串，不是 404。

        使用示例::

            GET /api/sap/materials/?matnr=A01002000009&matnr=A01002000011

            {"results": [
              {"matnr": "A01002000009", "maktx": "ABS 121H"},
              {"matnr": "A01002000011", "maktx": ""}
            ]}
        """
        query = _valid(
            MaterialNameQuerySerializer,
            {"matnr": request.query_params.getlist("matnr")},
        )
        names = material_names(query["matnr"])
        return Response({
            "results": [
                {"matnr": code, "maktx": names.get(code, "")}
                for code in query["matnr"]
            ],
        })


class BomListCreateView(SapBomAPIView):
    """物料在某工厂下的 BOM 列表，以及新建一张 BOM。

    路由: ``/api/sap/boms/``
    """

    def get(self, request):
        """列出物料在该工厂挂了哪些 BOM，不展开组件。

        没有 BOM 是 200 空列表，不是 404。``matnr``、``werks`` 都必填。

        使用示例::

            GET /api/sap/boms/?matnr=A02006000027&werks=3011

            {
              "count": 1,
              "results": [{
                "matnr": "A02006000027",
                "werks": "3011",
                "stlan": "1",
                "stlal": "01",
                "stlnr": "00043885",
                "losvn": 0.0,
                "losbs": 0.0,
                "andat": "2025-10-15",
                "aedat": null
              }]
            }
        """
        query = _valid(BomListQuerySerializer, request.query_params)
        rows = list_bom_links(matnr=query["matnr"], werks=query["werks"])
        return Response({"count": len(rows), "results": rows})

    def post(self, request):
        """新建整张 BOM。成功 201，SAP 回 E/A 则 400，不会只建一半再告诉你。

        每行都是字符串，含数量。``datuv`` 最多 10 位，按原样传给 SAP，
        不要写成读取接口的 8 位 YYYYMMDD。``lines`` 至少一行。

        使用示例::

            POST /api/sap/boms/
            {
              "matnr": "A02006000027",
              "werks": "3011",
              "stlan": "1",
              "stlal": "05",
              "lines": [{
                "posnr": "0010",
                "postp": "L",
                "idnrk": "A01005000044",
                "menge": "649.800",
                "meins": "KG",
                "datuv": "2026-10-16"
              }]
            }
        """
        body = _valid(BomWriteSerializer, request.data)
        messages = create_bom(
            matnr=body["matnr"],
            werks=body["werks"],
            stlan=body["stlan"],
            stlal=body["stlal"],
            lines=body["lines"],
        )
        return Response(_header(body) | {"messages": messages}, status=201)


class BomDetailView(SapBomAPIView):
    """一张 BOM：展开、整表修改、删除。

    路由: ``/api/sap/boms/{matnr}/{werks}/{stlan}/{stlal}/``

    ``stlan`` 是 BOM 用途，``stlal`` 是可选 BOM，两个都要写在路径里。
    修改和删除的抬头只认路径，body 里再写一份也会被忽略。
    """

    def get(self, request, **kwargs):
        """按路径上的用途和备选展开组件。

        ``datuv`` 必填，格式 YYYY-MM-DD，进 SAP 前会转成 YYYYMMDD。
        不传时 SAP 返回 0 行，这里直接 400，避免被看成 404。
        ``emeng`` 可选，不传就不交给 SAP。

        返回行的用途或备选和路径不一致时（SAP 会静默退回另一张）响应 404，
        正文里不带那张退回的 BOM。同一项目号的替代组保留多行。

        使用示例::

            GET /api/sap/boms/A02006000027/3011/1/01/?datuv=2026-10-15&emeng=1

            {
              "matnr": "A02006000027",
              "werks": "3011",
              "stlan": "1",
              "stlal": "01",
              "datuv": "2026-10-15",
              "emeng": "1",
              "stlnr": "00043885",
              "items": [{
                "posnr": "0010",
                "postp": "L",
                "idnrk": "A01005000044",
                "menge": 649.8,
                "meins": "KG",
                "datuv": "2025-09-01"
              }]
            }
        """
        key = _valid(BomKeySerializer, kwargs)
        query = _valid(BomDetailQuerySerializer, request.query_params)
        bom = get_bom(
            matnr=key["matnr"],
            werks=key["werks"],
            stlan=key["stlan"],
            stlal=key["stlal"],
            datuv=query["datuv"],
            emeng=query.get("emeng"),
        )
        if bom is None:
            raise NotFound("BOM 不存在")
        return Response(bom)

    def put(self, request, **kwargs):
        """用 body 里的组件行整表替换这次修改要提交的内容。

        不先读出现有行，也不和 SAP 里已有的行合并。没写进 ``lines`` 的行，
        SAP 会不会删掉还不确定，调用方要自己把想保留的行一并传上。
        成功 200。SAP 回 E/A 是 400，不先查这张 BOM 在不在，所以也不会 404。

        使用示例::

            PUT /api/sap/boms/A02006000027/3011/1/01/
            {"lines": [{
              "posnr": "0010", "postp": "L", "idnrk": "A01005000044",
              "menge": "649.800", "meins": "KG", "datuv": "2026-10-16"
            }]}
        """
        key = _valid(BomKeySerializer, kwargs)
        body = _valid(BomUpdateSerializer, request.data)
        messages = update_bom(
            matnr=key["matnr"],
            werks=key["werks"],
            stlan=key["stlan"],
            stlal=key["stlal"],
            lines=body["lines"],
        )
        return Response(_header(key) | {"messages": messages})

    def delete(self, request, **kwargs):
        """按路径删除这一张 BOM。没有 body。

        成功 200，带 SAP 的 ``rtype`` / ``rtmsg``。
        删不掉是 SAP 业务错误，返回 400，不会因为本地没有记录而 404。

        使用示例::

            DELETE /api/sap/boms/A02006000027/3011/1/01/

            {"matnr": "A02006000027", "werks": "3011",
             "stlan": "1", "stlal": "01", "rtype": "S", "rtmsg": "删除成功"}
        """
        key = _valid(BomKeySerializer, kwargs)
        result = delete_bom(
            matnr=key["matnr"],
            werks=key["werks"],
            stlan=key["stlan"],
            stlal=key["stlal"],
        )
        return Response(_header(key) | result)


def _valid(serializer_cls, data):
    """校验入参。失败抛 DRF ValidationError，由基类收成 400 validation_error。"""
    serializer = serializer_cls(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def _header(data) -> dict:
    """响应里重复一遍 BOM 主键，方便调用方不用再从 URL 里拆。"""
    return {
        "matnr": data["matnr"],
        "werks": data["werks"],
        "stlan": data["stlan"],
        "stlal": data["stlal"],
    }
