/**
 * 完成注塑任务 — 样条行动态管理
 * 依赖 DOM 结构：
 *   div#specimen-rows            — 行容器
 *   script#specimen-row-template — 行模板（{IDX} 占位符）
 *   input#specimen_count         — 隐藏字段，记录当前行数
 *   button#add-specimen-row      — 新增行按钮
 *   .remove-specimen-row         — 删除行按钮（事件委托）
 */
document.addEventListener('DOMContentLoaded', function () {
    var specimenRows = document.getElementById('specimen-rows');
    var template = document.getElementById('specimen-row-template').innerHTML;
    var specimenCountInput = document.getElementById('specimen_count');
    var specimenIdx = 0;

    function updateSpecimenCount() {
        specimenCountInput.value = specimenRows.querySelectorAll('.specimen-row').length;
    }

    function addSpecimenRow() {
        var html = template.replace(/{IDX}/g, specimenIdx);
        specimenRows.insertAdjacentHTML('beforeend', html);
        specimenIdx++;
        updateSpecimenCount();
    }

    document.getElementById('add-specimen-row').addEventListener('click', addSpecimenRow);

    // 事件委托：删除行
    specimenRows.addEventListener('click', function (e) {
        var btn = e.target.closest('.remove-specimen-row');
        if (!btn) return;
        btn.closest('.specimen-row').remove();
        updateSpecimenCount();
    });

    // 初始添加一行
    addSpecimenRow();
});
