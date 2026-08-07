/* app_form_management 表单填写页：Vue 表单 + 审批流程预览（bpmn-js）
 * 动态业务配置（stepGroups/布尔/CSRF/URL）由模板通过 json_script 注入 */
(function() {
    'use strict';

    // ── 服务端预计算的业务数据（json_script 标签）──
    var configEl = document.getElementById('fill-config-data');
    var FILL_CONFIG = {};
    if (configEl) {
        try { FILL_CONFIG = JSON.parse(configEl.textContent.trim()); } catch(e) {}
    }
    var stepGroups = FILL_CONFIG.stepGroups || [];
    var hasSteps = FILL_CONFIG.hasSteps;
    var workflowRestricted = FILL_CONFIG.workflowRestricted;
    var hasWorkflow = FILL_CONFIG.hasWorkflow;
    var csrfToken = FILL_CONFIG.csrfToken || '';
    var submitUrl = FILL_CONFIG.submitUrl || '';
    var mySubmissionsUrl = FILL_CONFIG.mySubmissionsUrl || '';
    var uploadUrl = FILL_CONFIG.uploadUrl || '';

    var workflowPreview = null;
    var previewEl = document.getElementById('workflow-preview-data');
    if (previewEl) {
        try { workflowPreview = JSON.parse(previewEl.textContent.trim()); } catch(e) {}
    }

    // ── 审批流程预览：bpmn-js 渲染（复用通用组件 preview 模式）──
    function initFlowViewer() {
        var canvasEl = document.getElementById('bpmn-preview-canvas');
        var errorEl = document.getElementById('bpmn-preview-error');
        if (!canvasEl || !workflowPreview || !workflowPreview.bpmn_xml) return;
        if (!window.BpmnStatusViewer) return;
        errorEl.style.display = 'none';

        window.BpmnStatusViewer.render(
            canvasEl,
            workflowPreview.bpmn_xml,
            workflowPreview.status_map || {},
            { preview: true, errorEl: errorEl }
        );
    }

    const { createApp } = Vue;

    const app = createApp({
        data() {
            var configEl = document.getElementById('form-config-data');
            var optionEl = document.getElementById('form-option-data');
            var dataEl = document.getElementById('existing-data');
            var allRules = [];
            var option = {};
            var formData = {};
            try { allRules = JSON.parse(configEl.textContent.trim()); } catch(e) {}
            try { option = JSON.parse(optionEl.textContent.trim()); } catch(e) {}
            try { formData = JSON.parse(dataEl.textContent.trim()); } catch(e) {}

            var formOption = Object.assign({
                form: { labelWidth: '120px' }
            }, option, {
                submitBtn: false,
                resetBtn: false,
                form: Object.assign({ labelWidth: '120px' }, option.form || {})
            });

            // 工作流限制时：仅步骤1的字段可编辑，其余字段只读
            if (workflowRestricted) {
                FCReadonly.apply(allRules, function(r) {
                    return FCReadonly.stepOf(r) !== 1;
                });
            }

            return {
                allRules: allRules,
                stepGroups: stepGroups,
                hasSteps: hasSteps,
                hasWorkflow: hasWorkflow,
                workflowRestricted: workflowRestricted,
                activeStep: 0,
                formData: formData,
                fApi: null,
                saving: false,
                showFlow: false,
                flowLoading: false,
                formOption: formOption
            };
        },

        mounted() {
            if (this.fApi && this.formData && Object.keys(this.formData).length > 0) {
                this.fApi.setValue(this.formData);
            }
        },

        watch: {
            fApi(api) {
                if (api && this.formData && Object.keys(this.formData).length > 0) {
                    api.setValue(this.formData);
                }
            },
            showFlow(v) {
                if (v) {
                    this.flowLoading = true;
                    this.$nextTick(function() {
                        initFlowViewer();
                        setTimeout(function() { this.flowLoading = false; }.bind(this), 300);
                    }.bind(this));
                }
            }
        },

        methods: {
            openFlowPreview() {
                if (!workflowPreview || !workflowPreview.bpmn_xml) {
                    ElementPlus.ElMessage.warning('该表单未关联审批流程');
                    return;
                }
                this.showFlow = true;
            },

            _readSubmissionId() {
                var submissionEl = document.getElementById('submission-id');
                var subId = null;
                if (submissionEl) {
                    try { subId = JSON.parse(submissionEl.textContent.trim()); } catch(e) {}
                }
                return subId;
            },

            // 单个待上传文件通过上传端点上传，返回 {url, name}
            async uploadOne(file, field, subId) {
                var fd = new FormData();
                fd.append('file', file);
                fd.append('submission_id', subId || '');
                fd.append('field_name', field);
                fd.append('csrfmiddlewaretoken', csrfToken);
                var resp = await fetch(uploadUrl, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': csrfToken,
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: fd
                });
                var result = await resp.json();
                if (!result.data) {
                    throw new Error(result.message || '文件上传失败');
                }
                return result.data; // {url, name}
            },

            // 提交/保存前，将设计为"选取后不立即上传"的字段中待上传文件统一上传
            async flushPendingUploads() {
                var reg = window.__fcPendingUploads__ || {};
                var subId = this._readSubmissionId();
                for (var field in reg) {
                    var files = reg[field];
                    if (!Array.isArray(files)) continue;
                    // 找出"选择了但尚未上传"的文件（有 raw 且无服务器下载 URL）
                    var pending = files.filter(function(f) {
                        return f && f.raw &&
                            !(f.url && f.url.indexOf('/attachment/download/') > -1);
                    });
                    if (!pending.length) continue;

                    var uploaded = [];
                    for (var i = 0; i < pending.length; i++) {
                        var res = await this.uploadOne(pending[i].raw, field, subId);
                        uploaded.push({ url: res.url, name: res.name });
                    }

                    // 合并字段值：保留已上传项（有 url、无 raw），追加新上传项，去掉未上传的 raw 项
                    var existing = this.fApi.form[field];
                    if (!Array.isArray(existing)) existing = [];
                    var seen = {};
                    existing.forEach(function(e) {
                        if (e && e.url && !e.raw) seen[e.url] = 1;
                    });
                    var merged = existing.filter(function(e) {
                        return e && e.url && !e.raw;
                    });
                    uploaded.forEach(function(up) {
                        if (!seen[up.url]) { seen[up.url] = 1; merged.push(up); }
                    });
                    this.fApi.setValue({ [field]: merged });
                }
            },

            async sendData(formData, status) {
                var remark = document.getElementById('remark-input').value.trim();
                var submissionEl = document.getElementById('submission-id');
                var submissionId = null;
                try { submissionId = JSON.parse(submissionEl.textContent.trim()); } catch(e) {}
                var body = {
                    form_data: formData,
                    status: status,
                    remark: remark,
                };
                if (submissionId) {
                    body.submission_id = submissionId;
                }
                var resp = await fetch(submitUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify(body)
                });
                var result = await resp.json();
                if (result.status !== 'success') {
                    ElementPlus.ElMessage.error(result.message || '操作失败');
                }
                return result;
            },

            async saveDraft() {
                if (!this.fApi) return;
                this.saving = true;
                try {
                    await this.flushPendingUploads();
                    var result = await this.sendData(this.fApi.form, 'DRAFT');
                    if (result && result.status === 'success') {
                        ElementPlus.ElMessage.success('草稿已保存');
                    }
                } catch(err) {
                    ElementPlus.ElMessage.error('请求失败: ' + err.message);
                } finally {
                    this.saving = false;
                }
            },

            async submitForm() {
                if (!this.fApi) return;
                this.saving = true;
                try {
                    await this.flushPendingUploads();
                    await this.fApi.validate();
                    var data = this.fApi.form;
                    if (data && Object.keys(data).length > 0) {
                        var result = await this.sendData(data, 'SUBMITTED');
                        if (result && result.status === 'success') {
                            window.location.href = mySubmissionsUrl;
                        }
                    } else {
                        ElementPlus.ElMessage.warning('请检查表单填写内容');
                    }
                } catch(err) {
                    ElementPlus.ElMessage.warning('请检查表单填写内容');
                } finally {
                    this.saving = false;
                }
            }
        }
    });

    app.use(ElementPlus);
    app.use(FcDesigner.formCreate);
    app.mount('#form-fill-app');

    // 供模板内"返回"按钮 onclick 调用
    window.goBack = function goBack() {
        window.history.back();
    };
})();