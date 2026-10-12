(function () {
    var card = document.getElementById('test-result-card');
    var btn = document.getElementById('btn-test-return');
    if (!card || !btn) {
        return;
    }

    var MANUAL_TITLE = '请先选择工单';
    var CONFIRM_TEXT = '确定将该工单的测试任务退回「测试中」吗？已填写的测试数据会保留，材料测试中心可以重新修改并再次回写。配方上已回写的结果保持不变，直到重新回写覆盖。';

    function applyTab(link) {
        var isOrder = link && link.hasAttribute('data-order-id');
        var canReturn = isOrder && link.getAttribute('data-can-return') === '1';
        var url = canReturn ? (link.getAttribute('data-return-url') || '') : '';
        btn.dataset.returnUrl = url;
        if (canReturn && url) {
            btn.disabled = false;
            btn.title = '将该工单的测试任务退回测试中';
            return;
        }
        btn.disabled = true;
        if (!isOrder) {
            btn.title = MANUAL_TITLE;
            return;
        }
        var label = link.getAttribute('data-status-label') || '';
        btn.title = label
            ? '当前任务状态为「' + label + '」，不能退回'
            : '该工单没有可退回的测试任务';
    }

    card.addEventListener('shown.bs.tab', function (event) {
        applyTab(event.target);
    });

    btn.addEventListener('click', function () {
        var url = btn.dataset.returnUrl;
        if (btn.disabled || !url) {
            return;
        }
        if (!window.confirm(CONFIRM_TEXT)) {
            return;
        }
        btn.disabled = true;
        fetch(url, {
            method: 'POST',
            headers: {
                'X-CSRFToken': btn.getAttribute('data-csrf') || '',
                'X-Requested-With': 'XMLHttpRequest',
            },
        }).then(function (resp) {
            if (resp.status === 403) {
                return resp.json().then(function (data) {
                    window.alert((data && data.message) || '权限不足，无法执行此操作。');
                    applyTab(card.querySelector('.nav-link.active'));
                });
            }
            window.location.reload();
        }).catch(function () {
            window.alert('退回失败，请稍后重试');
            applyTab(card.querySelector('.nav-link.active'));
        });
    });
})();
