/**
 * 完成注塑任务 — 模具×配方矩阵交互
 *
 * DOM 依赖：
 *   table#specimen-matrix        — 矩阵表格
 *   input.specimen-qty           — 每单元格产出数量
 *
 * 功能：
 *   - 每行实时计算产量合计（所有 .specimen-qty 之和）
 *   - 动态追加"合计"列到表头和每行末尾
 */
document.addEventListener('DOMContentLoaded', function () {
    var matrix = document.getElementById('specimen-matrix');
    if (!matrix) return;

    /**
     * 更新指定行的合计值
     */
    function updateRowTotal(row, totalCell) {
        var total = 0;
        var qtyInputs = row.querySelectorAll('.specimen-qty');
        for (var i = 0; i < qtyInputs.length; i++) {
            total += parseInt(qtyInputs[i].value) || 0;
        }
        totalCell.textContent = total || '0';
    }

    // 为表头追加"合计"列
    var headerRows = matrix.querySelectorAll('thead tr');
    for (var h = 0; h < headerRows.length; h++) {
        var th = document.createElement('th');
        if (h === 0) {
            th.textContent = '合计';
            th.style.width = '60px';
        }
        headerRows[h].appendChild(th);
    }

    // 为每行追加合计单元格并绑定事件
    var rows = matrix.querySelectorAll('tbody tr.specimen-matrix-row');
    for (var r = 0; r < rows.length; r++) {
        var row = rows[r];
        var totalCell = document.createElement('td');
        totalCell.className = 'text-center fw-bold row-total-cell';
        totalCell.style.minWidth = '50px';
        row.appendChild(totalCell);

        updateRowTotal(row, totalCell);

        // 行内 qty 输入变化时重新计算合计
        row.addEventListener('input', function (e) {
            if (e.target.classList.contains('specimen-qty')) {
                var tr = e.target.closest('tr');
                var tc = tr.querySelector('.row-total-cell');
                if (tc) updateRowTotal(tr, tc);
            }
        });
    }
});
