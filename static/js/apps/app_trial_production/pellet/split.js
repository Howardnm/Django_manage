(function() {
    const tbody = document.querySelector('#split-table tbody');
    const template = document.querySelector('#empty-row-template');
    const totalForms = document.querySelector('#id_form-TOTAL_FORMS');
    const btnAdd = document.querySelector('#btn-add-row');

    function updateStats() {
        const rows = tbody.querySelectorAll('.split-row:not(.d-none)');
        let finishedCount = 0, injectionCount = 0;
        rows.forEach(row => {
            const typeInput = row.querySelector('select[id$="-sub_type"]') || row.querySelector('input[id$="-sub_type"]');
            const qtyInput = row.querySelector('input[id$="-quantity"]');
            if (!typeInput || !qtyInput) return;
            const subType = typeInput.value;
            const qty = parseFloat(qtyInput.value) || 0;
            if (qty > 0) {
                if (subType === 'FINISHED') finishedCount++;
                else if (subType === 'FOR_INJECTION') injectionCount++;
            }
        });
        const statFinished = document.querySelector('#stat-finished-count');
        const statInjection = document.querySelector('#stat-injection-count');
        if (statFinished) statFinished.textContent = finishedCount;
        if (statInjection) statInjection.textContent = injectionCount;
    }

    function updateAllocationTracker() {
        const rows = tbody.querySelectorAll('.split-row:not(.d-none)');
        const formulaTotals = {};
        const bars = document.querySelectorAll('[id^="formula-bar-"]');
        const overplanWarning = document.querySelector('#overplan-warning');
        const overplanDetail = document.querySelector('#overplan-detail');
        const trackerStatus = document.querySelector('#tracker-status');

        rows.forEach(row => {
            const formulaInput = row.querySelector('select[id$="-formula"]') || row.querySelector('input[id$="-formula"]');
            const qtyInput = row.querySelector('input[id$="-quantity"]');
            if (!formulaInput || !qtyInput) return;
            const pk = formulaInput.value;
            const qty = parseFloat(qtyInput.value) || 0;
            if (pk) {
                formulaTotals[pk] = (formulaTotals[pk] || 0) + qty;
            }
        });

        let hasOverplan = false;
        let totalFill = 0;

        bars.forEach(bar => {
            const formulaPk = bar.id.replace('formula-bar-', '');
            const planned = parseFloat(bar.dataset.planned) || 0;
            const existing = parseFloat(bar.dataset.existing) || 0;
            const formQty = formulaTotals[formulaPk] || 0;
            const totalQty = existing + formQty;
            const pct = planned > 0 ? Math.min((totalQty / planned) * 100, 100) : 0;

            bar.style.width = pct + '%';
            bar.setAttribute('aria-valuenow', Math.round(pct));
            if (totalQty > planned && planned > 0) {
                bar.classList.add('bg-danger');
                bar.classList.remove('bg-primary');
                hasOverplan = true;
            } else {
                bar.classList.add('bg-primary');
                bar.classList.remove('bg-danger');
            }

            const currentEl = document.querySelector('#formula-current-' + formulaPk);
            if (currentEl) {
                currentEl.textContent = totalQty.toFixed(1);
                if (totalQty > planned && planned > 0) {
                    currentEl.classList.add('text-red');
                } else {
                    currentEl.classList.remove('text-red');
                }
            }

            totalFill += totalQty;
        });

        if (hasOverplan) {
            overplanWarning.classList.remove('d-none');
            overplanDetail.textContent = '分拨合计超出计划产量，请检查填写数量';
        } else {
            overplanWarning.classList.add('d-none');
        }

        if (trackerStatus) {
            if (totalFill === 0) {
                trackerStatus.textContent = '待填写';
                trackerStatus.className = 'badge ms-auto bg-secondary-lt';
            } else if (hasOverplan) {
                trackerStatus.textContent = '超标';
                trackerStatus.className = 'badge ms-auto bg-red-lt';
            } else {
                trackerStatus.textContent = '填写中';
                trackerStatus.className = 'badge ms-auto bg-azure-lt';
            }
        }
    }

    function addRow() {
        const idx = parseInt(totalForms.value);
        let html = template.innerHTML;
        html = html.replace(/__prefix__/g, idx);
        tbody.insertAdjacentHTML('beforeend', html);
        totalForms.value = idx + 1;

        const firstFormula = tbody.querySelector('.split-row:not(.d-none) select[id$="-formula"]');
        const newFormula = tbody.querySelector('#id_form-' + idx + '-formula');
        if (firstFormula && newFormula) {
            newFormula.innerHTML = firstFormula.innerHTML;
        }

        const newRow = tbody.querySelector('#id_form-' + idx + '-formula').closest('.split-row');
        bindRemove(newRow);
        bindChange(newRow);
    }

    function removeRow(btn) {
        const row = btn.closest('.split-row');
        let deleteCheckbox = row.querySelector('input[id$="-DELETE"]');
        if (!deleteCheckbox) {
            return;
        }
        deleteCheckbox.checked = true;
        row.classList.add('d-none');
        updateStats();
        updateAllocationTracker();
    }

    function bindRemove(row) {
        const btn = row.querySelector('.btn-remove-row');
        if (btn) {
            btn.addEventListener('click', function() { removeRow(btn); });
        }
    }

    function highlightRow(row) {
        const typeInput = row.querySelector('select[id$="-sub_type"]') || row.querySelector('input[id$="-sub_type"]');
        if (!typeInput) return;
        row.classList.remove('row-finished', 'row-injection');
        if (typeInput.value === 'FINISHED') row.classList.add('row-finished');
        else if (typeInput.value === 'FOR_INJECTION') row.classList.add('row-injection');
    }

    function bindChange(row) {
        const inputs = row.querySelectorAll('select, input');
        inputs.forEach(function(input) {
            input.addEventListener('change', function() {
                updateStats();
                updateAllocationTracker();
                highlightRow(row);
            });
            input.addEventListener('input', function() {
                updateStats();
                updateAllocationTracker();
            });
        });
        highlightRow(row);
    }

    // 初始化
    document.querySelectorAll('.split-row').forEach(function(row) {
        bindRemove(row);
        bindChange(row);
    });

    if (btnAdd) {
        btnAdd.addEventListener('click', addRow);
    }

    updateStats();
    updateAllocationTracker();

    // 行颜色样式
    var style = document.createElement('style');
    style.textContent = [
        '.split-row.row-finished td { background-color: rgba(46, 184, 92, 0.04) !important; }',
        '.split-row.row-injection td { background-color: rgba(246, 109, 68, 0.04) !important; }',
    ].join('\n');
    document.head.appendChild(style);
})();
