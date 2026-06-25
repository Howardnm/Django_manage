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
        const newValue = parseFloat(inputWorkload.value) || 0;
        const total = existingSum + newValue;

        if (currentTotalText) {
            currentTotalText.textContent = (total * 100).toFixed(0) + '%';
        }

        if (total > 1.0001) {
            if (warningBox) warningBox.classList.remove('d-none');
            if (warningText) warningText.innerHTML = '<strong>权重超标！</strong> 总工作量将达到 <b>' + (total * 100).toFixed(0) + '%</b>，请调减。';
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
