/**
 * 产品报价需求单详情页交互。
 *
 * - submitStep(action)：把审批栏的意见/动作写入步骤表单并提交。
 * - openTransfer()：打开人员选择器，确认后提交移交表单。
 */

function submitStep(action) {
    var form = document.getElementById('step-form');
    var actionInput = document.getElementById('step-action');
    var remarkInput = document.getElementById('step-remark');
    var remarkBox = document.getElementById('remark-input');
    if (actionInput) actionInput.value = action;
    if (remarkInput && remarkBox) remarkInput.value = remarkBox.value;
    if (form) form.submit();
}

function openTransfer() {
    openUserPicker('transferPicker', function (result) {
        var userId = result && result.id;
        if (!userId) return;
        document.getElementById('reassign-user-id').value = userId;
        document.getElementById('reassign-form').submit();
    }, { dynamic: true, title: '选择移交人' });
}

// ── 查看审批流程：bpmn-js 弹窗渲染（复用通用组件 BpmnStatusViewer）──
document.addEventListener('DOMContentLoaded', function () {
    var modal = document.getElementById('modal-flow');
    if (!modal || !window.BpmnStatusViewer) return;
    var rendered = false;
    modal.addEventListener('shown.bs.modal', function () {
        if (rendered) return;
        rendered = true;
        var xmlEl = document.getElementById('bpmn-xml-data');
        var statusEl = document.getElementById('status-map-data');
        var canvasEl = document.getElementById('bpmn-viewer-canvas');
        var loadingEl = document.getElementById('bpmn-loading');
        var errorEl = document.getElementById('bpmn-error');
        var xml = xmlEl ? xmlEl.textContent.trim() : '';
        var statusMap = {};
        try { statusMap = statusEl ? JSON.parse(statusEl.textContent) : {}; } catch (e) {}
        window.BpmnStatusViewer.render(canvasEl, xml, statusMap, {
            loadingEl: loadingEl,
            errorEl: errorEl
        });
    });
});
