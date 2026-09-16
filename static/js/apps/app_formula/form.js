/* ==========================================
   配方表单交互逻辑 — app_formula/form.html
   依赖: TomSelect (via tomselect_remote.js), Coloris
   数据桥接:
     - window.testConfigMeta           (模板注入)
     - window.FORMULA_MATERIAL_API_URL (模板注入)
     - window.FORMULA_REPO_API_URL     (模板注入)
     - #variant-data json_script       (模板注入，可选)
   ========================================== */

/* ── 测试项：根据配置类型切换值输入控件 ── */
function toggleValueInput(selectElement) {
    const row = selectElement.closest('tr');
    const valueInputs = row.querySelectorAll('.value-number');
    const textInputs = row.querySelectorAll('.value-text');
    const selectInputs = row.querySelectorAll('.value-select');
    const configId = selectElement.value;

    if (!configId) return;
    const meta = window.testConfigMeta[configId] || {type: 'NUMBER', options: []};

    valueInputs.forEach(el => el.style.display = 'none');
    textInputs.forEach(el => el.style.display = 'none');
    selectInputs.forEach(el => el.style.display = 'none');

    if (meta.type === 'NUMBER') {
        valueInputs.forEach(el => el.style.display = 'block');
        if (selectElement.dataset.initialized === 'true') {
            textInputs.forEach(el => el.value = '');
            selectInputs.forEach(el => el.value = '');
        }
    } else if (meta.type === 'TEXT') {
        textInputs.forEach(el => el.style.display = 'block');
        if (selectElement.dataset.initialized === 'true') {
            valueInputs.forEach(el => el.value = '');
            selectInputs.forEach(el => el.value = '');
        }
    } else if (meta.type === 'SELECT') {
        selectInputs.forEach(el => {
            el.style.display = 'block';
            if (el.options.length <= 1) {
                const currentValue = el.getAttribute('data-current-value') || el.value;
                el.innerHTML = '';
                const emptyOpt = document.createElement('option');
                emptyOpt.value = '';
                emptyOpt.text = '---------';
                el.appendChild(emptyOpt);
                meta.options.forEach(opt => {
                    const option = document.createElement('option');
                    option.value = opt;
                    option.text = opt;
                    if (opt === currentValue) option.selected = true;
                    el.appendChild(option);
                });
            }
        });
        if (selectElement.dataset.initialized === 'true') {
            valueInputs.forEach(el => el.value = '');
            textInputs.forEach(el => el.value = '');
        }
    }
    selectElement.dataset.initialized = 'true';
}

/* ── BOM 比例总和实时计算 ── */
function updateBomSums() {
    var numCols = parseInt(document.getElementById('num_columns').value) || 1;
    var sumColumns = document.getElementById('bom-sum-columns');
    if (!sumColumns) return;

    for (var c = 0; c < numCols; c++) {
        var sum = 0;
        var selector = c === 0
            ? '#bom-formset input[name$="-percentage"]'
            : '#bom-formset input[name$="-percentage_col' + c + '"]';
        document.querySelectorAll(selector).forEach(function (input) {
            var row = input.closest('tr.bom-form');
            if (row && row.style.display !== 'none') {
                var val = parseFloat(input.value);
                if (!isNaN(val)) sum += val;
            }
        });
        var sumEl = document.getElementById('bom-sum-' + c);
        if (sumEl) {
            sumEl.textContent = sum.toFixed(2);
            sumEl.classList.remove('text-success', 'text-warning', 'text-danger');
            if (sum > 0 && Math.abs(sum - 100) < 0.005) {
                sumEl.classList.add('text-success');
            } else if (sum > 0 && Math.abs(sum - 100) < 5) {
                sumEl.classList.add('text-warning');
            } else if (sum > 0) {
                sumEl.classList.add('text-danger');
            }
        }
    }
}

