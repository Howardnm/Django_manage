/**
 * 注塑模具矩阵 —— 动态行管理
 * 依赖: #mold-matrix-body, #mold-row-template, #mold_count, #add-mold-row
 */
document.addEventListener('DOMContentLoaded', function () {
    var tbody = document.getElementById('mold-matrix-body');
    var template = document.getElementById('mold-row-template');
    var moldCountInput = document.getElementById('mold_count');

    if (!tbody || !template || !moldCountInput) return;

    var tpl = template.innerHTML;

    function updateMoldCount() {
        var rows = tbody.querySelectorAll('.mold-row');
        moldCountInput.value = rows.length;
        rows.forEach(function (row, idx) {
            row.setAttribute('data-row', idx);
            row.querySelectorAll('[name]').forEach(function (el) {
                el.name = el.name.replace(/^(mold|qty)_\d+/, '$1_' + idx);
            });
        });
    }

    document.getElementById('add-mold-row').addEventListener('click', function () {
        var count = tbody.querySelectorAll('.mold-row').length;
        var newRow = tpl.replace(/__ROW_/g, count);
        tbody.insertAdjacentHTML('beforeend', newRow);
        updateMoldCount();
    });

    tbody.addEventListener('click', function (e) {
        var btn = e.target.closest('.remove-mold-row');
        if (!btn) return;
        var row = btn.closest('.mold-row');
        var rows = tbody.querySelectorAll('.mold-row');
        if (rows.length <= 1) return;
        row.remove();
        updateMoldCount();
    });
});
