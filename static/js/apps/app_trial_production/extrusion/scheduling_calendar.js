/**
 * 试验排产中心 — 只读排产日历 (FullCalendar 6.1.21)
 *
 * 仅用于查看：排产单不可点击跳转、不可拖拽/调整/取消排期，
 * 只允许在 月 (dayGridMonth) / 周 (timeGridWeek) / 日 (timeGridDay) /
 * 日程 (listWeek) 四种视图间切换，默认月视图。
 *
 * 数据流:
 *   事件 → GET window.EVENTS_URL?start=xxx&end=xxx (FullCalendar 自动附加)
 *
 * 与排产工作台 board.js 的差异:
 *   - 移除全部拖拽/排期/取消排期/统计/待排产池逻辑
 *   - editable / droppable / eventStartEditable / eventDurationEditable 全为 false
 *   - eventClick 不进行任何跳转
 */

document.addEventListener('DOMContentLoaded', function () {
    'use strict';

    var calendarEl = document.getElementById('scheduling-calendar');

    // ===== FullCalendar 初始化（只读） =====
    var calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'dayGridMonth',
        locale: 'zh-cn',
        firstDay: 0,
        scrollTime: '08:00:00',               // 初始滚动到 8:00
        headerToolbar: {
            left: 'prev,next today',
            center: 'title',
            right: 'dayGridMonth,timeGridWeek,timeGridDay,listWeek'
        },
        buttonText: {
            today: '今天',
            dayGridMonth: '月',
            timeGridWeek: '周',
            timeGridDay: '日',
            listWeek: '日程'
        },
        // 时间网格默认配置（周/日视图统一：全天 0-24 时）
        slotMinTime: '00:00:00',
        slotMaxTime: '24:00:00',
        slotDuration: '00:30:00',
        slotLabelInterval: '01:00:00',
        allDaySlot: true,
        nowIndicator: true,

        // 视图切换时动态设置高度：周/日视图固定 1350px（超出滚轮），月/日程自适应
        viewDidMount: function (arg) {
            var isTimeGrid = arg.view.type === 'timeGridWeek' || arg.view.type === 'timeGridDay';
            arg.view.calendar.setOption('height', isTimeGrid ? 1350 : 'auto');
        },

        // 只读开关
        editable: false,
        droppable: false,
        eventStartEditable: false,
        eventDurationEditable: false,
        slotEventOverlap: false,             // 同时间事件并排等宽，不堆叠
        dayMaxEvents: 4,

        // 事件数据源：函数模式，自动跟随视图日期范围请求
        events: function (fetchInfo, successCallback, failureCallback) {
            var url = window.EVENTS_URL + '?start=' + encodeURIComponent(fetchInfo.startStr) +
                      '&end=' + encodeURIComponent(fetchInfo.endStr);
            fetch(url)
                .then(function (r) { return r.json(); })
                .then(successCallback)
                .catch(failureCallback);
        },

        // 加载指示器
        loading: function (isLoading) {
            calendarEl.style.opacity = isLoading ? '0.6' : '1';
        },

        // ===== 事件渲染 — 单行卡片（仅展示） =====
        eventContent: function (arg) {
            var props = arg.event.extendedProps;
            var materialTypeName = props.material_type_name || '';

            // 颜色胶囊：有 RGB 色值则用，否则回退到默认灰
            var rgbValue = props.rgb_value || '';
            var colorCapsule = '';
            if (materialTypeName) {
                var bgColor = rgbValue || '#6c7a91';
                // 根据背景明度自适应文字颜色
                var r = parseInt(bgColor.slice(1, 3), 16) || 108;
                var g = parseInt(bgColor.slice(3, 5), 16) || 122;
                var b = parseInt(bgColor.slice(5, 7), 16) || 145;
                var luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
                var textColor = luminance > 0.6 ? '#1e293b' : '#ffffff';
                colorCapsule = '<span class="badge me-1" style="background-color:' + bgColor + ';color:' + textColor + ';font-size:10px;">'
                    + materialTypeName + '</span>';
            }

            return {
                html:
                    '<div class="fc-tabler-event d-flex flex-row align-items-start gap-1 p-1 rounded border ' +
                            (props.border_css || 'border-blue') + ' text-nowrap overflow-hidden" ' +
                            'data-trial-code="' + (props.trial_code || '') + '" ' +
                            'data-quantity="' + (props.quantity || '') + '" ' +
                            'data-formula-count="' + (props.formula_count || 0) + '" ' +
                            'data-needs-color="' + (props.needs_color ? '1' : '0') + '" ' +
                            'data-project-name="' + (props.project_name || '') + '" ' +
                            'data-process-profile="' + (props.process_profile_name || '') + '" ' +
                            'data-created-at="' + (props.created_at || '') + '" ' +
                            'data-stage-node="' + (props.stage_node || '') + '" ' +
                            'data-material-type="' + materialTypeName + '" ' +
                            'data-color-name="' + (props.material_color_name || '') + '" ' +
                            'data-pantone="' + (props.pantone_code || '') + '" ' +
                            'data-rgb="' + rgbValue + '">' +
                        colorCapsule +
                        '<span class="fc-ev-code fw-semibold">' + arg.event.title + '</span>' +
                        (props.quantity
                            ? ' <span class="badge ' + (props.quantity_badge || 'bg-blue text-white') + '">' + parseInt(props.quantity) + ' kg</span>'
                            : '') +
                    '</div>'
            };
        },

        // ===== 点击事件 → 仅展示，不跳转 =====
        eventClick: function (info) {
            info.jsEvent.preventDefault();
        },

        // ===== 悬浮弹窗：显示工单详细信息（仅展示） =====
        eventMouseEnter: function (info) {
            var card = info.el.querySelector('.fc-tabler-event');
            if (!card) return;

            var trialCode = card.dataset.trialCode || '-';
            var quantity = card.dataset.quantity || '0';
            var formulaCount = card.dataset.formulaCount || '0';
            var needsColor = card.dataset.needsColor === '1';
            var projectName = card.dataset.projectName || '-';
            var stageNode = card.dataset.stageNode || '-';
            var processProfile = card.dataset.processProfile || '-';
            var createdAt = card.dataset.createdAt || '-';

            // 颜色信息
            var materialType = card.dataset.materialType || '';
            var colorName = card.dataset.colorName || '';
            var pantone = card.dataset.pantone || '';
            var rgbVal = card.dataset.rgb || '';

            // 基材类型胶囊：背景色用 RGB，自适应文字颜色
            var matCapsule = '';
            if (materialType) {
                var bgColor = rgbVal || '#6c7a91';
                var r = parseInt(bgColor.slice(1, 3), 16) || 108;
                var g = parseInt(bgColor.slice(3, 5), 16) || 122;
                var b = parseInt(bgColor.slice(5, 7), 16) || 145;
                var lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
                matCapsule = '<span class="badge" style="background-color:' + bgColor + ';color:' + (lum > 0.6 ? '#1e293b' : '#ffffff') + ';">' + materialType + '</span>';
            }

            var html =
                '<div class="fw-bold pb-1 mb-1 border-bottom">' + info.event.title + '</div>' +
                (materialType || colorName || rgbVal
                    ? '<div class="d-flex align-items-center gap-2 mb-1"><span class="fc-popover-label fw-bold">颜色信息</span>'
                        + matCapsule
                        + (colorName ? ' <span class="mx-1">|</span> ' + colorName : '')
                        + (pantone ? ' <span class="badge bg-secondary-lt">' + pantone + '</span>' : '')
                        + (rgbVal
                            ? ' <span class="d-inline-block rounded ms-1" style="width:14px;height:14px;background-color:' + rgbVal
                                + ';vertical-align:middle;border:1px solid var(--tblr-border-color);"></span> ' + rgbVal
                            : '')
                        + '</div>'
                    : '') +
                '<div class="d-flex align-items-center gap-2 mb-1"><span class="fc-popover-label fw-bold">实验单号</span><span class="fw-bold">' + trialCode + '</span></div>' +
                '<div class="d-flex align-items-center gap-2 mb-1"><span class="fc-popover-label fw-bold">计划产量</span><span class="badge bg-purple-lt">' + quantity + ' kg</span></div>' +
                '<div class="d-flex align-items-center gap-2 mb-1"><span class="fc-popover-label fw-bold">配方数量</span><span class="badge bg-blue-lt">' + formulaCount + ' 个</span></div>' +
                '<div class="d-flex align-items-center gap-2 mb-1"><span class="fc-popover-label fw-bold">配色需求</span><span class="badge bg-orange-lt">' + (needsColor ? '需配色' : '无需配色') + '</span></div>' +
                '<div class="d-flex align-items-center gap-2 mb-1"><span class="fc-popover-label fw-bold">工艺方案</span><span class="badge bg-green-lt">' + processProfile + '</span></div>' +
                '<div class="d-flex align-items-center gap-2 mb-1"><span class="fc-popover-label fw-bold">关联项目</span><span class="fw-bold">' + projectName + '</span></div>' +
                '<div class="d-flex align-items-center gap-2 mb-1"><span class="fc-popover-label fw-bold">项目阶段</span><span class="badge bg-blue-lt">' + stageNode + '</span></div>' +
                '<div class="d-flex align-items-center gap-2 mb-1"><span class="fc-popover-label fw-bold">创建时间</span><span class="fw-bold">' + createdAt + '</span></div>';

            popover.innerHTML = html;
            popover.classList.add('active');
        },

        eventMouseLeave: function () {
            popover.classList.remove('active');
        },
    });

    calendar.render();

    // ===== 悬浮弹窗 DOM =====
    var popover = document.createElement('div');
    popover.id = 'fc-event-popover';
    popover.className = 'fc-event-popover card p-2';
    document.body.appendChild(popover);

    // 鼠标移动时弹窗自适应位置，避免被视口边缘遮挡
    calendarEl.addEventListener('mousemove', function (e) {
        if (!popover.classList.contains('active')) return;

        var gap = 12;
        var edgePad = 8;
        var pw = popover.offsetWidth;
        var ph = popover.offsetHeight;
        var vw = window.innerWidth;
        var vh = window.innerHeight;

        // 默认右下跟随，超出视口时翻转到左/上方
        var left = e.clientX + gap;
        var top = e.clientY + gap;

        if (left + pw > vw - edgePad) {
            left = e.clientX - pw - gap;        // 翻转到光标左侧
        }
        if (top + ph > vh - edgePad) {
            top = e.clientY - ph - gap;         // 翻转到光标上方
        }

        // 确保不超出左/上边界
        left = Math.max(edgePad, left);
        top = Math.max(edgePad, top);

        popover.style.left = left + 'px';
        popover.style.top = top + 'px';
    });
});