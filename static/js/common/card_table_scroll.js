/* 横滚表格内的 TomSelect：打开时挂到 body 并用视口坐标定位。
   配方编辑页、色粉配比 BOM、原材料性能指标、成品材料物性指标、生产工单注塑需求共用。选择器是 .formula-table-scroll。

   不用 dropdownParent:'body'。那条路径用 window.scrollY，而本项目滚动容器是
   .page-wrapper，scrollY 恒为 0，面板会飘。 */
function placeFormulaDropdown(ts) {
    if (!ts.isOpen) return;
    var scrollEl = ts.input.closest('.formula-table-scroll');
    if (!scrollEl) return;

    var rect = ts.wrapper.getBoundingClientRect();
    var port = scrollEl.getBoundingClientRect();
    var centerX = (rect.left + rect.right) / 2;
    var centerY = (rect.top + rect.bottom) / 2;
    var outsidePort = centerX <= port.left || centerX >= port.right
        || centerY <= port.top || centerY >= port.bottom;
    var outsideViewport = rect.bottom <= 0 || rect.top >= window.innerHeight;
    if (outsidePort || outsideViewport) {
        ts.close();
        return;
    }

    var dd = ts.dropdown;
    if (dd.parentElement !== document.body) {
        document.body.appendChild(dd);
    }
    // fixed 下样式表的 min-width:100% 会变成整屏宽，改成输入框像素宽度
    dd.style.position = 'fixed';
    dd.style.marginTop = '0';
    dd.style.minWidth = rect.width + 'px';
    dd.style.width = 'max-content';
    dd.style.left = rect.left + 'px';
    dd.style.top = (rect.bottom + 2) + 'px';

    var ddWidth = dd.offsetWidth;
    var left = rect.left;
    if (left + ddWidth > window.innerWidth - 8) {
        left = Math.max(8, window.innerWidth - ddWidth - 8);
    }
    dd.style.left = left + 'px';

    var ddHeight = dd.offsetHeight;
    if (rect.bottom + 2 + ddHeight > window.innerHeight && rect.top - ddHeight - 2 > 8) {
        dd.style.top = (rect.top - ddHeight - 2) + 'px';
    }
}

function bindFormulaTableDropdowns(root) {
    if (!root) return;
    root.querySelectorAll('.formula-table-scroll select').forEach(function (el) {
        var ts = el.tomselect;
        if (!ts || ts._formulaPortal) return;
        ts._formulaPortal = true;
        // 已有值时输入框在 left:-10000px。默认 focus() 会让横滚容器追过去，表被拉回最左边。
        var origFocus = ts.focus;
        ts.focus = function () {
            var input = this.control_input;
            var inputFocus = input.focus;
            input.focus = function () {
                return inputFocus.call(input, { preventScroll: true });
            };
            try {
                return origFocus.call(this);
            } finally {
                input.focus = inputFocus;
            }
        };
        var reposition = function () { placeFormulaDropdown(ts); };
        ts.on('dropdown_open', reposition);
        ts.on('load', reposition);
    });
}

function repositionOpenFormulaDropdowns() {
    document.querySelectorAll('.formula-table-scroll select').forEach(function (el) {
        if (el.tomselect && el.tomselect.isOpen) {
            placeFormulaDropdown(el.tomselect);
        }
    });
}

document.addEventListener('scroll', repositionOpenFormulaDropdowns, true);
window.addEventListener('resize', repositionOpenFormulaDropdowns);
