/**
 * BPMN 流程图状态查看器 — 通用组件
 *
 * 供 3 个页面复用：
 *   1. 流程实例详情页   templates/apps/app_workflow/instance_detail.html
 *   2. 表单提交详情页   templates/apps/app_form_management/submission_detail.html（审批页）
 *   3. 表单填写预览页   templates/apps/app_form_management/submission_fill.html
 *
 * 用法：
 *   BpmnStatusViewer.render(containerEl, bpmnXml, statusMap, {
 *       preview: false,          // true=预览模式：所有节点按 pending 渲染，仅展示预分配审批人
 *       loadingEl: loadingEl,    // 可选：加载提示元素
 *       errorEl: errorEl         // 可选：错误提示元素
 *   });
 *
 * statusMap: { [bpmnId]: {
 *     display_status, status_label, is_gateway, remark,
 *     approver_name, assigned_to_name, candidate_usernames, candidate_group_members,
 *     pre_assigned_name, pre_assigned_candidates, pre_assigned_groups, assignee_label
 * } }
 *
 * 依赖：bpmn-navigated-viewer（页面先于本文件加载，暴露全局 BpmnJS）。
 * 样式：full 模式用 approval-overlay / overlay-badge / status-capsule，
 *       preview 模式用 bpmn-preview-overlay / preview-badge，由各页面 CSS 提供。
 */

(function () {
    'use strict';

    // 记录各容器已创建的 viewer，重复渲染（如预览弹窗反复打开）时先销毁旧实例
    var viewers = {};

    function getViewer(containerEl) {
        var key = containerEl.id || String(containerEl);
        if (viewers[key]) {
            try { viewers[key].destroy(); } catch (e) {}
        }
        var viewer = new BpmnJS({ container: containerEl });
        viewers[key] = viewer;
        return viewer;
    }

    // ── 完整模式：按审批历史显示状态，优先级链 approver → 指派 → 候选 → 预解析 → camunda 兜底 ──
    function buildFullOverlay(info) {
        var displayStatus = info.display_status || 'pending';
        var statusLabel = info.status_label || '';
        var candidateUsernames = info.candidate_usernames || [];
        var candidateGroupMembers = info.candidate_group_members || {};
        var approverName = info.approver_name || '';
        var remark = info.remark || '';
        var assigneeLabel = info.assignee_label || '';

        var html = '<div class="approval-overlay"><div class="overlay-badge-row">';
        if (approverName) {
            if (displayStatus === 'returned') {
                html += '<span class="overlay-badge badge-returned">' + approverName + ' 退回</span>';
            } else if (displayStatus === 'rejected') {
                html += '<span class="overlay-badge badge-rejected">' + approverName + ' 驳回</span>';
            } else {
                html += '<span class="overlay-badge badge-approved">' + approverName + '</span>';
            }
        } else if (info.assigned_to_name) {
            html += '<span class="overlay-badge badge-assignee">' + info.assigned_to_name + '</span>';
        } else if (candidateUsernames.length > 0 || Object.keys(candidateGroupMembers).length > 0) {
            html += '<span class="overlay-badge badge-candidate">待签收</span>';
        } else if (info.pre_assigned_name) {
            html += '<span class="overlay-badge badge-pending">' + info.pre_assigned_name + '</span>';
        } else if ((info.pre_assigned_candidates && info.pre_assigned_candidates.length > 0) ||
                   (info.pre_assigned_groups && info.pre_assigned_groups.length > 0)) {
            html += '<span class="overlay-badge badge-pending">待签收</span>';
        } else if (assigneeLabel) {
            html += '<span class="overlay-badge badge-pending">' + assigneeLabel + '</span>';
        }
        if (statusLabel) {
            html += '<span class="status-capsule capsule-' + displayStatus + '">' + statusLabel + '</span>';
        }
        html += '</div>';

        if (candidateUsernames.length > 0) {
            html += '<div class="badge-row">';
            candidateUsernames.forEach(function (u) {
                html += '<span class="overlay-badge badge-assignee">' + u + '</span>';
            });
            html += '</div>';
        }
        if (remark) {
            html += '<div class="remark-text">' + remark + '</div>';
        }
        html += '</div>';
        return html;
    }

    // ── 预览模式：表单提交前的流程预览，仅展示预解析审批人或"待签收" ──
    function buildPreviewHtml(info) {
        var name = info.pre_assigned_name || '';
        var hasCandidates = (info.pre_assigned_candidates && info.pre_assigned_candidates.length) ||
                            (info.pre_assigned_groups && info.pre_assigned_groups.length);
        if (!name && !hasCandidates) return '';

        var html = '<div class="bpmn-preview-overlay"><div class="preview-badge-row">';
        if (name) {
            html += '<span class="preview-badge badge-pending">' + name + '</span>';
        } else {
            html += '<span class="preview-badge badge-pending">待签收</span>';
        }
        html += '</div></div>';
        return html;
    }

    function render(containerEl, bpmnXml, statusMap, options) {
        options = options || {};
        var loadingEl = options.loadingEl || null;
        var errorEl = options.errorEl || null;
        var preview = !!options.preview;
        statusMap = statusMap || {};

        if (!containerEl) return;

        function showLoading(v) {
            if (loadingEl) loadingEl.style.display = v ? 'flex' : 'none';
        }
        function showError() {
            if (errorEl) errorEl.style.display = 'flex';
        }

        if (!bpmnXml || bpmnXml.length < 50) {
            showLoading(false);
            showError();
            return;
        }

        var viewer = getViewer(containerEl);
        viewer.importXML(bpmnXml).then(function () {
            var canvas = viewer.get('canvas');
            var overlays = viewer.get('overlays');
            var elementRegistry = viewer.get('elementRegistry');
            showLoading(false);

            Object.keys(statusMap).forEach(function (bpmnId) {
                var info = statusMap[bpmnId] || {};
                var element = elementRegistry.get(bpmnId);
                if (!element) return;

                var displayStatus = info.display_status || 'pending';
                canvas.addMarker(bpmnId, 'status-' + displayStatus);
                if (info.is_gateway) return;

                var overlayHtml = preview ? buildPreviewHtml(info) : buildFullOverlay(info);
                if (!overlayHtml) return;
                try {
                    overlays.add(bpmnId, { position: { bottom: -5, left: 0 }, html: overlayHtml });
                } catch (e) {}
            });
            try { canvas.zoom('fit-viewport'); } catch (e) {}
        }).catch(function (err) {
            console.error('BPMN import failed:', err);
            showLoading(false);
            showError();
        });
    }

    window.BpmnStatusViewer = { render: render };
})();