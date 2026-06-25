/* ==========================================
   项目进度甘特图 — app_project/detail/_gantt.html
   依赖: Highcharts Gantt 12.5.0
   ========================================== */

document.addEventListener("DOMContentLoaded", function () {
    const ganttEl = document.getElementById('project-gantt');
    if (!ganttEl) return;

    // 1. 从 json_script 标签获取后端数据（安全方式）
    const dataScript = document.getElementById('gantt-data');
    if (!dataScript) return;
    const projectData = JSON.parse(dataScript.textContent);

    // 2. 数据判空处理
    if (!projectData || projectData.length === 0) {
        ganttEl.innerHTML = '<div class="text-center text-muted py-5">暂无进度数据</div>';
        return;
    }

    // 3. 动态高度计算
    var rowHeight = 24;
    var minRows = 5;
    var headerHeight = 65;
    var visibleRows = Math.max(projectData.length, minRows);
    var calculatedHeight = (visibleRows * rowHeight) + headerHeight;
    var maxHeight = 280;
    var chartHeight = Math.min(calculatedHeight, maxHeight);

    // 4. 初始化 Highcharts Gantt
    Highcharts.ganttChart('project-gantt', {
        chart: {
            height: chartHeight,
            style: { fontFamily: 'inherit' },
            plotBackgroundColor: 'rgba(128,128,128,0.02)',
            plotBorderColor: 'rgba(128,128,128,0.1)',
            plotBorderWidth: 1,
        },
        title: { text: null },
        plotOptions: {
            series: {
                borderRadius: 5,
                groupPadding: 0,
                borderWidth: 0,
                shadow: false,
                dataLabels: [{
                    enabled: true,
                    align: 'left',
                    format: '{point.name}-{point.node_round}',
                    padding: 0,
                    y: 0,
                    style: {
                        fontWeight: 'normal',
                        textOutline: 'none',
                        fontSize: '11px'
                    }
                }]
            }
        },
        series: [{
            name: 'Project',
            data: projectData
        }],
        tooltip: {
            headerFormat: '<span style="font-size: 10px">{point.key}</span><br/>',
            pointFormat: '<b>{point.status_label}</b><br/>{point.start:%Y-%m-%d} → {point.end:%Y-%m-%d}'
        },
        yAxis: {
            type: 'treegrid',
            uniqueNames: true,
            staticScale: rowHeight,
            minTickInterval: 1,
            grid: {
                borderColor: 'rgba(128,128,128,0.1)',
                borderWidth: 1,
                columns: [{
                    title: {
                        text: '阶段流程',
                        style: { fontSize: '12px' }
                    },
                    labels: {
                        align: 'left',
                        style: {
                            color: '#1d273b',
                            fontSize: '12px',
                            fontWeight: '500'
                        },
                        x: 15
                    }
                }]
            }
        },
        xAxis: [{
            currentDateIndicator: {
                color: '#2caffe',
                dashStyle: 'ShortDot',
                width: 2,
                label: { format: '' }
            },
            grid: {
                borderWidth: 1,
                borderColor: 'rgba(128,128,128,0.1)',
                cellHeight: 25
            },
            tickPixelInterval: 150,
            dateTimeLabelFormats: {
                day: { list: ['%d', '%a'] },
                week: { list: ['%m-%d', '%W周'] },
                month: { list: ['%Y-%m', '%Q'] }
            },
            labels: {
                style: { fontSize: '10px' },
                y: -5
            }
        }],
        navigator: {
            enabled: true,
            height: 15,
            series: { type: 'gantt', pointPadding: 0 },
            yAxis: { min: 0, max: 7, reversed: true, categories: [] }
        },
        scrollbar: { enabled: true },
        credits: { enabled: false }
    });
});
