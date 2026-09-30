"""产品报价需求单打印渲染器（OA 核价申请单打印版）。"""

from common_utils.printing.base import BasePrintRenderer

from ..services import QuotationService


class QuotationPrintRenderer(BasePrintRenderer):
    template_name = 'apps/app_quotation/print.html'

    def __init__(self, quotation, **kwargs):
        super().__init__(**kwargs)
        self.quotation = quotation

    def get_context_data(self, **kwargs):
        request = self.quotation
        boms = list(request.boms.select_related('formula')
                    .prefetch_related('formula__bom_lines__raw_material'))
        cost_map = QuotationService.bom_cost_map(request)
        material_prices = list(request.material_prices.select_related('raw_material'))
        return {
            'quotation': request,
            'bom_rows': [{'bom': b, 'cost': cost_map.get(b.pk)} for b in boms],
            'material_prices': material_prices,
            'info_sections': request.get_info_sections(),
        }
