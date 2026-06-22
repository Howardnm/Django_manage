/**
 * 生产工单创建页 —— BOM 配料表动态计算
 * 依赖: #bom-data (json_script), .planned-qty, #total-planned-qty,
 *       #id_quantity_planned, #feeding-total-foot, .feeding-row 等
 */
document.addEventListener('DOMContentLoaded', function () {
    var bomDataEl = document.getElementById('bom-data');
    if (!bomDataEl) return;

    var bomData = JSON.parse(bomDataEl.textContent);
    var qtyInputs = document.querySelectorAll('.planned-qty');
    var totalDisplay = document.getElementById('total-planned-qty');
    var totalField = document.getElementById('id_quantity_planned');
    var feedingTotalFoot = document.getElementById('feeding-total-foot');

    function recalcFeeding() {
        var grandTotal = 0;
        var formulaQtys = {};

        qtyInputs.forEach(function (input) {
            var pk = input.getAttribute('data-formula-pk');
            var qty = parseFloat(input.value) || 0;
            formulaQtys[pk] = qty;
            grandTotal += qty;
        });

        totalDisplay.textContent = grandTotal.toFixed(1);
        totalField.value = grandTotal.toFixed(1);

        // 计算每行每列的配料量
        var formulaColumnTotals = {};
        bomData.formulas.forEach(function (f) {
            formulaColumnTotals[f.pk] = 0;
        });
        var grandFeedingTotal = 0;

        document.querySelectorAll('.feeding-row').forEach(function (row) {
            var rowIdx = parseInt(row.getAttribute('data-row'));
            var rowData = bomData.rows[rowIdx];
            var rowSum = 0;

            // 每个配方版本的配料量
            row.querySelectorAll('.feeding-qty-cell').forEach(function (cell) {
                var formulaPk = cell.getAttribute('data-formula-pk');
                var pct = parseFloat(rowData.percentages[formulaPk]) || 0;
                var qty = formulaQtys[formulaPk] || 0;
                var val = qty * pct / 100;
                cell.textContent = val > 0 ? val.toFixed(3) : '-';
                rowSum += val;
                formulaColumnTotals[formulaPk] += val;
            });

            // 行合计
            var rowTotalEl = row.querySelector('.feeding-row-total');
            if (rowTotalEl) {
                rowTotalEl.textContent = rowSum > 0 ? rowSum.toFixed(3) : '-';
            }
            grandFeedingTotal += rowSum;
        });

        // 列合计
        bomData.formulas.forEach(function (f) {
            var el = document.querySelector('.feeding-formula-total[data-formula-pk="' + f.pk + '"]');
            if (el) {
                el.textContent = formulaColumnTotals[f.pk] > 0 ? formulaColumnTotals[f.pk].toFixed(3) : '0';
            }
        });
        document.getElementById('feeding-grand-total').textContent = grandFeedingTotal > 0 ? grandFeedingTotal.toFixed(3) : '0';

        if (grandFeedingTotal > 0) {
            feedingTotalFoot.style.display = '';
        } else {
            feedingTotalFoot.style.display = 'none';
        }
    }

    qtyInputs.forEach(function (input) {
        input.addEventListener('input', recalcFeeding);
    });

    recalcFeeding();
});
