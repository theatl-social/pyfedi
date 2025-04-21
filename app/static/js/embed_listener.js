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

function sendHeight() {
  const height = document.body.scrollHeight;
  window.parent.postMessage({
    type: 'setHeight',
    height: height,
    id: new URLSearchParams(location.hash.substring(1)).get('secret') || 0
  }, '*');
}

window.addEventListener('load', sendHeight);
new ResizeObserver(sendHeight).observe(document.body);


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
