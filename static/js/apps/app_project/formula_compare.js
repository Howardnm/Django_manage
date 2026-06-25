/* ==========================================
   配方对比表吸顶列 — app_project/detail/_formula_compare_panel.html
   依赖: 无
   ========================================== */

document.addEventListener("DOMContentLoaded", function () {
    const table = document.querySelector('.compare-table');
    if (!table) return;

    const STICKY_COLS = 4;

    function fixSticky() {
        const headerCells = table.querySelectorAll('thead > tr:first-child > th');
        const offsets = [];
        let cum = 0;
        headerCells.forEach(function (th, i) {
            if (i < STICKY_COLS) {
                offsets[i] = cum;
                cum += th.offsetWidth;
            }
        });
        table.querySelectorAll('tr').forEach(function (row) {
            var cells = row.children;
            var isThead = row.parentElement.tagName === 'THEAD';
            for (var i = 0; i < Math.min(STICKY_COLS, cells.length); i++) {
                var cell = cells[i];
                var isPreSticky = cell.classList.contains('sticky-col');
                if (cell.colSpan > 1 && !isPreSticky) continue;
                cell.classList.add('sticky-col');
                cell.style.left = isPreSticky ? cell.style.left || offsets[0] + 'px' : offsets[i] + 'px';
                if (!/bg-/.test(cell.className) && !cell.style.backgroundColor) {
                    cell.style.backgroundColor = isThead ? '#f8f9fa' : '#fff';
                }
            }
        });
    }

    fixSticky();
    window.addEventListener('resize', fixSticky);
    new ResizeObserver(fixSticky).observe(table);
});
