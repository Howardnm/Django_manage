/**
 * 挤出排产工作台 — FullCalendar 6.1.21
 *
 * 布局:
 *   上方: 待排产工单列表（可拖拽至日历 / 选择时间 + 领取按钮）
 *   下方: 排产日历（时间网格周视图/月视图/日视图，支持拖拽调整时间）
 *
 * 拖拽场景:
 *   场景一 (内部拖拽): 日历内拖动已有工单到新时间 → eventDrop → POST 更新排产时间
 *   场景二 (外部拖入): 从待排产池拖入日历时间槽 → eventReceive → POST 创建排产
 *   场景三 (拉伸调整): 拖动事件边缘调整时长 → eventResize → POST 更新结束时间
 *
 * 数据流:
 *   日历事件 → GET window.EVENTS_URL?start=xxx&end=xxx (FullCalendar 自动附加)
 *   领取排期 → POST window.SCHEDULE_URL → calendar.refetchEvents()
 *   取消排期 → POST /extrusion-board/{pk}/unschedule/ → reload
 *
 * 视图时间范围:
 *   周视图: 00:00-24:00 (业务时间)
 *   日视图: 00:00-24:00 (全天)
 *   月视图: 无时间轴
 */

document.addEventListener('DOMContentLoaded', function () {
    'use strict';

    var calendarEl = document.getElementById('extrusion-calendar');
    var pendingPool = null;  // HTMX 卡片加载后由 htmx:afterSettle 赋值

    // ===== 常量 =====
    var DEFAULT_DURATION_MS = 60 * 60 * 1000; // 默认排产时长 1 小时

    // ===== Toast 工具（使用 Tabler 原生样式） =====
    function showToast(msg, type) {
        var bgClass = type === 'success' ? 'bg-success-lt' : 'bg-danger-lt';
        var icon = type === 'success' ? 'ti-check' : 'ti-alert-circle';
        var toast = document.createElement('div');
        toast.className = 'toast show position-fixed ' + bgClass;
        toast.style.cssText = 'top:20px; right:20px; z-index:9999; min-width:300px;';
        toast.innerHTML =
            '<div class="toast-body d-flex align-items-center">' +
                '<i class="ti ' + icon + ' me-2 fs-4"></i>' +
                '<span>' + msg + '</span>' +
            '</div>';
        document.body.appendChild(toast);
        setTimeout(function () { toast.remove(); }, 3500);
    }

    // ===== 时间格式化 =====
    function formatTime(dateObj) {
        if (!dateObj) return '';
        return String(dateObj.getHours()).padStart(2, '0') + ':' +
               String(dateObj.getMinutes()).padStart(2, '0');
    }

    // ===== HTMX 卡片刷新 =====
    function refreshPendingCard() {
        if (typeof htmx !== 'undefined') {
            htmx.ajax('GET', window.CARD_REFRESH_URL, {
                target: '#pending-orders-card',
                swap: 'outerHTML',
            });
        }
    }

    // ===== 懒加载统计指标 =====
    function fetchStats() {
        fetch(window.STATS_URL)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                document.getElementById('stat-pending-count').textContent = data.pending_count;
                document.getElementById('stat-scheduled-count').textContent = data.scheduled_count;
                document.getElementById('stat-in-progress-count').textContent = data.in_progress_count;
            })
            .catch(function () {
                // 请求失败时保持占位符 —
            });
    }

    // ===== TomSelect 远程搜索配置（复用通用函数 initRemoteTomSelect） =====
    var PENDING_TS_OPTS = {
        apiUrl: '/trial-production/api/search/',
        valueField: 'id',
        responseKey: 'results',
    };

    // ===== HTMX 事件：卡片替换前先销毁旧 TomSelect（清除 body 中的 .ts-dropdown 残留） =====
    document.addEventListener('htmx:beforeSwap', function (e) {
        destroyTomSelectAll(e.target);
    });

    // ===== HTMX 事件：卡片加载/刷新后初始化 TomSelect + Draggable =====
    document.addEventListener('htmx:afterSettle', function () {
        var card = document.getElementById('pending-orders-card');
        if (!card) return;

        // TomSelect 初始化
        initRemoteTomSelectAll(card, PENDING_TS_OPTS);

        // Draggable 重建
        var newPool = document.getElementById('pending-pool');
        if (newPool && newPool !== pendingPool) {
            if (draggable) draggable.destroy();
            pendingPool = newPool;
            draggable = new FullCalendar.Draggable(pendingPool, {
                itemSelector: '.pending-drag-row',
                eventData: function (eventEl) {
                    return {
                        id: eventEl.dataset.eventId,
                        title: eventEl.dataset.eventTitle,
                        create: true,
                        duration: '01:00:00',
                    };
                }
            });
        }
    });

    // ===== 发送排期请求（共用：start 必传，end 可选） =====
    function scheduleOrder(orderPk, startStr, endStr) {
        // 全天事件：start/end 为纯日期格式 → 转为 T00:00:00
        if (startStr && startStr.length === 10) {
            startStr = startStr + 'T00:00:00';
            // 使用 FullCalendar 提供的 endStr（跨多天时为 exclusive end date）
            if (endStr && endStr.length === 10) {
                endStr = endStr + 'T00:00:00';
            } else {
                endStr = startStr;  // 兜底：单天全天事件
            }
        }
        // 确保 end 始终有值（定时事件默认 +1h）
        if (!endStr) {
            var d = new Date(startStr);
            d.setTime(d.getTime() + 60 * 60 * 1000);
            endStr = d.toISOString();
        }
        var body = 'order_pk=' + orderPk + '&scheduled_date=' + encodeURIComponent(startStr) +
                   '&scheduled_end=' + encodeURIComponent(endStr);
        return fetch(window.SCHEDULE_URL, {
            method: 'POST',
            headers: {
                'X-CSRFToken': window.CSRF_TOKEN,
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: body,
        }).then(function (r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        }).then(function (data) {
            if (!data.success) throw new Error(data.error || '排期失败');
            return data;
        });
    }

    // ===== FullCalendar 初始化 =====
    var calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'timeGridWeek',
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

        // 拖拽开关
        editable: true,
        droppable: true,
        eventStartEditable: true,
        eventDurationEditable: true,
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

        // ===== 事件渲染 — 单行卡片 + 操作按钮 =====
        eventContent: function (arg) {
            var props = arg.event.extendedProps;
            var orderPk = arg.event.id;
            var formulaCount = props.formula_count || 0;
            var isReadonly = !arg.event.startEditable;

            // 颜色胶囊：有 RGB 色值则用，否则回退到默认灰
            var rgbValue = props.rgb_value || '';
            var materialTypeName = props.material_type_name || '';
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
                            (props.border_css || 'border-blue') + ' text-nowrap overflow-hidden' +
                            (isReadonly ? ' fc-tabler-event-readonly' : '') + '" ' +
                            'data-order-pk="' + orderPk + '" ' +
                            'data-trial-code="' + (props.trial_code || '') + '" ' +
                            'data-quantity="' + (props.quantity || '') + '" ' +
                            'data-formula-count="' + formulaCount + '" ' +
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

        // ===== 场景一：日历内部拖拽 → 更新排产时间（含开始+结束） =====
        eventDrop: function (info) {
            var orderPk = info.event.id;
            var newStartStr = info.event.startStr;
            var oldStartStr = info.oldEvent.startStr;
            var newEndStr = info.event.endStr;

            if (newStartStr === oldStartStr) return;

            scheduleOrder(orderPk, newStartStr, newEndStr)
                .then(function (data) {
                    showToast(info.event.title + ' 已移至 ' + formatTime(new Date(data.date)), 'success');
                })
                .catch(function (err) {
                    info.revert();
                    showToast('移动失败：' + (err.message || '请稍后重试'), 'error');
                });
        },

        // ===== 场景三：拉伸事件调整时长 → 持久化结束时间 =====
        eventResize: function (info) {
            var orderPk = info.event.id;
            var startStr = info.event.startStr;
            var endStr = info.event.endStr;

            scheduleOrder(orderPk, startStr, endStr)
                .then(function () {
                    showToast(info.event.title + ' 时长已更新', 'success');
                })
                .catch(function (err) {
                    info.revert();
                    showToast('更新失败：' + (err.message || '请稍后重试'), 'error');
                });
        },

        // ===== 场景二：外部拖入 → 创建排期 =====
        eventReceive: function (info) {
            var orderPk = info.event.id;
            var startStr = info.event.startStr;
            var endStr = info.event.endStr;
            var draggedEl = info.draggedEl;
            var orderTitle = info.event.title;

            scheduleOrder(orderPk, startStr, endStr)
                .then(function (data) {
                    info.event.remove();
                    calendar.refetchEvents();
                    if (draggedEl) draggedEl.remove();
                    refreshPendingCard();
                    fetchStats();

                    showToast((data.code || orderTitle) + ' 已排期', 'success');
                })
                .catch(function (err) {
                    info.event.remove();
                    showToast('排期失败：' + (err.message || '请稍后重试'), 'error');
                });
        },

        // ===== 点击事件 → 跳转详情 =====
        eventClick: function (info) {
            if (info.jsEvent.target.closest('.fc-ev-btn')) {
                return;
            }
            info.jsEvent.preventDefault();
            window.location.href = '/trial-production/orders/' + info.event.id + '/';
        },

        // ===== 拖拽到待排产池 → 取消排期 =====
        eventDragStop: function (info) {
            if (!pendingPool) return;
            var pendingCard = pendingPool.closest('.card');
            if (!pendingCard) return;

            var pendingRect = pendingCard.getBoundingClientRect();
            var mouseX = info.jsEvent.clientX;
            var mouseY = info.jsEvent.clientY;

            if (mouseX >= pendingRect.left && mouseX <= pendingRect.right &&
                mouseY >= pendingRect.top && mouseY <= pendingRect.bottom) {
                var url = window.UNSCHEDULE_URL_PREFIX + info.event.id + window.UNSCHEDULE_URL_SUFFIX;
                fetch(url, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': window.CSRF_TOKEN },
                }).then(function (r) {
                    if (!r.ok) throw new Error('HTTP ' + r.status);
                    return r.json();
                }).then(function (data) {
                    if (data.success) {
                        info.event.remove();
                        refreshPendingCard();
                        fetchStats();
                        showToast(data.code + ' 已取消排期', 'success');
                    }
                }).catch(function () {
                    showToast('取消排期失败', 'error');
                });
            }
        },

        // ===== 悬浮弹窗：显示工单详细信息 =====
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

    // ===== 懒加载统计指标 + 待排产工单卡片 =====
    fetchStats();

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

    // ===== 外部拖拽：待排产池行 → 日历（HTMX 卡片加载后由 htmx:afterSettle 初始化） =====
    var draggable = null;

    // ===== 领取排期 / 取消排期 按钮代理 =====
    document.addEventListener('click', function (e) {
        // --- 领取排期 ---
        var scheduleBtn = e.target.closest('.btn-schedule-order');
        if (scheduleBtn) {
            e.preventDefault();
            var orderPk = scheduleBtn.dataset.orderPk;
            var orderCode = scheduleBtn.dataset.orderCode;
            var row = scheduleBtn.closest('tr');
            var dateInput = row.querySelector('.schedule-date-input');
            var datetimeValue = dateInput ? dateInput.value : '';

            if (!datetimeValue) {
                showToast('请选择排产时间', 'error');
                if (dateInput) dateInput.focus();
                return;
            }

            scheduleBtn.disabled = true;
            var originalHtml = scheduleBtn.innerHTML;
            scheduleBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>排期中...';

            // 领取按钮只有开始时间，后端自动补默认结束时间
            scheduleOrder(orderPk, datetimeValue)
                .then(function (data) {
                    calendar.refetchEvents();
                    refreshPendingCard();
                    fetchStats();
                    showToast((data.code || orderCode) + ' 已排期', 'success');
                })
                .catch(function (err) {
                    scheduleBtn.disabled = false;
                    scheduleBtn.innerHTML = originalHtml;
                    showToast('排期失败：' + (err.message || '请稍后重试'), 'error');
                });
            return;
        }

        // --- 取消排期 ---
        var unscheduleBtn = e.target.closest('.btn-unschedule');
        if (unscheduleBtn) {
            e.preventDefault();
            if (!confirm('确认取消排期？工单将退回待排产池。')) return;

            var url = unscheduleBtn.dataset.url;
            var orderPk = unscheduleBtn.dataset.orderPk;
            unscheduleBtn.disabled = true;

            fetch(url, {
                method: 'POST',
                headers: { 'X-CSRFToken': window.CSRF_TOKEN },
            }).then(function (r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            }).then(function (data) {
                if (data.success) {
                    var event = calendar.getEventById(String(orderPk));
                    if (event) event.remove();
                    refreshPendingCard();
                    fetchStats();
                    showToast(data.code + ' 已取消排期', 'success');
                }
            }).catch(function (err) {
                unscheduleBtn.disabled = false;
                showToast('取消排期失败', 'error');
            });
            return;
        }
    });
});