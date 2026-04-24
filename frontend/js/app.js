/**
 * ArbPulse — Main Application
 * Testnet mode activates ONLY for Ethereum (Sepolia).
 * All other chains always stay on mainnet regardless of the toggle.
 */

// ─── Logger ──────────────────────────────────────────────────────────────────
const AppLog = (() => {
  function _append(msg, cls) {
    const c = document.getElementById('logs-container');
    if (!c) return;
    const el = document.createElement('div');
    el.className = `log-entry ${cls}`;
    el.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
    c.appendChild(el);
    c.scrollTop = c.scrollHeight;
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

  // ── Testnet/Mainnet toggle ────────────────────────────────────────────────
  const testnetToggle = document.getElementById('testnet-toggle');
  const testnetBanner = document.getElementById('testnet-banner');

  function applyNetworkMode() {
    const isActive = effectiveIsTestnet(AppState.network);
    document.body.classList.toggle('testnet-active', isActive);
    if (testnetBanner) testnetBanner.classList.toggle('hidden', !isActive);
    _updateScannerModeIndicator();
    _populateNetworkUI(AppState.network);

    if (isActive) {
      AppLog.warn(`⚠ TESTNET mode — ${activeCfg().name} (Ethereum Sepolia only)`);
    } else {
      const net = AppState.network !== 'eth'
        ? `${activeCfg().name} (always mainnet)`
        : `${activeCfg().name} · Mainnet`;
      AppLog.info(`✓ Mainnet mode — ${net}`);
    }
    if (ScannerAPI.isScanning()) ScannerAPI.stopScanning();
  }

  testnetToggle?.addEventListener('change', () => {
    AppState.isTestnet = testnetToggle.checked;

    if (AppState.isTestnet) {
      // Testnet = Ethereum only. Force-switch to ETH and activate its pill.
      AppState.network = 'eth';
      document.querySelectorAll('.network-pill').forEach(p => p.classList.remove('active'));
      document.querySelector('.network-pill[data-network="eth"]')?.classList.add('active');
    }

    WalletManager.setNetwork(AppState.network);
    applyNetworkMode();
  });

  // ── Network switching ─────────────────────────────────────────────────────
  document.querySelectorAll('.network-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      document.querySelectorAll('.network-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      AppState.network = pill.dataset.network;
      WalletManager.setNetwork(AppState.network);
      _populateNetworkUI(AppState.network);
      _updateScannerModeIndicator();

      // Clear stale results immediately on chain switch
      ResultsManager.clear();
      // Clear contract address field immediately so old chain's address
      // doesn't show while the async fetchConfig loads the new one
      const contractInput = document.getElementById('cfg-contract');
      if (contractInput) contractInput.value = '';
      // Load saved contract address for this chain
      ScannerAPI.fetchConfig();

      const cfg = activeCfg();
      const isTestnetActive = effectiveIsTestnet(AppState.network);
      AppLog.info(`Switched to ${cfg.name}${isTestnetActive ? ' (Testnet)' : ' (Mainnet)'}`);
      if (ScannerAPI.isScanning()) ScannerAPI.stopScanning();
    });
  });

  function _updateScannerModeIndicator() {
    const cfg       = activeCfg();
    const indicator = document.getElementById('scanner-mode-indicator');
    const text      = document.getElementById('scanner-mode-text');
    if (!indicator || !text) return;

    const isTestnetActive = effectiveIsTestnet(AppState.network);
    const mode = isTestnetActive ? 'Testnet' : 'Mainnet';
    text.textContent = `${cfg.name} · ${mode}`;
    indicator.classList.toggle('testnet', isTestnetActive);
    indicator.classList.toggle('mainnet', !isTestnetActive);
  }

  function _populateNetworkUI(network) {
    const cfg = activeCfg(); // honours effectiveIsTestnet internally

    // Base tokens
    const tokenGrid = document.getElementById('base-tokens-grid');
    if (tokenGrid) {
      tokenGrid.innerHTML = cfg.baseTokens.map(t => `
        <button class="token-pill" data-symbol="${t.symbol}">
          ${t.symbol} <span class="flash-icon">⚡</span>
        </button>
      `).join('');
      tokenGrid.querySelectorAll('.token-pill').forEach(p =>
        p.addEventListener('click', () => p.classList.toggle('inactive'))
      );
    }

    // DEXes
    const dexGrid = document.getElementById('dex-pills-grid');
    if (dexGrid) {
      dexGrid.innerHTML = cfg.dexes.map(d => `
        <button class="dex-pill" data-dex="${d}">${d}</button>
      `).join('');
      dexGrid.querySelectorAll('.dex-pill').forEach(p =>
        p.addEventListener('click', () => p.classList.toggle('inactive'))
      );
    }
  }

  // Init with BSC mainnet
  _populateNetworkUI('bsc');
  _updateScannerModeIndicator();

  // ── Tab navigation ────────────────────────────────────────────────────────
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      const tab = document.getElementById(`tab-${btn.dataset.tab}`);
      if (tab) tab.classList.add('active');
      if (btn.dataset.tab === 'history') {
        ScannerAPI.fetchHistory().then(h => HistoryManager.setHistory(h)).catch(() => {});
      }
    });
  });

  // ── Wallet ────────────────────────────────────────────────────────────────
  document.getElementById('connect-wallet-btn')?.addEventListener('click', () => WalletManager.openPicker());
  document.getElementById('disconnect-btn')?.addEventListener('click',     () => WalletManager.disconnect());
  document.getElementById('wallet-picker-close')?.addEventListener('click',() => WalletManager.closePicker());

  // ── Scanner controls ──────────────────────────────────────────────────────
  document.getElementById('start-scan-btn')?.addEventListener('click', () => ScannerAPI.startScanning());
  document.getElementById('stop-scan-btn')?.addEventListener('click',  () => ScannerAPI.stopScanning());

  ScannerAPI.onStart(() => {
    document.getElementById('start-scan-btn')?.classList.add('hidden');
    document.getElementById('stop-scan-btn')?.classList.remove('hidden');
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.querySelector('[data-tab="results"]')?.classList.add('active');
    document.getElementById('tab-results')?.classList.add('active');
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
    const interval = document.getElementById('cfg-interval')?.value || 30;
    if (txt) txt.textContent = `${data.profitable} profitable · next in ${interval}s`;
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

  document.getElementById('sort-select')?.addEventListener('change', e => ResultsManager.setSort(e.target.value));
  document.getElementById('search-input')?.addEventListener('input', e => ResultsManager.setSearch(e.target.value));

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
  document.getElementById('modal-close-btn')?.addEventListener('click', () =>
    document.getElementById('execute-modal')?.classList.add('hidden')
  );
  document.getElementById('execute-modal')?.addEventListener('click', e => {
    if (e.target === e.currentTarget) e.currentTarget.classList.add('hidden');
  });

  ScannerAPI.fetchConfig();
  AppLog.info('ArbPulse initialised. Testnet mode active for Ethereum only (Sepolia). All other chains always use mainnet.');
});
