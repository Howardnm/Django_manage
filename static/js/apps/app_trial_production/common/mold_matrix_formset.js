/**
 * Mold Matrix Formset — 一套模具矩阵组件，同时服务：
 *   - order/form.html       (ProductionOrder 创建/编辑)
 *   - injection/form.html   (InjectionTask 创建)
 *
 * 自动检测模式：
 *   - Formset 模式：存在 #id_mold-TOTAL_FORMS → 使用 Django __prefix__ 替换
 *   - Legacy  模式：无 management form → 使用 __ROW__ 占位符替换
 *
 * 命名约定：
 *   - 模具选择：  name="mold-{N}" 或 name="mold__ROW_" (Legacy)
 *   - 变体列：    name="variant_qty_{row}_{formulaPk}" 或 name="variant_qty___ROW___{formulaPk}"
 *   - 删除标记：  name="mold-{N}-DELETE" 或 .mold-delete-flag (Legacy)
 */

function initMoldMatrix() {
    var totalForms = document.getElementById('id_mold-TOTAL_FORMS');

    if (totalForms) {
        initFormsetMode(totalForms);
    } else {
        initLegacyMode();
    }
}

/* ============ 穴数（Cavity Count）辅助函数 ============ */

/**
 * 根据行内 mold-select 的选中项，更新该行的穴数显示。
 * @param {HTMLElement} row — .mold-row 元素
 */
function updateCavityCell(row) {
    var select = row.querySelector('.mold-select');
    var cell = row.querySelector('.cavity-cell');
    if (!select || !cell) return;
    var selectedOption = select.options[select.selectedIndex];
    if (selectedOption && selectedOption.dataset.cavity) {
        cell.textContent = selectedOption.dataset.cavity + ' 穴';
    } else {
        cell.textContent = '—';
    }
}

/**
 * 遍历所有行，刷新穴数显示（用于页面初始化）。
 */
function refreshAllCavityCells() {
    var rows = document.querySelectorAll('#mold-matrix-body .mold-row');
    for (var i = 0; i < rows.length; i++) {
        updateCavityCell(rows[i]);
    }
}

/* ============ Formset 模式（Django modelformset_factory） ============ */

function initFormsetMode(totalForms) {
    var tbody = document.getElementById('mold-matrix-body');
    var rowTemplate = document.getElementById('mold-row-template');
    var addBtn = document.getElementById('add-mold-row');
    var matrixCard = document.getElementById('mold-matrix-card');

    if (!tbody || !rowTemplate || !addBtn || !matrixCard) return;

    var formulaPKs = JSON.parse(matrixCard.dataset.formulaPks || '[]');
    var rowHTML = rowTemplate.innerHTML;

    // 穴数初始化：页面加载时为已有行填充穴数
    refreshAllCavityCells();

    // 模具切换时更新穴数（事件委托）
    tbody.addEventListener('change', function (e) {
        if (e.target.classList.contains('mold-select')) {
            var row = e.target.closest('.mold-row');
            if (row) updateCavityCell(row);
        }
    });

    // 新增行按钮
    addBtn.addEventListener('click', function () {
        var idx = parseInt(totalForms.value);
        // __prefix__ (lowercase) = Django empty_form 渲染的占位符
        // __PREFIX__ (uppercase) = 模板中裸 <input> name 的占位符
        var newRowHTML = rowHTML
            .replace(/__prefix__/g, idx)
            .replace(/__PREFIX__/g, idx);
        tbody.insertAdjacentHTML('beforeend', newRowHTML);
        totalForms.value = idx + 1;
    });

    // 删除行（事件委托）
    tbody.addEventListener('click', function (e) {
        var btn = e.target.closest('.delete-mold-row-btn');
        if (!btn) return;
        var row = btn.closest('.mold-row');
        if (!row) return;
        var checkbox = row.querySelector('input[type=checkbox][name$="-DELETE"]');
        if (checkbox) checkbox.checked = true;
        row.style.display = 'none';
    });
}

/* ============ Legacy 模式（injection/form.html，手动 HTML） ============ */

function initLegacyMode() {
    var tbody = document.getElementById('mold-matrix-body');
    var template = document.getElementById('mold-row-template');
    var moldCountInput = document.getElementById('mold_count');
    var addBtn = document.getElementById('add-mold-row');

    if (!tbody || !template || !moldCountInput || !addBtn) return;

    var tpl = template.innerHTML;

    function updateVisibleCount() {
        var visible = tbody.querySelectorAll('.mold-row:not([style*="display: none"])');
        moldCountInput.value = visible.length;
    }

    addBtn.addEventListener('click', function () {
        var totalRows = tbody.querySelectorAll('.mold-row').length;
        var newRow = tpl.replace(/__ROW_/g, totalRows);
        tbody.insertAdjacentHTML('beforeend', newRow);
        updateVisibleCount();
    });

    // 删除行（事件委托）
    tbody.addEventListener('click', function (e) {
        var btn = e.target.closest('.remove-mold-row');
        if (!btn) return;
        var row = btn.closest('.mold-row');
        if (!row) return;
        row.style.display = 'none';

        // 清空表单值（防止提交）
        var moldSelect = row.querySelector('.mold-select');
        if (moldSelect) moldSelect.value = '';
        row.querySelectorAll('.qty-input').forEach(function (input) {
            input.value = '0';
        });
        updateVisibleCount();
    });

    updateVisibleCount();
}

/* ============ 表单提交前同步（防御纵深） ============ */

document.addEventListener('DOMContentLoaded', function () {
    var form = document.getElementById('order-create-form') || document.getElementById('injection-form');
    if (!form) return;
    form.addEventListener('submit', function () {
        var tbody = document.getElementById('mold-matrix-body');
        var moldCountInput = document.getElementById('mold_count');
        if (!tbody || !moldCountInput) return;
        var visibleRows = tbody.querySelectorAll('.mold-row:not([style*="display: none"])');
        moldCountInput.value = visibleRows.length;
    });
});

/* ============ 初始化 ============ */

if (document.readyState !== 'loading') {
    initMoldMatrix();
} else {
    document.addEventListener('DOMContentLoaded', initMoldMatrix);
}
