/**
 * ArbPulse — Main Application
 * Wires all modules together and handles UI interactions.
 */

// ─── Logger ──────────────────────────────────────────────────────────────────
const AppLog = (() => {
  function _append(msg, cls) {
    const container = document.getElementById('logs-container');
    if (!container) return;
    const el = document.createElement('div');
    el.className = `log-entry ${cls}`;
    el.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
    container.appendChild(el);
    container.scrollTop = container.scrollHeight;
  }
  return {
    info:   m => _append(m, 'info'),
    scan:   m => _append(m, 'scan'),
    profit: m => _append(m, 'profit'),
    warn:   m => _append(m, 'warn'),
    error:  m => _append(m, 'error'),
    exec:   m => _append(m, 'exec'),
  };
})();

// ─── App Init ─────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {

  let _activeNetwork = 'bsc';

  // ── Network switching ─────────────────────────────────────────────────────
  document.querySelectorAll('.network-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      document.querySelectorAll('.network-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      _activeNetwork = pill.dataset.network;
      // Tell WalletManager which network is active — does NOT disconnect any wallet
      WalletManager.setNetwork(_activeNetwork);
      _populateNetworkUI(_activeNetwork);
      AppLog.info(`Switched to ${_activeNetwork === 'bsc' ? 'BNB Chain' : 'Solana'} — wallet state preserved on both networks`);
      if (ScannerAPI.isScanning()) ScannerAPI.stopScanning();
    });
  });

  function _populateNetworkUI(network) {
    const cfg = NETWORK_CONFIG[network];

    // Flash loan providers
    const providerSelect = document.getElementById('cfg-flash-provider');
    if (providerSelect) {
      providerSelect.innerHTML = cfg.flashProviders.map(p =>
        `<option value="${p.value}">${p.label}</option>`
      ).join('');
    }

    // Base tokens
    const tokenGrid = document.getElementById('base-tokens-grid');
    if (tokenGrid) {
      tokenGrid.innerHTML = cfg.baseTokens.map(t => `
        <button class="token-pill" data-symbol="${t.symbol}">
          ${t.symbol} <span class="flash-icon">⚡</span>
        </button>
      `).join('');
      tokenGrid.querySelectorAll('.token-pill').forEach(pill => {
        pill.addEventListener('click', () => pill.classList.toggle('inactive'));
      });
    }

    // DEXes
    const dexGrid = document.getElementById('dex-pills-grid');
    if (dexGrid) {
      dexGrid.innerHTML = cfg.dexes.map(d => `
        <button class="dex-pill" data-dex="${d}">${d}</button>
      `).join('');
      dexGrid.querySelectorAll('.dex-pill').forEach(pill => {
        pill.addEventListener('click', () => pill.classList.toggle('inactive'));
      });
    }
  }

  // Init with BSC
  _populateNetworkUI('bsc');

  // ── Tab navigation ────────────────────────────────────────────────────────
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      const tab = document.getElementById(`tab-${btn.dataset.tab}`);
      if (tab) tab.classList.add('active');

      // Load history from backend when switching to history tab
      if (btn.dataset.tab === 'history') {
        ScannerAPI.fetchHistory().then(h => HistoryManager.setHistory(h)).catch(() => {});
      }
    });
  });

  // ── Wallet ────────────────────────────────────────────────────────────────
  document.getElementById('connect-wallet-btn')?.addEventListener('click', () => WalletManager.openPicker());
  document.getElementById('disconnect-btn')?.addEventListener('click',     () => WalletManager.disconnect());
  document.getElementById('wallet-picker-close')?.addEventListener('click', () => WalletManager.closePicker());

  // ── Scanner controls ──────────────────────────────────────────────────────
  document.getElementById('start-scan-btn')?.addEventListener('click', () => {
    ScannerAPI.startScanning();
  });
  document.getElementById('stop-scan-btn')?.addEventListener('click', () => {
    ScannerAPI.stopScanning();
  });

  ScannerAPI.onStart(() => {
    document.getElementById('start-scan-btn')?.classList.add('hidden');
    document.getElementById('stop-scan-btn')?.classList.remove('hidden');
    // Switch to results tab
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.querySelector('[data-tab="results"]')?.classList.add('active');
    document.getElementById('tab-results')?.classList.add('active');
    // Status bar
    const bar = document.getElementById('scan-status-bar');
    const txt = document.getElementById('scan-status-text');
    if (bar) bar.className = 'status-bar scanning';
    if (txt) txt.textContent = 'Scanning…';
    document.getElementById('scan-countdown')?.classList.remove('hidden');
  });

  ScannerAPI.onStop(() => {
    document.getElementById('start-scan-btn')?.classList.remove('hidden');
    document.getElementById('stop-scan-btn')?.classList.add('hidden');
    const bar = document.getElementById('scan-status-bar');
    const txt = document.getElementById('scan-status-text');
    if (bar) bar.className = 'status-bar idle';
    if (txt) txt.textContent = 'Idle — press Start Scanning';
  });

  ScannerAPI.onResults(data => {
    ResultsManager.update(data);
    const txt = document.getElementById('scan-status-text');
    if (txt) txt.textContent = `${data.profitable} profitable · next in ${document.getElementById('cfg-interval')?.value || 45}s`;
  });

  ScannerAPI.onError(msg => {
    const bar = document.getElementById('scan-status-bar');
    const txt = document.getElementById('scan-status-text');
    if (bar) bar.className = 'status-bar error';
    if (txt) txt.textContent = 'Error: ' + msg;
  });

  // ── Results filters / sort / search ───────────────────────────────────────
  document.querySelectorAll('.filter-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      ResultsManager.setFilter(tab.dataset.filter);
    });
  });

  document.getElementById('sort-select')?.addEventListener('change', e => {
    ResultsManager.setSort(e.target.value);
  });

  document.getElementById('search-input')?.addEventListener('input', e => {
    ResultsManager.setSearch(e.target.value);
  });

  // ── History ───────────────────────────────────────────────────────────────
  document.getElementById('clear-history-btn')?.addEventListener('click', async () => {
    await ScannerAPI.clearHistory();
    HistoryManager.clear();
    AppLog.info('Trade history cleared.');
  });

  // ── Logs ──────────────────────────────────────────────────────────────────
  document.getElementById('clear-logs-btn')?.addEventListener('click', () => {
    const c = document.getElementById('logs-container');
    if (c) c.innerHTML = '';
    AppLog.info('Logs cleared.');
  });

  // ── Modal close ───────────────────────────────────────────────────────────
  document.getElementById('modal-close-btn')?.addEventListener('click', () => {
    document.getElementById('execute-modal')?.classList.add('hidden');
  });
  document.getElementById('execute-modal')?.addEventListener('click', e => {
    if (e.target === e.currentTarget) e.currentTarget.classList.add('hidden');
  });

  // ── Fetch backend config on load ──────────────────────────────────────────
  ScannerAPI.fetchConfig();

  AppLog.info('ArbPulse initialised. Select network, configure scanner, connect wallet.');
});
