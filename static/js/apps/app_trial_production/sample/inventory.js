/**
 * 样品库存列表页 — 批量选择 + SAP 入库交互
 * 参考成品材料列表的勾选模式：全选用 onclick，操作按需查询 :checked
 */

/** 全选 / 取消全选 — 参考 material_list toggleAll 模式 */
function toggleAllSample(source) {
    var checkboxes = document.querySelectorAll('.sample-checkbox');
    for (var i = 0; i < checkboxes.length; i++) {
        checkboxes[i].checked = source.checked;
    }
    updateBatchBar();
}

/** 取消全部选择 */
function clearAllSampleSelections() {
    var checkboxes = document.querySelectorAll('.sample-checkbox');
    for (var i = 0; i < checkboxes.length; i++) {
        checkboxes[i].checked = false;
    }
    document.getElementById('select-all').checked = false;
    updateBatchBar();
}

/** 更新批量操作栏的显示/隐藏及选中计数 */
function updateBatchBar() {
    var checked = document.querySelectorAll('.sample-checkbox:checked');
    var batchBar = document.getElementById('batch-action-bar');
    var batchSelectedText = document.getElementById('batch-selected-text');
    var batchSapBtn = document.getElementById('batch-sap-btn');
    var batchSapBaseUrl = batchSapBtn ? batchSapBtn.getAttribute('data-batch-url') : '';
    var selectAll = document.getElementById('select-all');

    if (checked.length > 0) {
        batchBar.classList.add('d-flex');
        batchBar.style.display = '';
        batchSelectedText.textContent = '已选 ' + checked.length + ' 条样品';
        if (batchSapBtn && batchSapBaseUrl) {
            var ids = Array.from(checked).map(function (cb) { return cb.value; });
            batchSapBtn.href = batchSapBaseUrl + '?ids=' + ids.join(',');
        }
    } else {
        batchBar.classList.remove('d-flex');
        batchBar.style.display = 'none';
        if (selectAll) selectAll.checked = false;
    }
}

document.addEventListener('DOMContentLoaded', function () {
    // 单个 checkbox 变化时同步全选状态 + 刷新操作栏
    var checkboxes = document.querySelectorAll('.sample-checkbox');
    for (var i = 0; i < checkboxes.length; i++) {
        checkboxes[i].addEventListener('change', function () {
            var all = document.querySelectorAll('.sample-checkbox');
            var checked = document.querySelectorAll('.sample-checkbox:checked');
            document.getElementById('select-all').checked = checked.length === all.length;
            updateBatchBar();
        });
    }

    // 初始状态
    updateBatchBar();
});
