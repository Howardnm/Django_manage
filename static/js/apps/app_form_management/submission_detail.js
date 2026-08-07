/* app_form_management 表单提交详情页（审批页）：Vue 表单 + 流程图(Tab) + 审批操作
 * 动态业务配置（stepGroups/权限/URL）由模板通过 json_script 注入到 #detail-config-data */
(function () {
    'use strict';

    // ── 服务端预计算的业务数据 ──
    var cfgEl = document.getElementById('detail-config-data');
    var cfg = {};
    if (cfgEl) {
        try { cfg = JSON.parse(cfgEl.textContent.trim()); } catch (e) {}
    }
    var stepGroups = cfg.stepGroups || [];
    var hasSteps = stepGroups.length > 1;
    var canEditStep = !!cfg.canEditStep;
    var editableStepLabel = cfg.editableStepLabel || '';
    var activeStepIndex = cfg.activeStepIndex || 0;
    var currentTaskFormStep = cfg.currentTaskFormStep || 0;
    var approveUrl = cfg.approveUrl || '';
    var returnUrl = cfg.returnUrl || '';
    var reassignUrl = cfg.reassignUrl || '';
    window._mainFormApi = null;
    window._stepFieldMap = cfg.fieldStepMap || {};

    // ── Vue form renderer ──
    const { createApp } = Vue;
    const app = createApp({
        data() {
            var configEl = document.getElementById('form-config-data');
            var optionEl = document.getElementById('form-option-data');
            var dataEl = document.getElementById('submission-data');
            var allRules = [];
            var option = {};
            var formData = {};
            try { allRules = JSON.parse(configEl.textContent.trim()); } catch (e) {}
            try { option = JSON.parse(optionEl.textContent.trim()); } catch (e) {}
            try { formData = JSON.parse(dataEl.textContent.trim()); } catch (e) {}
            var formOption = Object.assign({ submitBtn: false, resetBtn: false }, option, {
                form: Object.assign({}, option.form || {})
            });

            // 字段编辑权限：仅当前审批人可以编辑其负责步骤的字段
            if (canEditStep) {
                // 当前用户是活跃审批人 → 启用其负责步骤的字段，其余字段只读
                FCReadonly.apply(allRules, function (r) {
                    return FCReadonly.stepOf(r) !== currentTaskFormStep;
                });
            } else {
                // 非活跃审批人（仅查看 / 流程已结束 / 单步骤表单审批中）→ 全部只读
                FCReadonly.apply(allRules, function () { return true; });
            }

            return {
                allRules: allRules, stepGroups: stepGroups, hasSteps: hasSteps,
                canEditStep: canEditStep, editableStepLabel: editableStepLabel,
                activeStep: activeStepIndex,
                formData: formData, fApi: null, formOption: formOption
            };
        },
        mounted() {
            if (this.fApi && this.formData && Object.keys(this.formData).length > 0) {
                this.fApi.setValue(this.formData);
            }
        },
        watch: {
            fApi(api) {
                if (api) {
                    window._mainFormApi = api;
                    if (this.formData && Object.keys(this.formData).length > 0) {
                        api.setValue(this.formData);
                    }
                }
            }
        }
    });
    app.use(ElementPlus);
    app.use(FcDesigner.formCreate);
    app.mount('#submission-detail-app');

    // ── Tab switching（流程图复用 BpmnStatusViewer）──
    document.querySelectorAll('.tab-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var tabName = this.getAttribute('data-tab');
            document.querySelectorAll('.tab-btn').forEach(function (b) { b.classList.remove('active'); });
            this.classList.add('active');
            document.querySelectorAll('.tab-pane').forEach(function (p) { p.classList.remove('active'); });
            document.getElementById('tab-' + tabName).classList.add('active');
            if (tabName === 'flow' && !window._bpmnInitialized) {
                window._bpmnInitialized = true;
                if (window.BpmnStatusViewer) {
                    var xmlEl = document.getElementById('bpmn-xml-data');
                    var statusEl = document.getElementById('status-map-data');
                    var canvasEl = document.getElementById('bpmn-viewer-canvas');
                    if (xmlEl && canvasEl) {
                        var statusMap = {};
                        try { statusMap = JSON.parse(statusEl.textContent); } catch (e) {}
                        window.BpmnStatusViewer.render(canvasEl, xmlEl.textContent.trim(), statusMap, {
                            loadingEl: document.getElementById('bpmn-loading'),
                            errorEl: document.getElementById('bpmn-error')
                        });
                    }
                }
            }
        });
    });

    // ── 审批操作（由模板内 button onclick 调用，暴露到 window）──
    function getCsrfToken() {
        var pair = document.cookie.split('; ').find(function (r) { return r.startsWith('csrftoken='); });
        return pair ? pair.split('=')[1] : '';
    }

    function showToast(msg, type) {
        var t = document.createElement('div');
        t.className = 'approval-toast ' + type;
        t.textContent = msg;
        document.body.appendChild(t);
        setTimeout(function () { t.remove(); }, 2500);
    }

    // 收集当前步骤（currentTaskFormStep）的表单字段数据
    function collectStepFormData() {
        if (currentTaskFormStep > 0 && window._mainFormApi) {
            try {
                var allFormData = window._mainFormApi.form;
                var filtered = {};
                Object.keys(allFormData).forEach(function (field) {
                    if ((window._stepFieldMap[field] || 1) === currentTaskFormStep) {
                        filtered[field] = allFormData[field];
                    }
                });
                if (Object.keys(filtered).length > 0) {
                    return filtered;
                }
            } catch (e) {}
        }
        return null;
    }

    async function submitApproval(action) {
        var remark = document.getElementById('approval-remark').value.trim();
        if (action === 'REJECT' && !remark) {
            showToast('驳回操作需要填写审批意见', 'error');
            return;
        }

        // 通过前校验当前步骤的必填字段
        if (action === 'APPROVE' && window._mainFormApi) {
            try {
                await window._mainFormApi.validate();
            } catch (e) {
                showToast('请完善当前步骤的必填项后再审批', 'error');
                return;
            }
        }

        var btn = document.querySelector(action === 'APPROVE' ? '.btn-approve' : '.btn-reject');
        var btnOriginalHTML = btn.innerHTML;
        btn.disabled = true;
        btn.textContent = '提交中...';

        var stepFormData = collectStepFormData();

        try {
            var formData = new FormData();
            formData.append('action', action);
            formData.append('remark', remark);
            if (stepFormData && Object.keys(stepFormData).length > 0) {
                formData.append('step_form_data', JSON.stringify(stepFormData));
            }
            var resp = await fetch(approveUrl, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrfToken(),
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: formData
            });
            var data = await resp.json().catch(function () { return {}; });
            if (resp.ok && data.status === 'success') {
                showToast(data.message || (action === 'APPROVE' ? '审批通过' : '已驳回'), 'success');
                setTimeout(function () { location.reload(); }, 1200);
            } else {
                showToast(data.message || '操作失败，请重试', 'error');
            }
        } catch (e) {
            showToast('网络错误，请重试', 'error');
        }
        btn.disabled = false;
        btn.innerHTML = btnOriginalHTML;
    }

    // ── Return dialog ──
    var _selectedReturnTarget = null;

    function showReturnDialog() {
        document.getElementById('returnOverlay').classList.add('show');
        document.getElementById('returnRemark').value = '';
        _selectedReturnTarget = null;
        var items = document.querySelectorAll('.return-target-item');
        items.forEach(function (item) { item.classList.remove('selected'); });
    }

    function closeReturnDialog() {
        document.getElementById('returnOverlay').classList.remove('show');
    }

    function selectReturnTarget(el) {
        var items = document.querySelectorAll('.return-target-item');
        items.forEach(function (item) { item.classList.remove('selected'); });
        el.classList.add('selected');
        _selectedReturnTarget = { pk: el.getAttribute('data-pk'), name: el.getAttribute('data-task-name') };
    }

    async function submitReturn() {
        var remark = document.getElementById('returnRemark').value.trim();
        if (!remark) {
            showToast('请填写退回原因', 'error');
            return;
        }
        if (!_selectedReturnTarget) {
            showToast('请选择退回到哪个节点', 'error');
            return;
        }

        var stepFormData = collectStepFormData();
        var formData = new FormData();
        formData.append('target_task_pk', _selectedReturnTarget.pk);
        formData.append('remark', remark);
        if (stepFormData && Object.keys(stepFormData).length > 0) {
            formData.append('step_form_data', JSON.stringify(stepFormData));
        }

        try {
            var resp = await fetch(returnUrl, {
                method: 'POST',
                headers: { 'X-CSRFToken': getCsrfToken() },
                body: formData
            });
            var data = await resp.json().catch(function () { return {}; });
            if (resp.ok && data.status === 'success') {
                showToast(data.message || '已退回', 'success');
                setTimeout(function () { location.reload(); }, 1200);
            } else {
                showToast(data.message || '退回失败，请重试', 'error');
            }
        } catch (e) {
            showToast('网络错误，请重试', 'error');
        }
    }

    // ── Transfer: opens shared user picker ──
    function showTransferDialog() {
        openUserPicker('transferPicker', function (user) {
            submitTransfer(user);
        });
    }

    async function submitTransfer(user) {
        var formData = new FormData();
        formData.append('to_user_id', user.id);

        try {
            var resp = await fetch(reassignUrl, {
                method: 'POST',
                headers: { 'X-CSRFToken': getCsrfToken() },
                body: formData
            });
            var data = await resp.json().catch(function () { return {}; });
            if (resp.ok && data.status === 'success') {
                showToast(data.message || '任务已移交给 ' + user.label, 'success');
                setTimeout(function () { location.reload(); }, 1200);
            } else {
                showToast(data.message || '移交失败，请重试', 'error');
            }
        } catch (e) {
            showToast('网络错误，请重试', 'error');
        }
    }

    // 暴露到 window，供模板内 button onclick 调用
    window.submitApproval = submitApproval;
    window.showReturnDialog = showReturnDialog;
    window.closeReturnDialog = closeReturnDialog;
    window.selectReturnTarget = selectReturnTarget;
    window.submitReturn = submitReturn;
    window.showTransferDialog = showTransferDialog;
    window.submitTransfer = submitTransfer;
})();