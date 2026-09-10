/**
 * 通用配方对比表格组件。
 *
 * 数据：由后端 DRF 序列化层（common_utils/serializers/compare.py serialize_compare）
 * 输出，经模板 `{{ compare_data|json_script:"compare-data" }}` 注入到
 * `<script type="application/json" id="compare-data">`。
 *
 * 渲染：把 columns + sections 渲染进 `#compare-table-mount`。
 */
(function () {
    'use strict';

    // 分区颜色 → Tabler 类 + 底色（与原 _formula_compare_panel.html 一致）
    var SECTION_COLORS = {
        blue:   { cls: 'bg-blue-lt',   hex: '#e6f1fa' },
        green:  { cls: 'bg-green-lt',  hex: '#e9f7ec' },
        orange: { cls: 'bg-orange-lt', hex: '#fef0e6' },
        pink:   { cls: 'bg-pink-lt',   hex: '#fbe9f0' },
        purple: { cls: 'bg-purple-lt', hex: '#f1ebf8' },
        cyan:   { cls: 'bg-cyan-lt',   hex: '#e6f4f7' },
    };

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = text;
        return node;
    }

    function link(url, text, className) {
        var a = document.createElement('a');
        a.href = url || '#';
        if (url) a.target = '_blank';
        a.className = className || 'text-reset';
        a.textContent = text;
        return a;
    }

    function iconEl(name) {
        var i = el('i', 'ti ' + name + ' me-1');
        return i;
    }

    // ── 列头 ──
    function columnHeaderCell(col) {
        var th = document.createElement('th');
        th.className = 'align-middle';
        th.style.minWidth = '100px';

        if (col.type === 'material') {
            th.appendChild(el('div', 'badge bg-blue-lt mb-2', '基准材料'));
            var name = el('div', 'fw-bold fs-4 text-wrap');
            name.appendChild(link(col.detail_url, col.grade_name || '-'));
            th.appendChild(name);
            th.appendChild(el('div', 'small text-muted text-truncate', col.manufacturer || '-'));
        } else if (col.type === 'raw_material') {
            th.appendChild(el('div', 'badge bg-orange-lt mb-2', '原材料'));
            var rname = el('div', 'fw-bold fs-4 text-wrap');
            rname.appendChild(link(col.detail_url, col.name || '-'));
            th.appendChild(rname);
            th.appendChild(el('div', 'small text-muted text-truncate', col.model_name || '-'));
        } else {
            // formula
            th.appendChild(el('div', 'fw-bold text-primary text-wrap', col.stage_label || ''));
            th.appendChild(el('div', 'small text-muted', col.code || ''));
            var badges = el('div', 'mt-1');
            if (col.is_mature) badges.appendChild(el('span', 'badge bg-green-lt', '★成熟'));
            if (col.is_competitor) badges.appendChild(el('span', 'badge bg-purple-lt', '竞品'));
            if (col.is_foreign) {
                badges.appendChild(el('span', 'badge bg-yellow-lt', '史'));
            } else {
                badges.appendChild(el('span', 'badge bg-blue-lt', col.material_type_name || '-'));
            }
            th.appendChild(badges);
        }
        return th;
    }

    // 前 3 列：分类/项目、详情/标准、单位（min-width 与原始值一致）
    var LABEL_HEADERS = [
        { label: '分类 / 项目', minWidth: '60px' },
        { label: '详情 / 标准', minWidth: '100px' },
        { label: '单位', minWidth: '40px' },
    ];

    function buildThead(columns) {
        var thead = document.createElement('thead');
        var tr = document.createElement('tr');
        tr.className = 'bg-light';
        LABEL_HEADERS.forEach(function (h) {
            var th = document.createElement('th');
            th.className = 'text-start align-middle';
            th.style.minWidth = h.minWidth;
            th.style.whiteSpace = 'nowrap';
            th.textContent = h.label;
            tr.appendChild(th);
        });
        columns.forEach(function (col) {
            tr.appendChild(columnHeaderCell(col));
        });
        thead.appendChild(tr);
        return thead;
    }

    // ── 表体 ──
    function valueCell(v) {
        var td = document.createElement('td');
        td.className = 'align-middle';
        if (v.base) {
            td.classList.add('text-blue');
            td.style.backgroundColor = '#e6f1fa';
        }
        if (v.cls) td.classList.add(v.cls);
        if (v.empty || v.v === '' || v.v === null || v.v === undefined) {
            var dash = el('span', 'text-muted text-opacity-25', '-');
            td.appendChild(dash);
        } else if (v.url) {
            td.appendChild(link(v.url, v.v, 'fw-bold'));
        } else {
            td.appendChild(el('span', 'fw-bold', v.v));
        }
        return td;
    }

    // 第二固定列（详情/标准）：原材料行带可点击名称 + 括号内 SAP编码/单价（同行加粗）
    function label2Cell(row) {
        var td = document.createElement('td');
        if (row.label2_url) {
            td.className = 'text-start align-middle';
            var nameLink = document.createElement('a');
            nameLink.href = row.label2_url;
            nameLink.target = '_blank';
            nameLink.className = 'fw-bold text-reset';
            nameLink.textContent = row.label2 || '-';
            td.appendChild(nameLink);
            var meta = [];
            if (row.label2_sap) meta.push('SAP: ' + row.label2_sap);
            if (row.label2_price) meta.push('¥' + row.label2_price + '/kg');
            if (meta.length) td.appendChild(el('span', 'fw-bold text-reset small', ' (' + meta.join(' · ') + ')'));
        } else {
            td.className = 'text-start align-middle small text-muted';
            td.textContent = row.label2 || '-';
        }
        return td;
    }

    function buildRow(section, row, colorHex) {
        var tr = document.createElement('tr');
        if (!section.band) {
            // 单行样式（描述/成本/均价/色粉成本）：标签格带底色+加粗彩色
            var labelTd = document.createElement('td');
            labelTd.className = 'text-start bg-light fw-bold text-' + section.color + ' align-middle';
            labelTd.appendChild(iconEl(section.icon));
            labelTd.appendChild(document.createTextNode(row.label));
            tr.appendChild(labelTd);
        } else {
            var bandLabel = el('td', 'text-start align-middle text-muted small', row.label);
            tr.appendChild(bandLabel);
        }
        tr.appendChild(label2Cell(row));
        tr.appendChild(el('td', 'text-muted align-middle', row.unit || '-'));
        row.values.forEach(function (v) {
            tr.appendChild(valueCell(v));
        });
        return tr;
    }

    function sectionHeaderRow(section, nColumns) {
        var color = SECTION_COLORS[section.color] || SECTION_COLORS.blue;
        var tr = document.createElement('tr');
        tr.className = color.cls;
        var td1 = document.createElement('td');
        td1.className = 'text-start fw-bold text-' + section.color + ' align-middle';
        td1.colSpan = 4;
        td1.style.backgroundColor = color.hex;
        td1.appendChild(iconEl(section.icon));
        td1.appendChild(document.createTextNode(section.label));
        tr.appendChild(td1);
        if (nColumns > 1) {
            var td2 = document.createElement('td');
            td2.className = 'align-middle';
            td2.colSpan = nColumns - 1;
            td2.style.backgroundColor = color.hex;
            tr.appendChild(td2);
        }
        return tr;
    }

    function buildTbody(sections) {
        var tbody = document.createElement('tbody');
        sections.forEach(function (section) {
            if (!section.rows || !section.rows.length) return;
            if (section.band) {
                tbody.appendChild(sectionHeaderRow(section, /* nColumns from first row */ section.rows[0].values.length));
            }
            section.rows.forEach(function (row) {
                tbody.appendChild(buildRow(section, row));
            });
        });
        return tbody;
    }

    document.addEventListener('DOMContentLoaded', function () {
        var mount = document.getElementById('compare-table-mount');
        var dataEl = document.getElementById('compare-data');
        if (!mount || !dataEl) return;
        var data;
        try {
            data = JSON.parse(dataEl.textContent.trim());
        } catch (e) {
            return;
        }
        if (!data || !data.columns || !data.columns.length) return;

        var table = document.createElement('table');
        table.className = 'table table-vcenter table-bordered card-table text-center table-sm compare-table';
        table.style.fontSize = '13px';
        table.appendChild(buildThead(data.columns));
        table.appendChild(buildTbody(data.sections));
        mount.appendChild(table);
    });
})();
