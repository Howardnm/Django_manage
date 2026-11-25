/**
 * 工单页工艺方案：远程搜索，换方案后直接覆盖工艺参数输入框。
 * 服务端已经填过 initial 时不在进入页面时再请求。
 * 覆盖选择器：#process-params [name="<AbstractExtrusionParams.ALL_PARAM_FIELDS>"]
 * 表单不要加 prefix，name 就是字段名。
 */
document.addEventListener('DOMContentLoaded', function () {
    var card = document.getElementById('process-scheme-card');
    if (!card) return;

    var hidden = card.querySelector('input[name="process_profile"]');
    if (!hidden) return;

    var current = String(hidden.value || '');
    var requestSeq = 0;
    var displayKeys = {name: true, machine: true, screw_combination: true};

    function setLabel(id, text) {
        var el = document.getElementById(id);
        if (!el) return;
        el.textContent = text ? String(text) : '—';
    }

    function setControl(el, value) {
        var text = value === null || value === undefined ? '' : String(value);
        if (el.tomselect) {
            el.tomselect.setValue(text, true);
        } else {
            el.value = text;
        }
    }

    function applyParams(data) {
        setLabel('process-scheme-machine', data.machine);
        setLabel('process-scheme-screw', data.screw_combination);
        var root = document.getElementById('process-params');
        if (!root) return;
        Object.keys(data).forEach(function (key) {
            if (displayKeys[key]) return;
            var escaped = window.CSS && CSS.escape ? CSS.escape(key) : key;
            var el = root.querySelector('[name="' + escaped + '"]');
            if (!el) return;
            setControl(el, data[key]);
        });
    }

    function loadParams(pk) {
        var template = card.getAttribute('data-params-url') || '';
        var url = template.replace('/0/', '/' + pk + '/');
        var seq = ++requestSeq;
        fetch(url, {headers: {Accept: 'application/json'}})
            .then(function (response) {
                if (!response.ok) throw new Error('params');
                return response.json();
            })
            .then(function (data) {
                if (seq !== requestSeq) return;
                applyParams(data);
            })
            .catch(function () {
                if (seq !== requestSeq) return;
                setLabel('process-scheme-machine', '');
                setLabel('process-scheme-screw', '');
            });
    }

    function onProfileChange(value) {
        value = value == null ? '' : String(value);
        if (value === current) return;
        current = value;
        if (!/^\d+$/.test(value)) {
            setLabel('process-scheme-machine', '');
            setLabel('process-scheme-screw', '');
            return;
        }
        loadParams(value);
    }

    var modal = document.getElementById('modal-process-profile');
    if (modal) {
        modal.addEventListener('hidden.bs.modal', function () {
            onProfileChange(hidden.value);
        });
    }
});
