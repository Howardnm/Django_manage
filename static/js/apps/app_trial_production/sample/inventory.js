/**
 * 样品库存列表页 — 批量选择 + SAP 入库交互
 */

document.addEventListener('DOMContentLoaded', function () {
    var selectAll = document.getElementById('select-all');
    var checkboxes = document.querySelectorAll('.sample-checkbox');
    var batchBar = document.getElementById('batch-action-bar');
    var batchSelectedText = document.getElementById('batch-selected-text');
    var batchSapBtn = document.getElementById('batch-sap-btn');
    // 从 data 属性读取批量入库 URL 基础路径，避免硬编码
    var batchSapBaseUrl = batchSapBtn ? batchSapBtn.getAttribute('data-batch-url') : '';

    if (!selectAll || !batchBar) return;

    function getSelectedIds() {
        var checked = document.querySelectorAll('.sample-checkbox:checked');
        return Array.from(checked).map(function (cb) { return cb.value; });
    }

    function updateBatchBar() {
        var ids = getSelectedIds();
        if (ids.length > 0) {
            // 直接修改 inline style 会覆盖原有的 display:none（包括 !important）
            batchBar.style.display = 'flex';
            batchSelectedText.textContent = '已选 ' + ids.length + ' 条样品';
            if (batchSapBtn && batchSapBaseUrl) {
                batchSapBtn.href = batchSapBaseUrl + '?ids=' + ids.join(',');
            }
        } else {
            batchBar.style.display = 'none';
            selectAll.checked = false;
        }
    }

    // 全选 / 取消全选
    selectAll.addEventListener('change', function () {
        checkboxes.forEach(function (cb) {
            cb.checked = selectAll.checked;
        });
        updateBatchBar();
    });

    // 单个 checkbox 变化
    checkboxes.forEach(function (cb) {
        cb.addEventListener('change', function () {
            if (!cb.checked) {
                selectAll.checked = false;
            } else if (getSelectedIds().length === checkboxes.length) {
                selectAll.checked = true;
            }
            updateBatchBar();
        });
    });

    // 初始状态
    updateBatchBar();
});

/** 取消全部选择（供模板按钮 onclick 调用） */
function clearAllSelections() {
    document.querySelectorAll('.sample-checkbox:checked').forEach(function (cb) {
        cb.checked = false;
    });
    var selectAll = document.getElementById('select-all');
    if (selectAll) selectAll.checked = false;
    var batchBar = document.getElementById('batch-action-bar');
    if (batchBar) batchBar.style.display = 'none';
}
