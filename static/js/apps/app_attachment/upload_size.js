// 点「校验」才看 file.size。通过才放开上传按钮。不监听 document，也不改 input.value。
window.attachmentUploadSize = {
  check: function (button) {
    var form = button.closest('form');
    var input = form && form.querySelector('input[type="file"][data-max-bytes]');
    var submit = form && form.querySelector('[data-upload-submit]');
    if (!input || !submit) return;

    var file = input.files && input.files[0];
    if (!file) {
      submit.disabled = true;
      this._show(input, '请先选择文件。', true);
      return;
    }

    var max = Number(input.getAttribute('data-max-bytes'));
    if (max > 0 && file.size > max) {
      submit.disabled = true;
      var maxMb = max / 1024 / 1024;
      var maxLabel = maxMb % 1 === 0 ? String(maxMb) : maxMb.toFixed(2);
      var actual = (file.size / 1024 / 1024).toFixed(2);
      this._show(input, '文件大小不能超过 ' + maxLabel + 'MB。当前文件大小: ' + actual + 'MB', true);
      return;
    }

    submit.disabled = false;
    this._show(input, '文件大小符合要求，可以上传', false);
  },

  reset: function (input) {
    var form = input.closest('form');
    var submit = form && form.querySelector('[data-upload-submit]');
    if (submit) submit.disabled = true;
    var body = input.closest('.modal-body') || input.parentNode;
    var alert = body && body.querySelector('[data-upload-size-error]');
    if (alert) alert.remove();
  },

  _show: function (input, text, isError) {
    var body = input.closest('.modal-body') || input.closest('form') || input.parentNode;
    var alert = body.querySelector('[data-upload-size-error]');
    if (!alert) {
      alert = document.createElement('div');
      alert.setAttribute('data-upload-size-error', '');
      body.insertBefore(alert, body.firstChild);
    }
    alert.className = isError ? 'alert alert-danger' : 'alert alert-success';
    alert.textContent = text;
  }
};
