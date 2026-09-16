/* ==========================================
   测试数据回写页交互 — app_project/detail/_test_result_mean_writeback.html
   数据桥接:
     - #writeback-config-meta        (模板 |json_script 注入的测试项目元数据)
     - #writeback-empty-row-template (新增行的 <script type="text/template">)

   「测试项目」下拉与实验单编辑页保持一致：.form-select-search（base.html 会在
   DOMContentLoaded 全局初始化为 TomSelect 本地搜索），选项文案同为 TestConfig.__str__。
   值控件按类型分三态（数字 / 文本 / 下拉）；字段名沿用服务端前缀约定：
     num_{pk} 数值 · txt_{pk} 文本或下拉结果 · date_{pk} 测试日期 · rem_{pk} 备注
   ========================================== */

document.addEventListener('DOMContentLoaded', function () {
    var rowsBody = document.getElementById('writeback-rows');
    var addBtn = document.getElementById('add-writeback-row');
    var templateEl = document.getElementById('writeback-empty-row-template');
    if (!rowsBody || !addBtn || !templateEl) return;

    var meta = {};
    var metaEl = document.getElementById('writeback-config-meta');
    if (metaEl) {
        try { meta = JSON.parse(metaEl.textContent); } catch (e) { meta = {}; }
    }

    /* 选项文案来自后台配置，拼进 HTML 前必须转义（属性值与文本都要） */
    function escapeHtml(text) {
        return String(text == null ? '' : text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    // 控件一律用基础尺寸，由 test_result_writeback.css 的 #data-table 规则统一压紧；
    // 混用 -sm 会让选框大小与现存行不一致。
    var EMPTY_VALUE_CELL = '<input type="text" class="form-control" ' +
        'disabled placeholder="请先选择测试项目">';

    function buildValueWidget(pk, info) {
        if (info.type === 'NUMBER') {
            return '<input type="number" step="0.001" class="form-control value-number" name="num_' +
                escapeHtml(pk) + '">';
        }
        if (info.type === 'SELECT') {
            var parts = ['<option value=""></option>'];
            (info.options || []).forEach(function (opt) {
                parts.push('<option value="' + escapeHtml(opt) + '">' + escapeHtml(opt) + '</option>');
            });
            return '<select class="form-select value-select" name="txt_' + escapeHtml(pk) + '">' +
                parts.join('') + '</select>';
        }
        return '<input type="text" class="form-control value-text" name="txt_' + escapeHtml(pk) + '">';
    }

    /* 选中某个测试项目后：重建值控件并给日期/备注补上 name。
       换测试项目等于换了一行内容，旧值没有意义，一并清掉。 */
    function applyConfigSelection(select) {
        var row = select.closest('tr');
        var cell = row.querySelector('.writeback-value-cell');
        var dateInput = row.querySelector('.writeback-date, input[name^="date_"]');
        var remarkInput = row.querySelector('.writeback-remark, input[name^="rem_"]');
        var origin = row.querySelector('.writeback-origin');

        function reset(disabled) {
            dateInput.value = '';
            remarkInput.value = '';
            dateInput.disabled = disabled;
            remarkInput.disabled = disabled;
            if (disabled) {
                dateInput.removeAttribute('name');
                remarkInput.removeAttribute('name');
            }
        }

        var pk = select.value;
        var info = meta[pk];
        if (!info) {
            cell.innerHTML = EMPTY_VALUE_CELL;
            reset(true);
            if (origin) origin.removeAttribute('name');
            return;
        }

        cell.innerHTML = buildValueWidget(pk, info);
        reset(false);
        dateInput.name = 'date_' + pk;
        remarkInput.name = 'rem_' + pk;
        // 告诉服务端这一行原本属于哪个测试项，改过就移除原记录
        if (origin) {
            origin.name = 'orig_' + pk;
            origin.value = origin.dataset.origin;
        }
    }

    /* ── 新增一行 ── */
    addBtn.addEventListener('click', function () {
        var emptyRow = document.getElementById('writeback-empty-row');
        if (emptyRow) emptyRow.remove();

        rowsBody.insertAdjacentHTML('beforeend', templateEl.innerHTML);
        var row = rowsBody.lastElementChild;

        // 全局 TomSelect 初始化只在 DOMContentLoaded 跑过一次，新行要自己补
        if (window.TomSelect && typeof initLocalTomSelectAll === 'function') {
            initLocalTomSelectAll(row);
        }
        var select = row.querySelector('.writeback-config');
        if (select) select.focus();
    });

    /* ── 切换测试项目（已有行与新增行共用）──
       委托在 tbody 上即可：TomSelect 变更时会向原 <select> 派发冒泡的原生 change。 */
    rowsBody.addEventListener('change', function (e) {
        var select = e.target.closest('.writeback-config');
        if (select) applyConfigSelection(select);
    });

    /* ── 删除行 ──
       库里已存在的行（data-persisted）改为清空值并隐藏：空值仍会随表单提交，
       服务端据此删除该测试项的手动录入记录。新增行直接摘掉 DOM 即可。 */
    rowsBody.addEventListener('click', function (e) {
        var btn = e.target.closest('.remove-writeback-row');
        if (!btn) return;

        var row = btn.closest('tr');
        if (!row.dataset.persisted) {
            row.remove();
            return;
        }
        row.querySelectorAll('input, select').forEach(function (el) {
            if (el.name) el.value = '';
        });
        row.style.display = 'none';
    });
});