document.addEventListener('DOMContentLoaded', function () {
    /* ── 远程搜索 TomSelect 初始化 ── */
    if (window.TomSelect) {
        document.querySelectorAll('.remote-search').forEach(function (el) {
            var modelType = el.getAttribute('data-model');
            var apiUrl = window.FORMULA_MATERIAL_API_URL;
            if (['customer', 'oem', 'salesperson'].includes(modelType)) {
                apiUrl = window.FORMULA_REPO_API_URL;
            }
            initRemoteTomSelect(el, {apiUrl: apiUrl});
        });
    }

    /* ── 多列变体管理 ── */
    let currentNumColumns = parseInt(document.getElementById('num_columns').value) || 1;

    function getBomPrefix(rowEl) {
        var inputs = rowEl.querySelectorAll('input, select');
        for (var i = 0; i < inputs.length; i++) {
            var m = inputs[i].name.match(/^bom-(\d+)-/);
            if (m) return m[1];
        }
        return '__prefix__';
    }

    function getTestPrefix(rowEl) {
        var inputs = rowEl.querySelectorAll('input, select');
        for (var i = 0; i < inputs.length; i++) {
            var m = inputs[i].name.match(/^test-(\d+)-/);
            if (m) return m[1];
        }
        return '__prefix__';
    }

    function makePctHTML(prefix, colIdx) {
        if (colIdx === 0) {
            return '<input type="number" name="bom-' + prefix + '-percentage" step="0.01" class="form-control" id="id_bom-' + prefix + '-percentage">';
        }
        return '<input type="number" name="bom-' + prefix + '-percentage_col' + colIdx + '" step="0.01" class="form-control">';
    }

    function makeValueHTML(prefix, colIdx) {
        if (colIdx === 0) {
            return '<input type="number" name="test-' + prefix + '-value" step="0.001" class="form-control value-number" id="id_test-' + prefix + '-value">' +
                '<input type="text" name="test-' + prefix + '-value_text" class="form-control value-text" style="display:none;" id="id_test-' + prefix + '-value_text">' +
                '<select name="test-' + prefix + '-value_select" class="form-select value-select" style="display:none;" id="id_test-' + prefix + '-value_select"><option value="">---------</option></select>';
        }
        return '<input type="number" name="test-' + prefix + '-value_col' + colIdx + '" step="0.001" class="form-control value-number">' +
            '<input type="text" name="test-' + prefix + '-value_text_col' + colIdx + '" class="form-control value-text" style="display:none;">' +
            '<select name="test-' + prefix + '-value_select_col' + colIdx + '" class="form-select value-select" style="display:none;"><option value="">---------</option></select>';
    }

    /* 列注册表：每列一个隐藏域，DOM 顺序即列序，值 = 该列对应的配方版本 pk（空串 = 新版本）。
       后端只认这个顺序，列数也以它为准。 */
    function registryInputs() {
        var registry = document.getElementById('column-registry');
        if (!registry) return [];
        return Array.prototype.slice.call(
            registry.querySelectorAll('input[name="column_formula_ids"]'));
    }

    function columnCount() {
        var sumColumns = document.getElementById('bom-sum-columns');
        return sumColumns ? sumColumns.querySelectorAll('.percentage-col').length : 1;
    }

    /* 按列在 DOM 中的实际位置重写所有后缀：data-col、input 的 name/id、表尾合计 id。
       删除中间列后必须调用，否则第 2 列之后的数据会被写到错位的版本上。
       只改属性、不重建 DOM，因此用户已填的值不会丢。 */
    function reindexColumns() {
        document.querySelectorAll('#bom-formset tr.bom-form').forEach(function (row) {
            var prefix = getBomPrefix(row);
            row.querySelectorAll('.percentage-columns > .percentage-col').forEach(function (col, i) {
                col.setAttribute('data-col', i);
                var input = col.querySelector('input[name*="percentage"]');
                if (!input) return;
                if (i === 0) {
                    input.name = 'bom-' + prefix + '-percentage';
                    input.id = 'id_bom-' + prefix + '-percentage';
                } else {
                    input.name = 'bom-' + prefix + '-percentage_col' + i;
                    input.removeAttribute('id');
                }
            });
        });

        document.querySelectorAll('#test-formset tr.test-form').forEach(function (row) {
            var prefix = getTestPrefix(row);
            row.querySelectorAll('.value-columns > .value-col').forEach(function (col, i) {
                col.setAttribute('data-col', i);
                var suffix = i === 0 ? '' : '_col' + i;
                var idPart = i === 0 ? 'id_test-' + prefix + '-' : null;
                [['.value-number', 'value'], ['.value-text', 'value_text'], ['.value-select', 'value_select']]
                    .forEach(function (pair) {
                        var el = col.querySelector(pair[0]);
                        if (!el) return;
                        el.name = 'test-' + prefix + '-' + pair[1] + suffix;
                        if (idPart) el.id = idPart + pair[1];
                        else el.removeAttribute('id');
                    });
            });
        });

        var sumColumns = document.getElementById('bom-sum-columns');
        if (sumColumns) {
            sumColumns.querySelectorAll(':scope > .percentage-col').forEach(function (col, i) {
                col.setAttribute('data-col', i);
                var value = col.querySelector('.bom-sum-value');
                if (value) value.id = 'bom-sum-' + i;
            });
        }

        ['#bom-column-heads', '#test-column-heads'].forEach(function (selector) {
            var heads = document.querySelector(selector);
            if (!heads) return;
            heads.querySelectorAll(':scope > .percentage-col, :scope > .value-col').forEach(function (col, i) {
                col.setAttribute('data-col', i);
                var btn = col.querySelector('.remove-pct-col');
                if (btn) btn.setAttribute('data-col', i);
            });
        });

        currentNumColumns = columnCount();
        document.getElementById('num_columns').value = currentNumColumns;
        updateBomSums();
    }

    function appendColumnHeads(colIdx) {
        var bomHeads = document.getElementById('bom-column-heads');
        if (bomHeads) {
            var div = document.createElement('div');
            div.className = 'percentage-col text-center';
            div.setAttribute('data-col', colIdx);
            div.innerHTML = '<span class="badge bg-orange-lt text-orange" title="尚未保存的新版本">新</span>' +
                '<button type="button" class="btn btn-sm btn-ghost-danger btn-icon remove-pct-col" data-col="' +
                colIdx + '" title="移除该版本"><i class="ti ti-x"></i></button>';
            bomHeads.appendChild(div);
        }
        var testHeads = document.getElementById('test-column-heads');
        if (testHeads) {
            var tDiv = document.createElement('div');
            tDiv.className = 'value-col text-center';
            tDiv.setAttribute('data-col', colIdx);
            tDiv.innerHTML = '<span class="badge bg-orange-lt text-orange" title="尚未保存的新版本">新</span>';
            testHeads.appendChild(tDiv);
        }
    }

    function addColumn() {
        var colIdx = columnCount();

        var registry = document.getElementById('column-registry');
        if (registry) {
            var hidden = document.createElement('input');
            hidden.type = 'hidden';
            hidden.name = 'column_formula_ids';
            hidden.value = '';
            registry.appendChild(hidden);
        }

        document.querySelectorAll('#bom-formset tr.bom-form').forEach(function (row) {
            var div = document.createElement('div');
            div.className = 'percentage-col';
            div.setAttribute('data-col', colIdx);
            div.style.cssText = 'flex:0 0 70px; min-width:70px;';
            div.innerHTML = makePctHTML(getBomPrefix(row), colIdx);
            row.querySelector('.percentage-columns').appendChild(div);
        });

        document.querySelectorAll('#test-formset tr.test-form').forEach(function (row) {
            var div = document.createElement('div');
            div.className = 'value-col';
            div.setAttribute('data-col', colIdx);
            div.style.cssText = 'flex:0 0 105px; min-width:105px;';
            div.innerHTML = makeValueHTML(getTestPrefix(row), colIdx);
            row.querySelector('.value-columns').appendChild(div);
        });

        var sumColumns = document.getElementById('bom-sum-columns');
        if (sumColumns) {
            var sumDiv = document.createElement('div');
            sumDiv.className = 'percentage-col';
            sumDiv.setAttribute('data-col', colIdx);
            sumDiv.style.cssText = 'flex:0 0 70px; min-width:70px;';
            sumDiv.innerHTML = '<span class="bom-sum-value fw-bold" id="bom-sum-' + colIdx + '" style="font-size:13px;">0</span>';
            sumColumns.appendChild(sumDiv);
        }

        appendColumnHeads(colIdx);
        reindexColumns();
        updateRemoveBtn();
    }

    /* 删除任意一列（不只是最后一列），随后整体重排后缀 */
    function removeColumnAt(colIdx) {
        if (columnCount() <= 1) {
            window.alert('至少需要保留一个配方版本');
            return;
        }
        var selector = '[data-col="' + colIdx + '"]';
        document.querySelectorAll('.percentage-columns > .percentage-col' + selector)
            .forEach(function (el) { el.remove(); });
        document.querySelectorAll('.value-columns > .value-col' + selector)
            .forEach(function (el) { el.remove(); });
        ['#bom-column-heads', '#test-column-heads'].forEach(function (sel) {
            var heads = document.querySelector(sel);
            if (heads) heads.querySelectorAll(':scope > ' + selector).forEach(function (el) { el.remove(); });
        });
        var sumColumns = document.getElementById('bom-sum-columns');
        if (sumColumns) {
            sumColumns.querySelectorAll(':scope > .percentage-col' + selector)
                .forEach(function (el) { el.remove(); });
        }
        var inputs = registryInputs();
        if (inputs[colIdx]) inputs[colIdx].remove();

        reindexColumns();
        updateRemoveBtn();
    }

    function removeColumn() {
        removeColumnAt(columnCount() - 1);
    }

    function updateRemoveBtn() {
        var btn = document.getElementById('remove-pct-col');
        if (btn) {
            if (columnCount() <= 1) { btn.classList.add('d-none'); }
            else { btn.classList.remove('d-none'); }
        }
    }

    function fillRowColumns(rowEl, prefix) {
        var pctContainer = rowEl.querySelector('.percentage-columns');
        var valContainer = rowEl.querySelector('.value-columns');
        if (!pctContainer && !valContainer) return;

        for (var c = 0; c < currentNumColumns; c++) {
            if (pctContainer) {
                var pDiv = document.createElement('div');
                pDiv.className = 'percentage-col';
                pDiv.setAttribute('data-col', c);
                pDiv.style.cssText = 'flex:0 0 70px; min-width:70px;';
                pDiv.innerHTML = makePctHTML(prefix, c);
                pctContainer.appendChild(pDiv);
            }
            if (valContainer) {
                var vDiv = document.createElement('div');
                vDiv.className = 'value-col';
                vDiv.setAttribute('data-col', c);
                vDiv.style.cssText = 'flex:0 0 105px; min-width:105px;';
                vDiv.innerHTML = makeValueHTML(prefix, c);
                valContainer.appendChild(vDiv);
            }
        }
    }

    var addPctColBtn = document.getElementById('add-pct-col');
    var removePctColBtn = document.getElementById('remove-pct-col');
    if (addPctColBtn) addPctColBtn.addEventListener('click', addColumn);
    if (removePctColBtn) removePctColBtn.addEventListener('click', removeColumn);

    // 每列表头的「移除该版本」按钮（列头是服务端渲染的，用事件委托）
    document.addEventListener('click', function (e) {
        var btn = e.target.closest('.remove-pct-col');
        if (!btn) return;
        var colIdx = parseInt(btn.getAttribute('data-col'), 10);
        if (!isNaN(colIdx)) removeColumnAt(colIdx);
    });

    /* ── 表单集动态行管理 ── */
    function setupFormSet(prefix, btnId, containerId, templateId) {
        var addBtn = document.getElementById(btnId);
        var totalForms = document.getElementById('id_' + prefix + '-TOTAL_FORMS');
        var container = document.getElementById(containerId);
        var templateEl = document.getElementById(templateId);
        // L3（已投产）编辑页整页只读：添加行按钮与空模板都不渲染，直接跳过绑定
        if (!addBtn || !totalForms || !container || !templateEl) return;
        var template = templateEl.innerHTML;

        addBtn.addEventListener('click', function () {
            var count = parseInt(totalForms.value);
            var newRow = template.replace(/__prefix__/g, count);
            container.insertAdjacentHTML('beforeend', newRow);
            totalForms.value = count + 1;

            var newRowElement = container.lastElementChild;
            fillRowColumns(newRowElement, count);

            if (window.TomSelect) {
                initLocalTomSelectAll(newRowElement, {
                    onChange: function () { toggleValueInput(this.input); }
                });

                newRowElement.querySelectorAll('.remote-search').forEach(function (el) {
                    var modelType = el.getAttribute('data-model');
                    var apiUrl = window.FORMULA_MATERIAL_API_URL;
                    if (['customer', 'oem', 'salesperson'].includes(modelType)) {
                        apiUrl = window.FORMULA_REPO_API_URL;
                    }
                    initRemoteTomSelect(el, {apiUrl: apiUrl});
                });
            }
            updateBomSums();
        });
    }

    setupFormSet('bom', 'add-bom', 'bom-formset', 'bom-empty-form');
    setupFormSet('test', 'add-test', 'test-formset', 'test-empty-form');

    /* ── 测试项初始值类型切换 ── */
    setTimeout(function () {
        document.querySelectorAll('.form-select-search').forEach(function (select) {
            if (select.value) {
                const row = select.closest('tr');
                const configId = select.value;
                const meta = window.testConfigMeta[configId];
                if (meta && meta.type === 'SELECT') {
                    row.querySelectorAll('.value-col').forEach(function (col) {
                        const textInput = col.querySelector('.value-text');
                        const selectInput = col.querySelector('.value-select');
                        if (textInput && selectInput && textInput.value) {
                            selectInput.setAttribute('data-current-value', textInput.value);
                        }
                    });
                }
                toggleValueInput(select);
            }
        });
    }, 100);

    /* ── BOM 百分比实时求和：事件委托 ── */
    var bomFormset = document.getElementById('bom-formset');
    if (bomFormset) {
        bomFormset.addEventListener('input', function (e) {
            if (e.target.matches('input[type="number"]') && e.target.name.indexOf('percentage') !== -1) {
                updateBomSums();
            }
        });
    }

    // 首次计算
    updateBomSums();

    /* ── 保存前确认：版本结构变更会连带删除引用本实验单的草稿工单 ──
       仅在前端做提示，真正的判定与执行都在服务端（FormulaEditPolicy）。 */
    (function () {
        var policyEl = document.getElementById('edit-policy');
        var mainForm = document.querySelector('form');
        if (!policyEl || !mainForm) return;

        var policy;
        try { policy = JSON.parse(policyEl.textContent); } catch (err) { return; }
        var orderCodes = (policy && policy.removable_order_codes) || [];
        if (!orderCodes.length) return;

        var initialIds = registryInputs().map(function (el) { return el.value; });

        mainForm.addEventListener('submit', function (e) {
            var currentIds = registryInputs().map(function (el) { return el.value; });
            var changed = currentIds.length !== initialIds.length ||
                currentIds.some(function (value, i) { return value !== initialIds[i]; });
            if (!changed) return;

            var message = '配方版本结构已变更。保存后，以下引用本实验单的草稿工单会被一并删除，' +
                '需要按新结构重新建单：\n\n' + orderCodes.join('、') + '\n\n确定继续保存吗？';
            if (!window.confirm(message)) e.preventDefault();
        });
    })();

    /* ── 表单验证错误恢复：重建多列并回填数据 ── */
    if (currentNumColumns > 1) {
        for (var c = 1; c < currentNumColumns; c++) {
            (function (colIdx) {
                document.querySelectorAll('#bom-formset tr.bom-form').forEach(function (row) {
                    var prefix = getBomPrefix(row);
                    var container = row.querySelector('.percentage-columns');
                    var div = document.createElement('div');
                    div.className = 'percentage-col';
                    div.setAttribute('data-col', colIdx);
                    div.style.cssText = 'flex:0 0 70px; min-width:70px;';
                    div.innerHTML = makePctHTML(prefix, colIdx);
                    container.appendChild(div);
                });
                document.querySelectorAll('#test-formset tr.test-form').forEach(function (row) {
                    var prefix = getTestPrefix(row);
                    var container = row.querySelector('.value-columns');
                    var div = document.createElement('div');
                    div.className = 'value-col';
                    div.setAttribute('data-col', colIdx);
                    div.style.cssText = 'flex:0 0 105px; min-width:105px;';
                    div.innerHTML = makeValueHTML(prefix, colIdx);
                    container.appendChild(div);
                });
            })(c);
        }
        updateRemoveBtn();

        // 重建 tfoot 中的多列合计单元格
        var sumColumns = document.getElementById('bom-sum-columns');
        if (sumColumns) {
            for (var c2 = 1; c2 < currentNumColumns; c2++) {
                (function (colIdx) {
                    var sumDiv = document.createElement('div');
                    sumDiv.className = 'percentage-col';
                    sumDiv.setAttribute('data-col', colIdx);
                    sumDiv.style.cssText = 'flex:0 0 70px; min-width:70px;';
                    sumDiv.innerHTML = '<span class="bom-sum-value fw-bold" id="bom-sum-' + colIdx + '" style="font-size:13px;">0</span>';
                    sumColumns.appendChild(sumDiv);
                })(c2);
            }
        }

        // 归一化所有后缀（name/id/data-col/表尾合计 id），并同步 #num_columns
        reindexColumns();

        // 回填变体数据
        var variantDataEl = document.getElementById('variant-data');
        if (variantDataEl) {
            try {
                var vd = JSON.parse(variantDataEl.textContent);
                for (var key in vd) {
                    var el = document.querySelector('[name="' + key + '"]');
                    if (el) el.value = vd[key];
                }
                updateBomSums();
            } catch (e) {
                // variant data parse error — silently ignore
            }
        }
    }
});

/* ── Coloris 颜色选择器初始化 ── */
if (typeof Coloris !== 'undefined') {
    Coloris.init();
    Coloris({
        el: '[data-coloris]',
        theme: 'default',
        themeMode: 'light',
        format: 'hex',
        alpha: false,
        clearButton: true,
        clearLabel: '清除',
        closeButton: true,
        closeLabel: '关闭',
    });
}

/* ── 删除行按钮（全局事件委托）── */
document.addEventListener('click', function (e) {
    var btn = e.target.closest('.delete-row-btn');
    if (!btn) return;
    var row = btn.closest('tr');
    var checkbox = row.querySelector('input[type=checkbox][name$="-DELETE"]');
    if (checkbox) checkbox.checked = true;
    row.style.display = 'none';
    updateBomSums();
});
