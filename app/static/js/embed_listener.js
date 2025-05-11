window.addEventListener('message', function (e) {
  var data = e.data || {};
  if (typeof data !== 'object' || data.type !== 'setHeight') return;

  var height = document.body.scrollHeight;

  e.source.postMessage({
    type: 'setHeight',
    id: data.id,
    height: height,
  }, '*');
});

function copyToClipboard() {
  const textarea = document.getElementById("embedCode");
  textarea.select();
  textarea.setSelectionRange(0, 99999); // For mobile devices

  navigator.clipboard.writeText(textarea.value)
    .then(() => {
      alert("Embed code has been copied to the clipboard!");
    })
    .catch(err => {
      console.error("Failed to copy: ", err);
    });
}

document.addEventListener("DOMContentLoaded", function () {
  const button = document.getElementById("copyToClipboardButton");
  if (button) {
    button.addEventListener("click", copyToClipboard);
  }
});
