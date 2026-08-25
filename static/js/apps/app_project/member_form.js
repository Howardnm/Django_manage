/* ==========================================
   协同成员表单前端校验 — app_project/modal/_member_form.html
   依赖: HTMX (通过 htmx:afterSettle 事件触发)
   ========================================== */

document.addEventListener("htmx:afterSettle", function (evt) {
    const form = document.getElementById('project-member-form');
    if (!form || form.dataset.validated) return;
    form.dataset.validated = '1';

    const existingSum = parseFloat(form.dataset.existingSum || '0');
    const inputWorkload = document.getElementById('input-workload');
    const btnSave = document.getElementById('btn-save-member');
    const warningBox = document.getElementById('frontend-warning');
    const warningText = document.getElementById('warning-text');
    const currentTotalText = document.getElementById('current-total-text');

    if (!inputWorkload) return;

    function validate() {
        const raw = inputWorkload.value.trim();
        const newValue = Number(raw);

        // 只允许填写 0~100 的整数
        if (raw !== '' && (!Number.isInteger(newValue) || newValue < 0 || newValue > 100)) {
            if (warningBox) warningBox.classList.remove('d-none');
            if (warningText) warningText.innerHTML = '<strong>占比只允许填写整数！</strong> 请输入 0 ~ 100 之间的整数。';
            if (btnSave) btnSave.disabled = true;
            inputWorkload.classList.add('is-invalid');
            return;
        }

        const total = existingSum + (raw === '' ? 0 : newValue);

        if (currentTotalText) {
            currentTotalText.textContent = total.toFixed(0) + '%';
        }

        if (total > 100) {
            if (warningBox) warningBox.classList.remove('d-none');
            if (warningText) warningText.innerHTML = '<strong>权重超标！</strong> 总工作量将达到 <b>' + total.toFixed(0) + '%</b>，请调减。';
            if (btnSave) btnSave.disabled = true;
            inputWorkload.classList.add('is-invalid');
        } else {
            if (warningBox) warningBox.classList.add('d-none');
            if (btnSave) btnSave.disabled = false;
            inputWorkload.classList.remove('is-invalid');
        }
    }

    inputWorkload.addEventListener('input', validate);
    validate();
});
