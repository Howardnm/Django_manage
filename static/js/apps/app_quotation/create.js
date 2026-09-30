/**
 * 发起报价页 — 远程搜索 TomSelect 初始化 + SAP 编码联动自动填充
 *
 * 只初始化 .remote-search（finished_material / customer），
 * 各自读 data-model + data-api-url，URL 不硬编码在 JS 里。
 * 本地 TomSelect（.form-select-search）由 base.html 全局 init 兜底。
 *
 * 联动：选择「SAP编码」后，从 material_sap 自动补全结果里取
 * grade_name / type_name，回填「产品名称」「产品类型」只读框。
 */
(function () {
    'use strict';
    if (!window.TomSelect) return;

    // 1. 初始化远程搜索
    document.querySelectorAll('.remote-search').forEach(function (el) {
        window.initRemoteTomSelect(el);
    });

    // 2. SAP编码 → 自动填 产品名称 / 产品类型
    var sapSelect = document.querySelector('select[name="finished_material"]');
    var nameInput = document.querySelector('input[name="product_name"]');
    var typeInput = document.querySelector('input[name="product_type"]');
    if (sapSelect) {
        sapSelect.addEventListener('change', function () {
            var ts = sapSelect.tomselect;
            var value = ts ? ts.getValue() : sapSelect.value;
            var opt = (ts && ts.options) ? ts.options[value] : null;
            if (nameInput) nameInput.value = (opt && opt.grade_name) || '';
            if (typeInput) typeInput.value = (opt && opt.type_name) || '';
        });
    }
})();
