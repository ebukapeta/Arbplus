/**
 * ArbPulse — Scanner API
 * Communicates with the Flask backend.
 *
 * Testnet rule: only ETH sends testnet:true to backend.
 * Stale-result guard: if the user switches chain mid-scan, results from the
 *   previous chain are silently discarded.
 */

const ScannerAPI = (() => {
  const BASE = '';

  let _scanInterval      = null;
  let _isScanning        = false;
  let _countdownInterval = null;
  let _contractAddress   = '';
  let _onResults = () => {};
  let _onStart   = () => {};
  let _onStop    = () => {};
  let _onError   = () => {};

  // Track which network + testnet state each scan was launched on
  let _scanStartNetwork = null;
  let _scanStartTestnet = null;

  function onResults(cb) { _onResults = cb; }
  function onStart(cb)   { _onStart   = cb; }
  function onStop(cb)    { _onStop    = cb; }
  function onError(cb)   { _onError   = cb; }
  function isScanning()  { return _isScanning; }
  function setContractAddress(addr) { _contractAddress = addr; }

  function buildConfig() {
    const network   = AppState.network;
    // Only ETH uses testnet — all other chains always send mainnet
    const isTestnet = network === 'eth' && AppState.isTestnet;
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
        baseTokens: activeBaseTokens.length ? activeBaseTokens : cfg.baseTokens.map(t => t.symbol),
        dexes:      activeDexes.length      ? activeDexes      : cfg.dexes,
      },
    };
  }

  async function runScan() {
    const payload = buildConfig();

    // Snapshot the network + testnet state at scan launch
    const launchNetwork = payload.network;
    const launchTestnet = payload.testnet;
    _scanStartNetwork = launchNetwork;
    _scanStartTestnet = launchTestnet;

    const mode = launchTestnet ? 'TESTNET' : 'MAINNET';
    AppLog.scan(
      `Scanning ${launchNetwork.toUpperCase()} [${mode}] — ` +
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

      // Stale-result guard: discard if user switched chain during the request
      const currentTestnet = AppState.network === 'eth' && AppState.isTestnet;
      if (AppState.network !== launchNetwork || currentTestnet !== launchTestnet) {
        AppLog.warn(`Discarding stale results from ${launchNetwork.toUpperCase()} (chain switched during scan)`);
        return;
      }

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
    if (!contractAddr) throw new Error('Contract address not set. Go to Scanner Config tab and enter your deployed contract address.');
    // Basic Ethereum address validation before sending to backend
    if (!/^0x[0-9a-fA-F]{40}$/.test(contractAddr)) throw new Error(`Invalid contract address: "${contractAddr}". Must be a 42-character hex address starting with 0x.`);
    // Persist per-chain whenever we use it
    localStorage.setItem(_contractKey(), contractAddr);

    const network   = AppState.network;
    const isTestnet = network === 'eth' && AppState.isTestnet;

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
    // Always ensure from is present — MetaMask rejects without it
    const tx = { ...unsignedTx };
    if (!tx.from) tx.from = WalletManager.getAddress();
    return await window.ethereum.request({ method: 'eth_sendTransaction', params: [tx] });
  }

  async function fetchHistory() {
    const resp = await fetch(`${BASE}/api/history`);
    const data = await resp.json();
    return data.history || [];
  }

  async function clearHistory() {
    await fetch(`${BASE}/api/history`, { method: 'DELETE' });
  }

  // ── Per-chain contract address storage ─────────────────────────────────
  // Key format: arbpulse_contract_<network>  e.g. arbpulse_contract_bsc
  // Testnet key: arbpulse_contract_eth_testnet
  function _contractKey() {
    const net = AppState.network;
    const test = net === 'eth' && AppState.isTestnet;
    return `arbpulse_contract_${net}${test ? '_testnet' : ''}`;
  }

  function _saveContractAddress() {
    const val = document.getElementById('cfg-contract')?.value?.trim() || '';
    if (val && /^0x[0-9a-fA-F]{40}$/.test(val)) {
      localStorage.setItem(_contractKey(), val);
    }
  }

  function _loadContractAddress() {
    const input = document.getElementById('cfg-contract');
    if (!input) return;
    const saved = localStorage.getItem(_contractKey()) || '';
    input.value = saved;
  }

  async function fetchConfig() {
    try {
      const resp = await fetch(`${BASE}/api/config`);
      const data = await resp.json();
      const input = document.getElementById('cfg-contract');
      if (!input) return;
      // Load saved address for this specific chain first
      const saved = localStorage.getItem(_contractKey()) || '';
      if (saved) {
        input.value = saved;
      } else {
        // Fall back to backend env config if nothing saved yet
        const addr = data[`${AppState.network}ContractAddress`] || '';
        if (addr) input.value = addr;
      }
    } catch {}
  }

  // Persist contract address whenever user types into the field
  document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('cfg-contract');
    if (input) {
      input.addEventListener('change', _saveContractAddress);
      input.addEventListener('blur',   _saveContractAddress);
    }
  });

  return {
    startScanning, stopScanning, runScan, executeTrade, sendTransactionEVM,
    fetchHistory, clearHistory, fetchConfig, isScanning,
    setContractAddress, onResults, onStart, onStop, onError,
  };
})();
