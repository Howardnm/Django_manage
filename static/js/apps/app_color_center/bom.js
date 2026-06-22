/* color_bom.js — 色粉配比BOM页面脚本 */

/* ---- TomSelect 远程搜索初始化 ---- */
function initRemoteSearch(el) {
    if (!window.TomSelect) return;
    var modelType = el.getAttribute('data-model');
    var materialApiUrl = window.MATERIAL_API_URL || '';
    new TomSelect(el, {
        valueField: 'value',
        labelField: 'text',
        searchField: 'text',
        load: function(query, callback) {
            var url = materialApiUrl + "?model=" + modelType + "&q=" + encodeURIComponent(query);
            fetch(url)
                .then(function(r) { return r.json(); })
                .then(function(json) { callback(json); })
                .catch(function() { callback(); });
        },
        copyClassesToDropdown: false,
        dropdownParent: 'body',
        create: false,
        placeholder: '请输入关键词搜索...',
        preload: 'focus',
        render: {
            option: function(data, escape) { return '<div>' + escape(data.text) + '</div>'; },
            item: function(data, escape) { return '<div>' + escape(data.text) + '</div>'; },
            no_results: function() { return '<div class="no-results p-2 text-muted small">无匹配结果</div>'; },
            loading: function() { return '<div class="spinner-border spinner-border-sm text-muted m-2"></div>'; }
        }
    });
}

function initColorBom() {
    /* 初始化远程搜索控件 */
    document.querySelectorAll('.remote-search').forEach(function(el) {
        initRemoteSearch(el);
    });

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
                newRowEl.querySelectorAll('.remote-search').forEach(function(el) {
                    initRemoteSearch(el);
                });
            });
        }
    }
}

/* 脚本在 extra_js 块加载时 DOM 已就绪，直接执行；否则等待事件 */
if (document.readyState !== 'loading') {
    initColorBom();
} else {
    document.addEventListener('DOMContentLoaded', initColorBom);
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
