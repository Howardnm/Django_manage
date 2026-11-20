/* color_bom.js — 色粉配比BOM页面脚本 */

var BOM_TS_API_URL = window.MATERIAL_API_URL || '';

function initColorBom() {
    /* 初始化远程搜索控件 — 复用通用函数 tomselect_remote.js（base.html 已加载） */
    initRemoteTomSelectAll(document, {apiUrl: BOM_TS_API_URL});

    /* 本地搜索已由 base.html 的 initLocalTomSelectAll 建好，这里一并绑 */
    if (window.bindFormulaTableDropdowns) {
        bindFormulaTableDropdowns(document);
    }

    /* 原材料选择后自动更新原材料类型列和库存 */
    attachCategoryUpdate();
    bindRawMaterialStockAll(document);

    /* ---- Formset 动态新增行 ---- */
    var addBtn = document.getElementById('add-entry-row');
    if (addBtn) {
        var totalForms = document.getElementById('id_entries-TOTAL_FORMS');
        var container = document.getElementById('entries-formset');
        var templateEl = document.getElementById('entries-empty-form');
        if (totalForms && container && templateEl) {
            var template = templateEl.innerHTML;

            addBtn.addEventListener('click', function() {
                var count = parseInt(totalForms.value);
                var newRow = template.replace(/__prefix__/g, count);
                container.insertAdjacentHTML('beforeend', newRow);
                totalForms.value = count + 1;

                var newRowEl = container.lastElementChild;
                initRemoteTomSelectAll(newRowEl, {apiUrl: BOM_TS_API_URL});
                if (window.bindFormulaTableDropdowns) {
                    bindFormulaTableDropdowns(newRowEl);
                }
                attachCategoryUpdate();
                bindRawMaterialStockAll(newRowEl);
            });
        }
    }
}

/* 监听 raw_material 的 TomSelect 变化，更新原材料类型列 */
function attachCategoryUpdate() {
    document.querySelectorAll('select[data-model="raw_material"]').forEach(function(el) {
        if (!el.tomselect) return;
        // 移除旧监听，避免重复绑定
        el.tomselect.off('item_add', el._catHandler);
        el._catHandler = function(value, item) {
            var row = el.closest('tr');
            if (!row) return;
            // 原材料类型在第3列（第1列是隐藏的 id input，第2列是喂料口）
            var catCell = row.querySelector('td:nth-child(3)');
            if (!catCell) return;
            var data = el.tomselect.options[value];
            if (data && data.category_name) {
                catCell.innerHTML = '<span class="badge bg-blue-lt">' + escapeHtml(data.category_name) + '</span>';
            } else {
                catCell.innerHTML = '<span class="text-muted">-</span>';
            }
        };
        el.tomselect.on('item_add', el._catHandler);
    });
}

function bomStockMap() {
    if (!window.BOM_STOCK) {
        var node = document.getElementById('bom-stock-map');
        window.BOM_STOCK = node ? JSON.parse(node.textContent) : {};
    }
    return window.BOM_STOCK;
}

function bindRawMaterialStockAll(root) {
    root.querySelectorAll('select[data-model="raw_material"]').forEach(bindRawMaterialStock);
}

function bindRawMaterialStock(el) {
    if (!el.tomselect || el._stockBound) return;
    el._stockBound = true;
    var ts = el.tomselect;

    function show(qty) {
        var row = el.closest('tr');
        var cell = row && row.querySelector('.bom-stock');
        if (!cell) return;
        cell.textContent = (qty === null || qty === undefined) ? '-' : String(qty);
    }

    function lookup(id, data) {
        if (data && Object.prototype.hasOwnProperty.call(data, 'stock_qty')) return data.stock_qty;
        var map = bomStockMap();
        var key = String(id);
        if (Object.prototype.hasOwnProperty.call(map, key)) return map[key];
        return undefined;
    }

    function apply(id) {
        var data = id ? ts.options[String(id)] : null;
        var qty = lookup(id, data);
        if (qty === undefined) return;
        show(qty);
    }

    // 已在下拉里的物料，addOption 不会覆盖，搜索结果里的 stock_qty 要补回去。
    ts.on('load', function (results) {
        (results || []).forEach(function (opt) {
            if (!opt || !Object.prototype.hasOwnProperty.call(opt, 'stock_qty')) return;
            var key = String(opt.value);
            bomStockMap()[key] = opt.stock_qty;
            if (ts.options[key]) ts.options[key].stock_qty = opt.stock_qty;
        });
        if (ts.items.length) apply(ts.items[0]);
    });
    ts.on('item_add', function (value) {
        apply(value);
    });
    ts.on('item_remove', function () {
        var current = ts;
        setTimeout(function () {
            if (!current.items.length) show(null);
        }, 0);
    });
    if (el.value) apply(el.value);
}

function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/* 脚本在 extra_js 块加载时 DOM 已就绪，直接执行；否则等待事件。
   本地 TomSelect 在 base.html 的 DOMContentLoaded 里创建，且注册更早。
   若本脚本赶在那之前执行，等 DOMContentLoaded 再绑一次分秤/喂料口。 */
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initColorBom);
} else {
    initColorBom();
    if (document.readyState === 'interactive' && window.bindFormulaTableDropdowns) {
        document.addEventListener('DOMContentLoaded', function () {
            bindFormulaTableDropdowns(document);
        });
    }
}

/* ---- 删除行（事件委托，来自 _color_bom_form.html） ---- */
document.addEventListener('click', function(e) {
    var btn = e.target.closest('.delete-row-btn');
    if (!btn) return;
    var row = btn.closest('tr');
    var checkbox = row.querySelector('input[type=checkbox][name$="-DELETE"]');
    if (checkbox) checkbox.checked = true;
    row.style.display = 'none';
});

/* ---- 对比表 sticky 列（来自 _color_bom_compare.html） ---- */
(function() {
    var table = document.querySelector('.compare-table');
    if (!table) return;
    var STICKY_COLS = 3;
    function fixSticky() {
        var headerCells = table.querySelectorAll('thead > tr:first-child > th');
        var offsets = [];
        var cum = 0;
        headerCells.forEach(function(th, i) {
            if (i < STICKY_COLS) {
                offsets[i] = cum;
                cum += th.offsetWidth;
            }
        });
        table.querySelectorAll('tr').forEach(function(row) {
            var cells = row.children;
            var isThead = row.parentElement.tagName === 'THEAD';
            for (var i = 0; i < Math.min(STICKY_COLS, cells.length); i++) {
                var cell = cells[i];
                var isPreSticky = cell.classList.contains('sticky-col');
                if (cell.colSpan > 1 && !isPreSticky) continue;
                cell.classList.add('sticky-col');
                cell.style.left = isPreSticky ? (cell.style.left || offsets[0] + 'px') : offsets[i] + 'px';
                if (!/bg-/.test(cell.className) && !cell.style.backgroundColor) {
                    cell.style.backgroundColor = isThead ? '#f8f9fa' : '#fff';
                }
            }
        });
    }
    fixSticky();
    window.addEventListener('resize', fixSticky);
    new ResizeObserver(fixSticky).observe(table);
})();
