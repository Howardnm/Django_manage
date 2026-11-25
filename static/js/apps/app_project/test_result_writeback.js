/* ==========================================
   测试数据回写页 — app_project/detail/_test_result_mean_writeback.html
   数据桥接:
     - #writeback-config-meta        (模板 |json_script 注入的测试项目元数据)
     - #writeback-empty-row-template (新增行的 <script type="text/template">)

   每个版本一格数值，字段名 num_{配方pk}_{测试项pk} / txt_{配方pk}_{测试项pk}。
   测试日期、备注整行一份：date_{测试项pk} / rem_{测试项pk}。
   ========================================== */

document.addEventListener('DOMContentLoaded', function () {
    if (window.bindFormulaTableDropdowns) {
        bindFormulaTableDropdowns(document);
    }

    var rowsBody = document.getElementById('writeback-rows');
    var addBtn = document.getElementById('add-writeback-row');
    var templateEl = document.getElementById('writeback-empty-row-template');
    if (!rowsBody || !addBtn || !templateEl) return;

    var meta = {};
    var metaEl = document.getElementById('writeback-config-meta');
    if (metaEl) {
        try { meta = JSON.parse(metaEl.textContent); } catch (e) { meta = {}; }
    }

    function escapeHtml(text) {
        return String(text == null ? '' : text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    var EMPTY_VALUE_CELL = '<input type="text" class="form-control" ' +
        'disabled placeholder="请先选择测试项目">';

    function buildValueWidget(formulaPk, testPk, info) {
        var name = escapeHtml(String(formulaPk) + '_' + String(testPk));
        if (info.type === 'NUMBER') {
            return '<input type="number" step="0.001" class="form-control value-number" name="num_' +
                name + '">';
        }
        if (info.type === 'SELECT') {
            var parts = ['<option value=""></option>'];
            (info.options || []).forEach(function (opt) {
                parts.push('<option value="' + escapeHtml(opt) + '">' + escapeHtml(opt) + '</option>');
            });
            return '<select class="form-select value-select" name="txt_' + name + '">' +
                parts.join('') + '</select>';
        }
        return '<input type="text" class="form-control value-text" name="txt_' + name + '">';
    }

    /* 选中某个测试项目后：为每个版本重建值控件，日期/备注仍是这一行一份。
       已经绑在这个测试项上的行不要重建，否则会把服务端预填的值清掉。 */
    function applyConfigSelection(select) {
        var row = select.closest('tr');
        var cells = row.querySelectorAll('.writeback-value-cell');
        var dateInput = row.querySelector('.writeback-date, input[name^="date_"]');
        var remarkInput = row.querySelector('.writeback-remark, input[name^="rem_"]');
        var origin = row.querySelector('.writeback-origin');
        var pk = select.value;
        var info = meta[pk];

        function reset(disabled) {
            if (!dateInput || !remarkInput) return;
            dateInput.value = '';
            remarkInput.value = '';
            dateInput.disabled = disabled;
            remarkInput.disabled = disabled;
            if (disabled) {
                dateInput.removeAttribute('name');
                remarkInput.removeAttribute('name');
            }
        }

        if (!info) {
            cells.forEach(function (cell) { cell.innerHTML = EMPTY_VALUE_CELL; });
            reset(true);
            if (origin) origin.removeAttribute('name');
            return;
        }

        var named = row.querySelector('.writeback-value-cell [name]');
        if (named && named.name.endsWith('_' + pk)) {
            return;
        }

        cells.forEach(function (cell) {
            cell.innerHTML = buildValueWidget(cell.getAttribute('data-formula'), pk, info);
        });
        reset(false);
        dateInput.name = 'date_' + pk;
        remarkInput.name = 'rem_' + pk;
        if (origin && origin.dataset.origin) {
            origin.name = 'orig_' + pk;
            origin.value = origin.dataset.origin;
        }
    }

    addBtn.addEventListener('click', function () {
        var emptyRow = document.getElementById('writeback-empty-row');
        if (emptyRow) emptyRow.remove();

        rowsBody.insertAdjacentHTML('beforeend', templateEl.innerHTML);
        var row = rowsBody.lastElementChild;

        if (window.TomSelect && typeof initLocalTomSelectAll === 'function') {
            initLocalTomSelectAll(row);
        }
        if (window.bindFormulaTableDropdowns) {
            bindFormulaTableDropdowns(row);
        }
        var select = row.querySelector('.writeback-config');
        if (select) select.focus();
    });

    rowsBody.addEventListener('change', function (e) {
        var select = e.target.closest('.writeback-config');
        if (select) applyConfigSelection(select);
    });

    /* 库里已有的行清空各版本的值并隐藏：空值会随表单提交，服务端据此删除。
       新增行直接摘掉。 */
    rowsBody.addEventListener('click', function (e) {
        var btn = e.target.closest('.remove-writeback-row');
        if (!btn) return;

        var row = btn.closest('tr');
        if (!row.dataset.persisted) {
            row.remove();
            return;
        }
        row.querySelectorAll('input, select').forEach(function (el) {
            if (el.name && el.type !== 'hidden') el.value = '';
        });
        row.style.display = 'none';
    });
});
