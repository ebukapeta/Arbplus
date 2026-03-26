/**
 * ArbPulse — Scanner API
 * Communicates with the Flask backend to scan DEXes and execute trades.
 */

const ScannerAPI = (() => {
  const BASE = '';  // same origin; in dev set to 'http://localhost:5000'

  let _scanInterval = null;
  let _isScanning = false;
  let _countdownInterval = null;
  let _contractAddress = '';

  // Callbacks
  let _onResults = () => {};
  let _onStart   = () => {};
  let _onStop    = () => {};
  let _onError   = () => {};

  function onResults(cb) { _onResults = cb; }
  function onStart(cb)   { _onStart   = cb; }
  function onStop(cb)    { _onStop    = cb; }
  function onError(cb)   { _onError   = cb; }

  function isScanning() { return _isScanning; }

  function setContractAddress(addr) { _contractAddress = addr; }

  function buildConfig() {
    const network = document.querySelector('.network-pill.active')?.dataset.network || 'bsc';
    const netCfg = NETWORK_CONFIG[network];

    const activeBaseTokens = Array.from(
      document.querySelectorAll('.token-pill:not(.inactive)')
    ).map(el => el.dataset.symbol);

    const activeDexes = Array.from(
      document.querySelectorAll('.dex-pill:not(.inactive)')
    ).map(el => el.dataset.dex);

    return {
      network,
      config: {
        minNetProfitPct:  parseFloat(document.getElementById('cfg-min-profit')?.value || 0.3),
        slippageTolerance:parseFloat(document.getElementById('cfg-slippage')?.value || 0.5),
        minLiquidityUsd:  parseFloat(document.getElementById('cfg-min-liq')?.value || 25000),
        flashLoanProvider:document.getElementById('cfg-flash-provider')?.value || netCfg.flashProviders[0].value,
        baseTokens:       activeBaseTokens.length ? activeBaseTokens : netCfg.baseTokens.map(t => t.symbol),
        dexes:            activeDexes.length ? activeDexes : netCfg.dexes,
      },
    };
  }

  async function runScan() {
    const payload = buildConfig();
    AppLog.scan(`Scanning ${payload.network.toUpperCase()} — ${payload.config.dexes.length} DEXes, ${payload.config.baseTokens.length} base tokens...`);

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
        `Scan complete — ${data.total} opportunities, ${data.profitable} profitable. ` +
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

    // Immediate first scan
    runScan();

    // Recurring scans
    const intervalSec = parseInt(document.getElementById('cfg-interval')?.value || 45);
    _scanInterval = setInterval(runScan, intervalSec * 1000);

    // Countdown timer
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
    _scanInterval = null;
    _countdownInterval = null;
    const countdownEl = document.getElementById('scan-countdown');
    if (countdownEl) countdownEl.classList.add('hidden');
    _onStop();
    AppLog.info('Scanning stopped.');
  }

  async function executeTrade(opportunity) {
    const walletAddress = WalletManager.getAddress();
    if (!walletAddress) {
      throw new Error('Wallet not connected');
    }
    const contractAddr = document.getElementById('cfg-contract')?.value?.trim() || _contractAddress;
    if (!contractAddr) {
      throw new Error('Smart contract address not set. Enter it in Scanner Config.');
    }

    const network = document.querySelector('.network-pill.active')?.dataset.network || 'bsc';

    AppLog.exec(`Building flash loan tx for ${opportunity.pair} (${opportunity.buyDex} → ${opportunity.sellDex})...`);

    const resp = await fetch(`${BASE}/api/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ network, opportunity, wallet: walletAddress, contractAddress: contractAddr }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (data.error) throw new Error(data.error);
    return data;
  }

  async function sendTransactionEVM(unsignedTx) {
    if (!window.ethereum) throw new Error('MetaMask not available');
    const txHash = await window.ethereum.request({
      method: 'eth_sendTransaction',
      params: [unsignedTx],
    });
    return txHash;
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
      if (data.bscContractAddress) {
        const input = document.getElementById('cfg-contract');
        if (input && !input.value) input.value = data.bscContractAddress;
      }
    } catch {}
  }

  return {
    startScanning, stopScanning, runScan, executeTrade, sendTransactionEVM,
    fetchHistory, clearHistory, fetchConfig, isScanning,
    setContractAddress, onResults, onStart, onStop, onError,
  };
})();
