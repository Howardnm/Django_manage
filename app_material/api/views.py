"""成品 BOM 发布页用的本地接口。

SAP 的列表、明细、删除不经过这里，页面直接打 ``/api/sap/boms/``。

Views:
    FinishedBomAPIView     — 会话登录。未登录 403
    FinishedBomListView    — 左树
    FinishedBomPlantListView — 页头的工厂多选
    FinishedBomPublishView — 新建或整表覆盖
"""

from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from app_formula.models import LabFormula
from app_material.api.exceptions import finished_bom_exception_handler
from app_material.api.serializers import FinishedBomPublishSerializer, FinishedBomQuerySerializer
from app_material.selectors.finished_bom import get_finished_bom_tree, list_active_plants
from app_material.services.finished_bom_publish import publish_finished_bom


class FinishedBomAPIView(APIView):
    """与 SAP BOM 接口相同：只有会话登录，错误体 ``detail/code/messages``。"""

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return finished_bom_exception_handler


class FinishedBomListView(FinishedBomAPIView):
    """``GET /api/material/finished-boms/?sap_code=``。未知编码 404。"""

    def get(self, request):
        query = _valid(FinishedBomQuerySerializer, request.query_params)
        tree = get_finished_bom_tree(query["sap_code"])
        if tree is None:
            raise NotFound("成品不存在")
        return Response(tree)


class FinishedBomPlantListView(FinishedBomAPIView):
    """``GET /api/material/finished-boms/plants/``。"""

    def get(self, request):
        plants = list_active_plants()
        return Response({"count": len(plants), "results": plants})


class FinishedBomPublishView(FinishedBomAPIView):
    """``POST /api/material/finished-boms/publish/``。

    ``mode=create`` 返回 201，``mode=update`` 返回 200。
    修改是整表覆盖，不合并 SAP 里已有、这次没提交的行。
    """

    def post(self, request):
        body = _valid(FinishedBomPublishSerializer, request.data)
        try:
            result = publish_finished_bom(
                formula_id=body["formula_id"],
                werks=body["werks"],
                stlan=body["stlan"],
                stlal=body["stlal"],
                bmeng=body["bmeng"],
                datuv=body["datuv"],
                stlst=body["stlst"],
                stktx=body["stktx"],
                ztext=body["ztext"],
                ausch=body["ausch"],
                merge_color=body["merge_color"],
                mode=body["mode"],
            )
        except LabFormula.DoesNotExist:
            raise NotFound("配方不存在")
        status = 201 if body["mode"] == "create" else 200
        return Response(result, status=status)


def _valid(serializer_class, data):
    serializer = serializer_class(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data
