/**
 * RGB 色值输入联动 — 文本框 ↔ 框内右侧原生颜色选择器。
 *
 * 约定结构：
 *   <div class="input-group">
 *     <input type="text" name="rgb_value" class="form-control">
 *     <input type="color" class="form-control form-control-color rgb-color-picker">
 *   </div>
 *
 * 用法：引入本文件即可（DOMContentLoaded 自动绑定所有 .rgb-color-picker）。
 */
(function () {
    'use strict';

    function init(root) {
        var scope = root || document;
        scope.querySelectorAll('.rgb-color-picker').forEach(function (picker) {
            if (picker.dataset.rgbBound) return;
            picker.dataset.rgbBound = '1';
            var group = picker.closest('.input-group');
            var text = group ? group.querySelector('input[type="text"][name="rgb_value"]') : null;
            if (!text) return;

            // 选择器 → 文本框
            picker.addEventListener('input', function () {
                text.value = picker.value;
            });
            // 文本框 → 选择器（仅合法 #RRGGBB 才同步）
            text.addEventListener('input', function () {
                var v = text.value.trim();
                if (/^#[0-9a-fA-F]{6}$/.test(v)) picker.value = v;
            });
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        init(document);
    });

    // 供动态插入内容后手动调用
    window.initRgbColorInputs = init;
})();
