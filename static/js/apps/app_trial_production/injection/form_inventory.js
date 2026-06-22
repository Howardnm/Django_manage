/**
 * 从样品库创建独立注塑任务 — 模具行动态管理
 * 依赖 DOM 结构：
 *   div#mold-rows            — 行容器
 *   script#mold-row-template — 行模板（{IDX} 占位符）
 *   input#mold_count         — 隐藏字段，记录当前行数
 *   button#add-mold-row      — 新增行按钮
 *   .remove-mold-row         — 删除行按钮（事件委托）
 */
document.addEventListener('DOMContentLoaded', function () {
    var moldRows = document.getElementById('mold-rows');
    var template = document.getElementById('mold-row-template').innerHTML;
    var moldCountInput = document.getElementById('mold_count');
    var moldIdx = 0;

    function updateMoldCount() {
        moldCountInput.value = moldRows.querySelectorAll('.mold-row').length;
    }

    function addMoldRow() {
        var html = template.replace(/{IDX}/g, moldIdx);
        moldRows.insertAdjacentHTML('beforeend', html);
        moldIdx++;
        updateMoldCount();
    }

    document.getElementById('add-mold-row').addEventListener('click', addMoldRow);

    // 事件委托：删除行
    moldRows.addEventListener('click', function (e) {
        var btn = e.target.closest('.remove-mold-row');
        if (!btn) return;
        btn.closest('.mold-row').remove();
        updateMoldCount();
    });

    // 初始添加一行
    addMoldRow();
});
