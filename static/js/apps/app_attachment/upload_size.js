// 选文件时按 data-max-bytes 拦住，避免超限文件先上传再被服务器拒绝。
// 表单会被 HTMX 换掉，所以绑在 document 上。一页多块面板只绑一次。
(function () {
  if (window.__attachmentUploadSizeBound) return;
  window.__attachmentUploadSizeBound = true;

  function maxBytes(input) {
    var max = Number(input.getAttribute('data-max-bytes'));
    return max > 0 ? max : 0;
  }

  function oversized(input) {
    var max = maxBytes(input);
    var file = input.files && input.files[0];
    if (!max || !file || file.size <= max) return null;
    return file;
  }

  function showError(input, file) {
    var body = input.closest('.modal-body') || input.closest('form') || input.parentNode;
    var alert = body.querySelector('[data-upload-size-error]');
    if (!alert) {
      alert = document.createElement('div');
      alert.className = 'alert alert-danger';
      alert.setAttribute('data-upload-size-error', '');
      body.insertBefore(alert, body.firstChild);
    }
    var max = maxBytes(input);
    var maxMb = max / 1024 / 1024;
    var maxLabel = maxMb % 1 === 0 ? String(maxMb) : maxMb.toFixed(2);
    var actual = (file.size / 1024 / 1024).toFixed(2);
    alert.textContent = '文件大小不能超过 ' + maxLabel + 'MB。当前文件大小: ' + actual + 'MB';
  }

  function clearError(input) {
    var body = input.closest('.modal-body') || input.parentNode;
    var alert = body && body.querySelector('[data-upload-size-error]');
    if (alert) alert.remove();
  }

  document.addEventListener('change', function (event) {
    var input = event.target;
    if (!input.matches || !input.matches('input[type="file"][data-max-bytes]')) return;
    var file = oversized(input);
    if (!file) {
      clearError(input);
      return;
    }
    input.value = '';
    showError(input, file);
  }, true);

  document.addEventListener('submit', function (event) {
    var form = event.target;
    if (!form || !form.querySelector) return;
    var input = form.querySelector('input[type="file"][data-max-bytes]');
    if (!input) return;
    var file = oversized(input);
    if (!file) return;
    event.preventDefault();
    input.value = '';
    showError(input, file);
  }, true);
})();
