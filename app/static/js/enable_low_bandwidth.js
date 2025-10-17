(function() {
  // Do nothing if low_bandwidth cookie already exists
  if(document.cookie.includes('low_bandwidth')) return;

  const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
  if (!conn) return; // API not supported

  const slowTypes = ['slow-2g', '2g', '3g'];

  if (slowTypes.includes(conn.effectiveType)) {
    // Set cookie for 300 days
    document.cookie = "low_bandwidth=1; path=/; max-age=" + (60 * 60 * 24 * 300);

    // Stop page loading and reload
    window.stop();
    location.reload();
  }
})();
