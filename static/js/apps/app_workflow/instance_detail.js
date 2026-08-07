/* app_workflow 流程实例详情页：bpmn-js 渲染（复用 BpmnStatusViewer）+ 退回/取消弹窗处理 */
document.addEventListener('DOMContentLoaded', function() {

    // ── bpmn-js viewer（复用通用组件）──
    var xmlEl = document.getElementById('bpmn-xml-data');
    var statusEl = document.getElementById('status-map-data');
    var loadingEl = document.getElementById('bpmn-loading');
    var errorEl = document.getElementById('bpmn-error');
    var canvasEl = document.getElementById('bpmn-viewer-canvas');

    if (xmlEl && canvasEl && window.BpmnStatusViewer) {
        var bpmnXml = xmlEl.textContent.trim();
        var statusMap = {};
        try { statusMap = JSON.parse(statusEl.textContent); } catch(e) {}
        window.BpmnStatusViewer.render(canvasEl, bpmnXml, statusMap, {
            loadingEl: loadingEl,
            errorEl: errorEl
        });
    }

    // ── Return modal handler ──
    var returnBtn = document.getElementById('confirmReturn');
    if (returnBtn) {
        returnBtn.addEventListener('click', async function() {
            var url = this.getAttribute('data-url');
            var targetPk = document.getElementById('returnTarget').value;
            var reason = document.getElementById('returnReason').value.trim();
            var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

            if (!targetPk) { alert('请选择退回到哪个节点。'); return; }
            if (!reason) { alert('请填写退回原因。'); return; }

            try {
                var formData = new FormData();
                formData.append('target_task_pk', targetPk);
                formData.append('remark', reason);
                var resp = await fetch(url, {
                    method: 'POST',
                    headers: {'X-CSRFToken': csrfToken},
                    body: formData,
                });
                var result = await resp.json();
                if (result.status === 'success') {
                    window.location.reload();
                } else {
                    alert('退回失败：' + result.message);
                }
            } catch (err) {
                alert('退回请求发生错误。');
            }
        });
    }

    // ── Cancel modal handler ──
    var cancelBtn = document.getElementById('confirmCancel');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', async function() {
            var url = this.getAttribute('data-url');
            var reason = document.getElementById('cancelReason').value;
            var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

            try {
                var formData = new FormData();
                formData.append('reason', reason);
                var resp = await fetch(url, {
                    method: 'POST',
                    headers: {'X-CSRFToken': csrfToken},
                    body: formData,
                });
                var result = await resp.json();
                if (result.status === 'success') {
                    window.location.reload();
                } else {
                    alert('取消失败：' + result.message);
                }
            } catch (err) {
                alert('取消请求发生错误。');
            }
        });
    }
});