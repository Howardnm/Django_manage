/**
 * TomSelect 远程搜索 — 通用初始化函数
 *
 * 消除项目中散落在各 JS 文件 / 模板内联脚本中的重复初始化代码。
 * 约定优于配置：优先从 HTML data-* 属性读取配置，可通过 opts 覆盖。
 *
 * HTML 约定（均为可选，缺省使用下方默认值）：
 *   <select class="remote-search"
 *           data-model="project"
 *           data-api-url="/trial-production/api/search/"
 *           data-value-field="id"
 *           data-response-key="results"
 *           placeholder="检索项目名称"></select>
 *
 * @param {Element} el      - 带 .remote-search 类的 <select> 元素
 * @param {Object}  [opts]  - 可选覆盖项：
 *   {string}  apiUrl       - API 端点（默认读取 data-api-url 属性）
 *   {string}  valueField   - 值字段名（默认 'value'）
 *   {string}  responseKey  - JSON 响应中结果数组的 key（默认 null = 直接传整个数组）
 *   {boolean} multi        - 多选模式（默认 false，可从 class .tomselect-multi-remote 自动检测）
 *   {string}  placeholder  - 占位文本（默认读取元素 placeholder 属性）
 */
function initRemoteTomSelect(el, opts) {
    if (!window.TomSelect) return;
    if (el.tomselect) return; // 防止重复初始化

    opts = opts || {};

    var modelType = el.getAttribute('data-model');
    if (!modelType) return;

    // ── 配置解析：约定优于配置 ──
    var apiUrl = opts.apiUrl || el.getAttribute('data-api-url') || '';
    var valueField = opts.valueField || el.getAttribute('data-value-field') || 'value';
    var responseKey = opts.responseKey !== undefined ? opts.responseKey : (el.getAttribute('data-response-key') || null);
    var isMulti = opts.multi || el.classList.contains('tomselect-multi-remote');
    var placeholder = opts.placeholder || el.getAttribute('placeholder') || '请输入关键词搜索...';

    // ── 构造 TomSelect 配置 ──
    var config = {
        valueField: valueField,
        labelField: 'text',
        searchField: 'text',
        copyClassesToDropdown: false,
        create: false,
        preload: 'focus',
        placeholder: placeholder,
        onDropdownOpen: function () {
            if (this.dropdown_content) {
                this.dropdown_content.style.maxHeight = '22rem';
            }
        },
        load: function (query, callback) {
            var url = apiUrl + '?model=' + modelType + '&q=' + encodeURIComponent(query);
            fetch(url)
                .then(function (r) { return r.json(); })
                .then(function (json) {
                    callback(responseKey ? json[responseKey] : json);
                })
                .catch(function () { callback(); });
        },
        render: {
            option: function (data, escape) {
                return '<div>' + escape(data.text) + '</div>';
            },
            item: function (data, escape) {
                return '<div>' + escape(data.text) + '</div>';
            },
            no_results: function () {
                return '<div class="no-results p-2 text-muted small">无匹配结果</div>';
            },
            loading: function () {
                return '<div class="spinner-border spinner-border-sm text-muted m-2"></div>';
            }
        }
    };

    // ── 多选模式 ──
    if (isMulti) {
        config.mode = 'multi';
        config.plugins = ['remove_button'];
    }

    new TomSelect(el, config);
}


/**
 * 批量初始化容器内所有 .remote-search 元素
 *
 * @param {Element} container - 父容器 DOM 元素
 * @param {Object}  [opts]    - 传递给 initRemoteTomSelect 的配置
 */
function initRemoteTomSelectAll(container, opts) {
    container.querySelectorAll('.remote-search').forEach(function (el) {
        initRemoteTomSelect(el, opts);
    });
}


/**
 * 销毁容器内所有 TomSelect 实例（用于 HTMX beforeSwap 等场景）
 *
 * @param {Element} container - 父容器 DOM 元素
 */
function destroyTomSelectAll(container) {
    container.querySelectorAll('.remote-search').forEach(function (el) {
        if (el.tomselect) {
            el.tomselect.destroy();
        }
    });
}
