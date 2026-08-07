/**
 * 字段只读控制工具 —— 表单填写页 / 审批详情页共用。
 *
 * 只读字段优先使用 readonly（Element Plus 支持 readonly 的组件），
 * 不支持的组件回退到 disabled；设计器已设 disabled 的字段保持 disabled。
 *
 * 递归遍历 children / control，确保表格布局（fcTable）、行/列、分组/subForm 等
 * 容器内的字段也被正确处理（form-create 不会把 disabled 从表格容器传播到子字段）。
 *
 * 暴露：window.FCReadonly.{ stepOf, setReadonly, apply }
 */
(function (global) {
    'use strict';

    // 支持 readonly 的组件类型（Element Plus 支持 readonly prop，设计器相应暴露了该开关）
    // 其余组件（select/radio/checkbox/switch/slider/upload/cascader/rate/color...）不支持 readonly，
    // 若只设 readonly 会被静默忽略 → 必须回退到 disabled。
    var FC_READONLY_TYPES = [
        'input', 'textarea', 'password', 'inputNumber',
        'datePicker', 'dateRange', 'timePicker', 'timeRange'
    ];

    // 读取规则所属表单步骤（缺省为第 1 步）
    function fcStepOf(r) {
        return (r.props && r.props.step != null) ? parseInt(r.props.step) : 1;
    }

    // 将单个字段设为只读：移除必填/校验；优先 readonly，不支持 readonly 的组件回退 disabled；
    // 设计器已设 disabled 的字段保持 disabled，不转 readonly。
    function fcSetReadonly(r) {
        var props = r.props = Object.assign({}, r.props || {});
        r.$required = false;
        r.validate = undefined;
        if (props.disabled === true) return; // 设计器已禁用 → 保持 disabled
        if (FC_READONLY_TYPES.indexOf(r.type) !== -1) {
            props.readonly = true;
        } else {
            props.disabled = true;
        }
    }

    // 递归遍历规则树，对满足 isReadonly(r) 的字段应用只读。
    // 仅对含 field 的规则（实际数据字段 / group / subForm）应用；
    // 纯布局容器（fcTable/row/col）跳过但递归其 children/control，
    // 这样表格布局内的字段也会被正确处理。
    function fcApplyReadonly(rules, isReadonly) {
        for (var i = 0; i < rules.length; i++) {
            var r = rules[i];
            if (!r || typeof r !== 'object') continue;
            if (r.field && isReadonly(r)) fcSetReadonly(r);
            if (Array.isArray(r.children)) fcApplyReadonly(r.children, isReadonly);
            if (Array.isArray(r.control)) fcApplyReadonly(r.control, isReadonly);
        }
    }

    global.FCReadonly = {
        stepOf: fcStepOf,
        setReadonly: fcSetReadonly,
        apply: fcApplyReadonly
    };
})(window);