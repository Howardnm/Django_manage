/* ==========================================
   项目全局配置页 — app_project/config.html
   依赖: 无
   ========================================== */

document.addEventListener("DOMContentLoaded", function () {
    const btnSave = document.getElementById('btn-save');
    if (!btnSave) return;

    btnSave.addEventListener('click', async function () {
        const btn = this;
        btn.disabled = true;
        try {
            const resp = await fetch(window.PROJECT_CONFIG_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': window.CSRF_TOKEN
                },
                body: JSON.stringify({
                    workflow_id: document.getElementById('workflow-select').value || null
                })
            });
            const result = await resp.json();
            if (result.status === 'success') {
                alert('配置已保存');
            } else {
                alert(result.message || '保存失败');
            }
        } catch (err) {
            alert('请求失败: ' + err.message);
        } finally {
            btn.disabled = false;
        }
    });
});
