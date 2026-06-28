/**
 * 通用搜索选择器模态框 v3 — includes/search_picker_modal.html
 *
 * 配置流：Python SearchPickerConfig.to_json() → 模板 <script> 注入 → JS 解析
 * 依赖：Bootstrap 5 modal, Tabler Icons, tomselect_remote.js（全局）
 *
 * 架构（5 个内部类，IIFE 包裹）：
 *   SearchPickerConfig      — 解析/校验 JSON 配置
 *   SearchPickerFieldBuilder — 多字段 DOM + TomSelect 初始化 + 值收集
 *   SearchPickerAPI          — fetch 请求 + 响应标准化
 *   SearchPickerRenderer     — 列表/表格/状态/分页 渲染 + 高亮
 *   SearchPicker             — 编排器：事件绑定、生命周期、键盘导航
 */
(function () {
    'use strict';

    // ═══════════════════════════════════════════════
    // SearchPickerConfig — 配置解析
    // ═══════════════════════════════════════════════

    function SearchPickerConfig(raw) {
        raw = raw || {};

        // ── 核心配置 ──
        this.searchUrl = raw.searchUrl || '';
        this.searchModel = raw.searchModel || '';
        this.displayMode = raw.displayMode || 'list';
        this.searchMode = raw.searchMode || 'simple';
        this.pageSize = parseInt(raw.pageSize, 10) || 8;
        this.showDetailButton = !!raw.showDetailButton;
        this.placeholder = raw.placeholder || '输入关键词搜索...';
        this.confirmText = raw.confirmText || '确认选择';
        this.initialSearch = !!raw.initialSearch;

        // ── 表格列定义 ──
        this.tableColumns = raw.tableColumns || [];

        // ── 多字段定义 ──
        this.searchFields = raw.searchFields || [];

        // ── 响应映射（优先级：JSON 显式设置 > 默认值） ──
        var rm = raw.responseMapping || {};
        this.resultsKey = rm.resultsKey !== undefined ? rm.resultsKey : 'results';
        this.totalKey = rm.totalKey || 'total';
        this.pageKey = rm.pageKey || 'page';
        this.pageSizeKey = rm.pageSizeKey || 'page_size';
        this.hasNextKey = rm.hasNextKey || 'has_next';
        this.hasPrevKey = rm.hasPrevKey || 'has_prev';
        this.valueField = rm.valueField || 'value';
        this.textField = rm.textField || 'text';
    }


    // ═══════════════════════════════════════════════
    // SearchPickerFieldBuilder — 多字段 DOM + TomSelect
    // ═══════════════════════════════════════════════

    function SearchPickerFieldBuilder(fieldsConfig, defaultSearchUrl, modalId) {
        this.fieldsConfig = fieldsConfig || [];
        this.defaultSearchUrl = defaultSearchUrl || '';
        this._modalId = modalId || 'searchpicker';
    }

    SearchPickerFieldBuilder.prototype.build = function (container) {
        if (!container || !this.fieldsConfig.length) return;

        var self = this;
        container.innerHTML = '';

        this.fieldsConfig.forEach(function (field) {
            var wrapper = document.createElement('div');
            wrapper.className = 'search-picker-field';

            if (field.label) {
                var label = document.createElement('label');
                label.textContent = field.label;
                wrapper.appendChild(label);
            }

            var el;
            switch (field.type) {
                case 'select':
                    el = self._buildSelect(field);
                    break;
                case 'remote-select':
                    el = self._buildRemoteSelect(field, false);
                    break;
                case 'remote-multi':
                    el = self._buildRemoteSelect(field, true);
                    break;
                case 'date':
                    el = self._buildInput(field, 'date');
                    break;
                case 'user':
                    el = self._buildUserPicker(field);
                    break;
                default:  // text
                    el = self._buildInput(field, 'text');
                    break;
            }
            if (el) wrapper.appendChild(el);
            container.appendChild(wrapper);
        });

        // 搜索按钮
        var btnWrapper = document.createElement('div');
        btnWrapper.className = 'search-picker-field search-picker-field-btn';
        var searchBtn = document.createElement('button');
        searchBtn.type = 'button';
        searchBtn.className = 'btn btn-primary search-multi-btn';
        searchBtn.innerHTML = '<i class="ti ti-search me-1"></i>搜索';
        btnWrapper.appendChild(searchBtn);
        container.appendChild(btnWrapper);
    };

    SearchPickerFieldBuilder.prototype._buildInput = function (field, type) {
        var input = document.createElement('input');
        input.type = type;
        input.className = 'form-control';
        input.setAttribute('data-field-name', field.name);
        if (field.placeholder) input.placeholder = field.placeholder;
        if (type === 'text') input.autocomplete = 'off';
        return input;
    };

    SearchPickerFieldBuilder.prototype._buildSelect = function (field) {
        var sel = document.createElement('select');
        sel.className = 'form-select form-select-search';
        sel.setAttribute('data-field-name', field.name);
        if (field.placeholder) sel.setAttribute('placeholder', field.placeholder);
        if (field.options) {
            field.options.forEach(function (opt) {
                var o = document.createElement('option');
                o.value = opt.value;
                o.textContent = opt.text;
                sel.appendChild(o);
            });
        }
        return sel;
    };

    SearchPickerFieldBuilder.prototype._buildRemoteSelect = function (field, isMulti) {
        var sel = document.createElement('select');
        sel.className = 'form-select remote-search';
        if (isMulti) {
            sel.className += ' tomselect-multi-remote';
            sel.setAttribute('multiple', '');
        }
        sel.setAttribute('data-field-name', field.name);
        if (field.model) sel.setAttribute('data-model', field.model);
        if (field.api_url) sel.setAttribute('data-api-url', field.api_url);
        if (field.placeholder) sel.setAttribute('placeholder', field.placeholder);
        if (field.value_field) sel.setAttribute('data-value-field', field.value_field);
        if (field.response_key) sel.setAttribute('data-response-key', field.response_key);
        return sel;
    };

    // ── user picker 字段 ──

    SearchPickerFieldBuilder.prototype._buildUserPicker = function (field) {
        var self = this;
        var wrapper = document.createElement('div');
        wrapper.className = 'search-picker-field-user';

        // 隐藏字段：存储选中用户的 ID（逗号分隔）
        var hiddenInput = document.createElement('input');
        hiddenInput.type = 'hidden';
        hiddenInput.setAttribute('data-field-name', field.name);

        // 只读显示字段：展示选中用户名
        var displayInput = document.createElement('input');
        displayInput.type = 'text';
        displayInput.className = 'form-control';
        displayInput.readOnly = true;
        displayInput.placeholder = field.placeholder || '点击选择人员...';
        displayInput.setAttribute('data-display-for', field.name);

        // 选择按钮
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-outline-secondary';
        btn.textContent = '选择人员';

        // 唯一 picker ID（每个 modal 实例的每个字段唯一）
        var pickerId = (self._modalId || 'searchpicker') + '__' + field.name;

        btn.addEventListener('click', function () {
            // 确保 overlay 在 body 下存在（调用 user_picker_modal.js 的全局函数）
            if (typeof window.ensureUserPickerOverlay === 'function') {
                window.ensureUserPickerOverlay(pickerId, {title: field.label || '选择人员'});
            }

            var isMulti = !!field.multi;
            window.openUserPicker(pickerId, function (result) {
                if (isMulti) {
                    // 多选：result = { users: [{id, label}, ...] }
                    var ids = result.users.map(function (u) { return u.id; });
                    var labels = result.users.map(function (u) { return u.label; });
                    hiddenInput.value = ids.join(',');
                    displayInput.value = labels.length > 0 ? labels.length + '人已选' : '';
                } else {
                    // 单选：result = { id, label }
                    hiddenInput.value = result.id;
                    displayInput.value = result.label;
                }
            }, { multi: isMulti, title: field.label || '选择人员', dynamic: true });
        });

        wrapper.appendChild(hiddenInput);
        wrapper.appendChild(displayInput);
        wrapper.appendChild(btn);
        return wrapper;
    };

    SearchPickerFieldBuilder.prototype.initTomSelects = function (container) {
        var self = this;
        if (!container) return;

        // 等 DOM 渲染完再初始化 TomSelect
        setTimeout(function () {
            // 本地搜索 select
            if (typeof initLocalTomSelectAll === 'function') {
                initLocalTomSelectAll(container);
            }

            // 远程搜索 select — 逐个初始化
            container.querySelectorAll('.remote-search').forEach(function (el) {
                if (typeof initRemoteTomSelect !== 'function') return;
                var apiUrl = el.getAttribute('data-api-url') || self.defaultSearchUrl;
                var opts = { apiUrl: apiUrl };
                if (el.classList.contains('tomselect-multi-remote')) {
                    opts.multi = true;
                }
                if (el.getAttribute('data-value-field')) {
                    opts.valueField = el.getAttribute('data-value-field');
                }
                if (el.getAttribute('data-response-key')) {
                    opts.responseKey = el.getAttribute('data-response-key');
                }
                initRemoteTomSelect(el, opts);
            });
        }, 50);
    };

    SearchPickerFieldBuilder.prototype.collectValues = function (container) {
        var params = {};
        if (!container) return params;

        container.querySelectorAll('[data-field-name]').forEach(function (el) {
            var name = el.getAttribute('data-field-name');
            var val = '';
            if (el.tomselect) {
                var tsVal = el.tomselect.getValue();
                if (Array.isArray(tsVal)) {
                    val = tsVal.join(',');
                } else {
                    val = tsVal || '';
                }
            } else {
                val = el.value.trim();
            }
            if (val) {
                params[name] = val;
            }
        });
        return params;
    };

    SearchPickerFieldBuilder.prototype.clearAll = function (container) {
        if (!container) return;

        container.querySelectorAll('input[type="text"], input[type="date"]').forEach(function (el) {
            el.value = '';
        });
        container.querySelectorAll('input[readonly]').forEach(function (el) {
            el.value = '';
        });
        container.querySelectorAll('input[type="hidden"]').forEach(function (el) {
            el.value = '';
        });
        container.querySelectorAll('select').forEach(function (el) {
            if (el.tomselect) {
                el.tomselect.clear();
            } else {
                el.selectedIndex = 0;
            }
        });
    };


    // ═══════════════════════════════════════════════
    // SearchPickerAPI — fetch + 响应标准化
    // ═══════════════════════════════════════════════

    function SearchPickerAPI(config) {
        this.config = config;
    }

    SearchPickerAPI.prototype.search = function (queryParams, page) {
        var self = this;
        var qs = this._buildQueryString(queryParams, page);

        return fetch(this.config.searchUrl + '?' + qs)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                return self._normalizeResponse(data);
            });
    };

    SearchPickerAPI.prototype._buildQueryString = function (queryParams, page) {
        var params = [];

        // 追加字段参数
        for (var key in queryParams) {
            if (queryParams.hasOwnProperty(key) && queryParams[key]) {
                params.push(encodeURIComponent(key) + '=' + encodeURIComponent(queryParams[key]));
            }
        }

        // 分页参数
        params.push('page=' + page);
        params.push('page_size=' + this.config.pageSize);

        // 搜索模型（仅 simple 模式）
        if (this.config.searchModel && !queryParams.model) {
            params.push('model=' + encodeURIComponent(this.config.searchModel));
        }

        return params.join('&');
    };

    SearchPickerAPI.prototype._normalizeResponse = function (json) {
        var cfg = this.config;

        // resultsKey 为 null 时，响应本身就是数组
        var results = cfg.resultsKey === null ? json : (json[cfg.resultsKey] || []);

        return {
            results: results,
            total: json[cfg.totalKey] !== undefined ? json[cfg.totalKey] : results.length,
            page: json[cfg.pageKey] || 1,
            pageSize: json[cfg.pageSizeKey] || cfg.pageSize,
            hasNext: json[cfg.hasNextKey] !== undefined ? !!json[cfg.hasNextKey] : false,
            hasPrev: json[cfg.hasPrevKey] !== undefined ? !!json[cfg.hasPrevKey] : false
        };
    };


    // ═══════════════════════════════════════════════
    // SearchPickerRenderer — 结果渲染 + 高亮
    // ═══════════════════════════════════════════════

    function SearchPickerRenderer(resultsContainer) {
        this.container = resultsContainer;
    }

    SearchPickerRenderer.prototype.renderResults = function (normalized, config, selectedValue) {
        if (!normalized.results || !normalized.results.length) {
            this.renderStatus('ti-mood-empty', '无匹配结果');
            return;
        }

        if (config.displayMode === 'table') {
            this.renderTable(normalized.results, config, selectedValue);
        } else {
            this.renderList(normalized.results, config, selectedValue);
        }
    };

    SearchPickerRenderer.prototype.renderList = function (results, config, selectedValue) {
        var self = this;
        var html = '<div class="list-group list-group-flush search-picker-list">';

        results.forEach(function (r) {
            var val = r[config.valueField];
            var text = r[config.textField] || val;
            var activeClass = String(val) === String(selectedValue) ? ' active' : '';
            var checkIcon = activeClass ? '<i class="ti ti-check search-picker-check"></i>' : '';
            var detailHtml = '';
            if (config.showDetailButton && r.url) {
                detailHtml = '<span class="search-detail-link ms-2" data-url="' + escapeAttr(r.url) + '" title="查看详情"><i class="ti ti-external-link"></i></span>';
            }
            html += '<a href="#" class="list-group-item list-group-item-action search-result-item' + activeClass + '"' +
                ' data-value="' + escapeAttr(val) + '" data-text="' + escapeAttr(text) + '">' +
                '<div class="d-flex align-items-center">' +
                '<div class="flex-fill text-truncate">' + htmlEscape(text) + '</div>' +
                detailHtml + checkIcon +
                '</div></a>';
        });

        html += '</div>';
        this.container.innerHTML = html;
    };

    SearchPickerRenderer.prototype.renderTable = function (results, config, selectedValue) {
        var columns = config.tableColumns;
        if (!columns.length) return;

        var html = '<div class="search-picker-table-wrapper">' +
            '<table class="table card-table table-vcenter text-nowrap search-picker-table mb-0">' +
            '<thead><tr>';

        columns.forEach(function (col) {
            var width = col.width ? ' style="width:' + col.width + '"' : '';
            html += '<th' + width + '>' + htmlEscape(col.title) + '</th>';
        });
        if (config.showDetailButton) {
            html += '<th style="width:100px"></th>';
        }
        html += '</tr></thead><tbody>';

        results.forEach(function (r) {
            var val = r[config.valueField];
            var isActive = String(val) === String(selectedValue);
            var rowClass = isActive ? ' table-active' : '';

            html += '<tr class="search-result-row' + rowClass + '" data-value="' + escapeAttr(val) + '">';

            columns.forEach(function (col, idx) {
                var cellVal = r[col.key];
                var cellHtml = cellVal !== undefined && cellVal !== null ? htmlEscape(String(cellVal)) : '';
                if (idx === 0 && isActive) {
                    cellHtml += ' <i class="ti ti-check search-picker-check"></i>';
                }
                if (col.monospace) {
                    cellHtml = '<span class="text-monospace">' + cellHtml + '</span>';
                }
                html += '<td>' + cellHtml + '</td>';
            });

            if (config.showDetailButton) {
                if (r.url) {
                    html += '<td><a href="' + escapeAttr(r.url) + '" target="_blank" class="btn btn-sm btn-outline-secondary" ' +
                        'onclick="event.stopPropagation()" title="查看详情">' +
                        '<i class="ti ti-external-link"></i> 查看</a></td>';
                } else {
                    html += '<td><span class="text-muted">&mdash;</span></td>';
                }
            }

            html += '</tr>';
        });

        html += '</tbody></table></div>';
        this.container.innerHTML = html;
    };

    SearchPickerRenderer.prototype.renderStatus = function (iconClass, message) {
        this.container.innerHTML =
            '<div class="search-picker-status">' +
            '<i class="ti ' + iconClass + '"></i>' +
            '<span>' + htmlEscape(message) + '</span>' +
            '</div>';
    };

    SearchPickerRenderer.prototype.renderLoading = function () {
        this.container.innerHTML =
            '<div class="search-picker-spinner">' +
            '<div class="spinner-border spinner-border-sm text-muted"></div>' +
            '</div>';
    };

    SearchPickerRenderer.prototype.renderPagination = function (data, paginationEl, pageInfoEl, prevBtn, nextBtn) {
        if (!paginationEl) return;

        if (data.total <= data.pageSize && data.page <= 1) {
            this.hidePagination(paginationEl);
            return;
        }

        if (pageInfoEl) {
            pageInfoEl.textContent = '第 ' + data.page + ' 页，共 ' + data.total + ' 条';
        }
        if (prevBtn) prevBtn.disabled = !data.hasPrev;
        if (nextBtn) nextBtn.disabled = !data.hasNext;

        paginationEl.classList.add('visible');
    };

    SearchPickerRenderer.prototype.hidePagination = function (paginationEl) {
        if (paginationEl) paginationEl.classList.remove('visible');
    };

    SearchPickerRenderer.prototype.highlightItem = function (value, container, displayMode) {
        var itemSelector = displayMode === 'table' ? '.search-result-row' : '.search-result-item';
        var items = container.querySelectorAll(itemSelector);

        // 清除所有高亮
        items.forEach(function (el) {
            if (displayMode === 'table') {
                el.classList.remove('table-active');
                var check = el.querySelector('.search-picker-check');
                if (check) check.remove();
            } else {
                el.classList.remove('active');
                var check = el.querySelector('.search-picker-check');
                if (check) check.remove();
            }
        });

        // 高亮选中项
        var target = container.querySelector(itemSelector + '[data-value="' + escapeAttr(value) + '"]');
        if (!target) return;

        if (displayMode === 'table') {
            target.classList.add('table-active');
            var firstTd = target.querySelector('td:first-child');
            if (firstTd) {
                var check = document.createElement('i');
                check.className = 'ti ti-check search-picker-check';
                firstTd.appendChild(check);
            }
        } else {
            target.classList.add('active');
            var checkEl = document.createElement('i');
            checkEl.className = 'ti ti-check search-picker-check';
            var flexDiv = target.querySelector('.d-flex');
            if (flexDiv) flexDiv.appendChild(checkEl);
        }
    };

    SearchPickerRenderer.prototype.clearHighlight = function (container, displayMode) {
        var itemSelector = displayMode === 'table' ? '.search-result-row' : '.search-result-item';
        container.querySelectorAll(itemSelector).forEach(function (el) {
            el.classList.remove('active', 'table-active');
            var check = el.querySelector('.search-picker-check');
            if (check) check.remove();
        });
    };


    // ═══════════════════════════════════════════════
    // SearchPicker — 编排器
    // ═══════════════════════════════════════════════

    function SearchPicker(modal, config) {
        this.modal = modal;
        this.config = config;
        this.api = new SearchPickerAPI(config);
        this.renderer = new SearchPickerRenderer(modal.querySelector('.search-picker-results'));

        // 多字段模式：初始化字段构建器
        if (config.searchMode === 'multi' && config.searchFields.length) {
            this.fieldBuilder = new SearchPickerFieldBuilder(config.searchFields, config.searchUrl, modal.id);
        } else {
            this.fieldBuilder = null;
        }

        // 状态
        this.currentPage = 1;
        this.totalPages = 0;
        this.selectedValue = null;
        this._debounceTimer = null;

        this._init();
        this._bindEvents();
    }

    // ── 初始化 DOM ──

    SearchPicker.prototype._init = function () {
        // 设置 modal-dialog 尺寸
        this._applyModalSize();

        // 设置确认按钮文字
        var confirmBtn = this.modal.querySelector('.search-confirm-btn');
        if (confirmBtn) {
            var icon = confirmBtn.querySelector('i');
            confirmBtn.innerHTML = '';
            if (icon) {
                confirmBtn.appendChild(icon.cloneNode(true));
            }
            confirmBtn.appendChild(document.createTextNode(this.config.confirmText));
        }

        // 构建搜索输入区域
        if (this.config.searchMode === 'multi' && this.fieldBuilder) {
            var fieldsContainer = this.modal.querySelector('.search-picker-fields');
            if (fieldsContainer) {
                this.fieldBuilder.build(fieldsContainer);
                this.fieldBuilder.initTomSelects(fieldsContainer);
            }
            // 隐藏 simple 模式输入区域
            var inputArea = this.modal.querySelector('.search-picker-input-area');
            if (inputArea) inputArea.style.display = 'none';
            // 多字段初始状态
            this.renderer.renderStatus('ti-filter', '设置筛选条件后点击搜索');
        } else {
            // simple 模式：构建单输入框
            this._buildSimpleInput();
            // 隐藏 multi 模式字段区域
            var fieldsArea = this.modal.querySelector('.search-picker-fields');
            if (fieldsArea) fieldsArea.style.display = 'none';
        }
    };

    SearchPicker.prototype._applyModalSize = function () {
        var dialog = this.modal.querySelector('.modal-dialog');
        if (!dialog) return;
        // 移除已有的尺寸类
        dialog.classList.remove('modal-xl', 'modal-lg', 'modal-sm');
        if (this.config.displayMode === 'table') {
            dialog.classList.add('modal-xl');
        } else {
            dialog.classList.add('modal-lg');
        }
    };

    SearchPicker.prototype._buildSimpleInput = function () {
        var inputArea = this.modal.querySelector('.search-picker-input-area');
        if (!inputArea) return;

        var wrapper = document.createElement('div');
        wrapper.className = 'input-group input-group-flat';

        this.input = document.createElement('input');
        this.input.type = 'text';
        this.input.className = 'form-control search-picker-input';
        this.input.placeholder = this.config.placeholder;
        this.input.autocomplete = 'off';

        var span = document.createElement('span');
        span.className = 'input-group-text';
        span.innerHTML = '<i class="ti ti-search"></i>';

        wrapper.appendChild(this.input);
        wrapper.appendChild(span);
        inputArea.appendChild(wrapper);
    };

    // ── 事件绑定 ──

    SearchPicker.prototype._bindEvents = function () {
        var self = this;

        // simple 模式：搜索输入防抖
        if (this.input) {
            this.input.addEventListener('input', function () {
                self._resetSelection();
                self._debounce(function () { self._doSearch(1); }, 350);
            });
        }

        // multi 模式：搜索按钮
        var multiBtn = this.modal.querySelector('.search-multi-btn');
        if (multiBtn) {
            multiBtn.addEventListener('click', function () {
                self._resetSelection();
                self._doSearch(1);
            });
        }

        // 分页按钮
        var prevBtn = this.modal.querySelector('.search-prev-btn');
        var nextBtn = this.modal.querySelector('.search-next-btn');
        if (prevBtn) {
            prevBtn.addEventListener('click', function () {
                if (self.currentPage > 1) self._doSearch(self.currentPage - 1);
            });
        }
        if (nextBtn) {
            nextBtn.addEventListener('click', function () {
                if (self.currentPage < self.totalPages) self._doSearch(self.currentPage + 1);
            });
        }

        // 确认按钮
        var confirmBtn = this.modal.querySelector('.search-confirm-btn');
        if (confirmBtn) {
            confirmBtn.addEventListener('click', function () {
                self._confirm();
            });
        }

        // 模态框生命周期
        this.modal.addEventListener('shown.bs.modal', function () {
            self._onOpen();
        });
        this.modal.addEventListener('hidden.bs.modal', function () {
            self._onClose();
        });

        // 键盘导航
        this.modal.addEventListener('keydown', function (e) {
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter') {
                self._handleKeydown(e);
            }
        });
    };

    // ── 搜索 ──

    SearchPicker.prototype._doSearch = function (page) {
        var self = this;

        // simple 模式：检查输入非空
        if (!this.fieldBuilder && this.input && !this.input.value.trim()) {
            this.renderer.renderStatus('ti-search', '请输入关键词开始搜索');
            this.renderer.hidePagination(this.modal.querySelector('.search-picker-pagination'));
            return;
        }

        this.renderer.renderLoading();

        // 收集查询参数
        var queryParams = {};
        if (this.fieldBuilder) {
            queryParams = this.fieldBuilder.collectValues(this.modal.querySelector('.search-picker-fields'));
        } else if (this.input) {
            queryParams.q = this.input.value.trim();
        }

        this.api.search(queryParams, page)
            .then(function (data) {
                self.currentPage = data.page;
                self.totalPages = Math.ceil(data.total / data.pageSize);

                self.renderer.renderResults(data, self.config, self.selectedValue);
                self._bindResultEvents();

                self.renderer.renderPagination(
                    data,
                    self.modal.querySelector('.search-picker-pagination'),
                    self.modal.querySelector('.search-page-info'),
                    self.modal.querySelector('.search-prev-btn'),
                    self.modal.querySelector('.search-next-btn')
                );
            })
            .catch(function () {
                self.renderer.renderStatus('ti-alert-triangle', '搜索失败，请重试');
            });
    };

    // ── 结果交互 ──

    SearchPicker.prototype._bindResultEvents = function () {
        var self = this;
        var container = this.renderer.container;

        // 详情链接
        container.querySelectorAll('.search-detail-link').forEach(function (link) {
            link.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                window.open(this.dataset.url, '_blank');
            });
        });

        // 结果项点击
        var itemSelector = this.config.displayMode === 'table' ? '.search-result-row' : '.search-result-item';
        container.querySelectorAll(itemSelector).forEach(function (item) {
            item.addEventListener('click', function (e) {
                // 不拦截详情链接和外部链接的点击
                if (e.target.closest('.search-detail-link') ||
                    e.target.closest('a[target="_blank"]')) return;
                e.preventDefault();
                self._selectItem(this.dataset.value);
            });
        });
    };

    SearchPicker.prototype._selectItem = function (value) {
        this.selectedValue = value;
        var confirmBtn = this.modal.querySelector('.search-confirm-btn');
        if (confirmBtn) confirmBtn.disabled = false;

        this.renderer.highlightItem(value, this.renderer.container, this.config.displayMode);
    };

    SearchPicker.prototype._resetSelection = function () {
        this.selectedValue = null;
        var confirmBtn = this.modal.querySelector('.search-confirm-btn');
        if (confirmBtn) confirmBtn.disabled = true;
    };

    // ── 确认 ──

    SearchPicker.prototype._confirm = function () {
        var form = this.modal.closest('form');
        if (form && this.selectedValue) {
            var valueInput = form.querySelector('.search-picker-value');
            if (valueInput) valueInput.value = this.selectedValue;
            form.submit();
        }
    };

    // ── 生命周期 ──

    SearchPicker.prototype._onOpen = function () {
        if (this.input) {
            this.input.focus();
        }
        if (this.config.initialSearch) {
            this._doSearch(1);
        }
    };

    SearchPicker.prototype._onClose = function () {
        // 重置状态
        if (this.input) this.input.value = '';
        this.currentPage = 1;
        this.totalPages = 0;
        this.selectedValue = null;

        var confirmBtn = this.modal.querySelector('.search-confirm-btn');
        if (confirmBtn) confirmBtn.disabled = true;

        // 重置结果显示
        if (this.fieldBuilder) {
            this.renderer.renderStatus('ti-filter', '设置筛选条件后点击搜索');
        } else {
            this.renderer.renderStatus('ti-search', '请输入关键词开始搜索');
        }

        this.renderer.hidePagination(this.modal.querySelector('.search-picker-pagination'));

        // 清除多字段值
        if (this.fieldBuilder) {
            this.fieldBuilder.clearAll(this.modal.querySelector('.search-picker-fields'));
        }
    };

    // ── 键盘导航 ──

    SearchPicker.prototype._handleKeydown = function (e) {
        var itemSelector = this.config.displayMode === 'table' ? '.search-result-row' : '.search-result-item';
        var items = this.renderer.container.querySelectorAll(itemSelector);
        if (!items.length) return;

        // 找到当前高亮项
        var activeIdx = -1;
        for (var i = 0; i < items.length; i++) {
            if (items[i].classList.contains('active') || items[i].classList.contains('table-active')) {
                activeIdx = i;
                break;
            }
        }

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            activeIdx = (activeIdx + 1) % items.length;
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            activeIdx = (activeIdx - 1 + items.length) % items.length;
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (activeIdx >= 0 && this.selectedValue) {
                this._confirm();
            }
            return;
        }

        var target = items[activeIdx];
        this._selectItem(target.dataset.value);
        target.scrollIntoView({ block: 'nearest' });
    };

    // ── 防抖 ──

    SearchPicker.prototype._debounce = function (fn, delay) {
        var self = this;
        if (this._debounceTimer) clearTimeout(this._debounceTimer);
        this._debounceTimer = setTimeout(function () { fn.call(self); }, delay);
    };


    // ═══════════════════════════════════════════════
    // 模块级：懒初始化监听器
    // ═══════════════════════════════════════════════

    document.addEventListener('show.bs.modal', function (e) {
        var modal = e.target;
        if (modal._searchPickerReady) return;

        // 仅通过 JSON config script 识别搜索选择器模态框
        var configEl = document.getElementById(modal.id + '-config');
        if (!configEl) return;

        var rawConfig;
        try {
            rawConfig = JSON.parse(configEl.textContent.trim());
        } catch (err) {
            return;  // JSON 无效，静默跳过
        }

        var config = new SearchPickerConfig(rawConfig);
        modal._searchPicker = new SearchPicker(modal, config);
        modal._searchPickerReady = true;
    });


    // ═══════════════════════════════════════════════
    // 工具函数
    // ═══════════════════════════════════════════════

    function htmlEscape(s) {
        var d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    function escapeAttr(s) {
        return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;')
            .replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

})();
