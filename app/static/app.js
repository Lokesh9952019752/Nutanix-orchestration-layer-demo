(function () {
  const strip = document.querySelector('[data-status-url]');
  if (!strip) return;
  async function refreshStatus() {
    try {
      const response = await fetch(strip.dataset.statusUrl, { headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      const parts = Object.entries(payload.environments).map(([key, value]) => {
        return value.ok ? `${key}: ${value.vm_count} VMs` : `${key}: ${value.message}`;
      });
      strip.textContent = parts.join(' · ');
    } catch (error) {
      strip.textContent = `Status refresh failed: ${error}`;
    }
  }
  refreshStatus();
  setInterval(refreshStatus, 30000);
})();
