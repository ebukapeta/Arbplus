/**
 * ArbPulse — Scanner API
 * Communicates with the Flask backend. Flash provider is chosen automatically by backend.
 */

const ScannerAPI = (() => {
  const BASE = '';

  let _scanInterval     = null;
  let _isScanning       = false;
  let _countdownInterval= null;
  let _contractAddress  = '';
  let _onResults = () => {};
  let _onStart   = () => {};
  let _onStop    = () => {};
  let _onError   = () => {};

  function onResults(cb) { _onResults = cb; }
  function onStart(cb)   { _onStart   = cb; }
  function onStop(cb)    { _onStop    = cb; }
  function onError(cb)   { _onError   = cb; }
  function isScanning()  { return _isScanning; }
  function setContractAddress(addr) { _contractAddress = addr; }

  function buildConfig() {
    const network   = AppState.network;
    const isTestnet = AppState.isTestnet;
    const cfg       = activeCfg();

    const activeBaseTokens = Array.from(
      document.querySelectorAll('.token-pill:not(.inactive)')
    ).map(el => el.dataset.symbol);

    const activeDexes = Array.from(
      document.querySelectorAll('.dex-pill:not(.inactive)')
    ).map(el => el.dataset.dex);

    return {
      network,
      testnet: isTestnet,
      config: {
        minNetProfitPct:   parseFloat(document.getElementById('cfg-min-profit')?.value  || 0.10),
        slippageTolerance: parseFloat(document.getElementById('cfg-slippage')?.value    || 1.00),
        minLiquidityUsd:   parseFloat(document.getElementById('cfg-min-liq')?.value     || 2000),
        // No flashLoanProvider — backend auto-selects cheapest with reserves
        baseTokens: activeBaseTokens.length ? activeBaseTokens : cfg.baseTokens.map(t => t.symbol),
        dexes:      activeDexes.length      ? activeDexes      : cfg.dexes,
      },
    };
  }

  async function runScan() {
    const payload = buildConfig();
    const mode    = payload.testnet ? 'TESTNET' : 'MAINNET';
    AppLog.scan(
      `Scanning ${payload.network.toUpperCase()} [${mode}] — ` +
      `${payload.config.dexes.length} DEXes, ${payload.config.baseTokens.length} base tokens…`
    );

    try {
      const resp = await fetch(`${BASE}/api/scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      if (data.error) throw new Error(data.error);

      AppLog.profit(
        `Scan complete — ${data.total} opps, ${data.profitable} profitable. ` +
        `Best: ${formatUsd(data.best_profit_usd)}. Avg spread: ${formatPercent(data.avg_spread)}`
      );
      _onResults(data);
    } catch (err) {
      AppLog.error(`Scan failed: ${err.message}`);
      _onError(err.message);
    }
  }

  function startScanning() {
    if (_isScanning) return;
    _isScanning = true;
    _onStart();
    runScan();

    const intervalSec = parseInt(document.getElementById('cfg-interval')?.value || 30);
    _scanInterval = setInterval(runScan, intervalSec * 1000);

    let remaining = intervalSec;
    const countdownEl = document.getElementById('scan-countdown');
    if (countdownEl) {
      countdownEl.classList.remove('hidden');
      countdownEl.textContent = `next in ${remaining}s`;
      _countdownInterval = setInterval(() => {
        remaining--;
        if (remaining <= 0) remaining = intervalSec;
        countdownEl.textContent = `next in ${remaining}s`;
      }, 1000);
    }
  }

  function stopScanning() {
    if (!_isScanning) return;
    _isScanning = false;
    clearInterval(_scanInterval);
    clearInterval(_countdownInterval);
    _scanInterval = _countdownInterval = null;
    const countdownEl = document.getElementById('scan-countdown');
    if (countdownEl) countdownEl.classList.add('hidden');
    _onStop();
    AppLog.info('Scanning stopped.');
  }

  async function executeTrade(opportunity) {
    const walletAddress = WalletManager.getAddress();
    if (!walletAddress) throw new Error('Wallet not connected');

    const contractAddr = document.getElementById('cfg-contract')?.value?.trim() || _contractAddress;
    if (!contractAddr) throw new Error('Smart contract address not set. Enter it in Scanner Config.');

    const network   = AppState.network;
    const isTestnet = AppState.isTestnet;

    AppLog.exec(`Building flash loan tx for ${opportunity.pair} (${opportunity.buyDex} → ${opportunity.sellDex})…`);

    const resp = await fetch(`${BASE}/api/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ network, testnet: isTestnet, opportunity, wallet: walletAddress, contractAddress: contractAddr }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (data.error) throw new Error(data.error);
    return data;
  }

  async function sendTransactionEVM(unsignedTx) {
    if (!window.ethereum) throw new Error('MetaMask not available');
    return await window.ethereum.request({ method: 'eth_sendTransaction', params: [unsignedTx] });
  }

  async function fetchHistory() {
    const resp = await fetch(`${BASE}/api/history`);
    const data = await resp.json();
    return data.history || [];
  }

  async function clearHistory() {
    await fetch(`${BASE}/api/history`, { method: 'DELETE' });
  }

  async function fetchConfig() {
    try {
      const resp = await fetch(`${BASE}/api/config`);
      const data = await resp.json();
      // Fill contract address from env if not already set
      const input = document.getElementById('cfg-contract');
      if (input && !input.value) {
        const addr = data[`${AppState.network}ContractAddress`] || data.bscContractAddress || '';
        if (addr) input.value = addr;
      }
    } catch {}
  }

  return {
    startScanning, stopScanning, runScan, executeTrade, sendTransactionEVM,
    fetchHistory, clearHistory, fetchConfig, isScanning,
    setContractAddress, onResults, onStart, onStop, onError,
  };
})();
