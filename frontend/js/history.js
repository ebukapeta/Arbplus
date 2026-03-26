/**
 * ArbPulse — History Manager
 * Manages trade history display and local persistence.
 */

const HistoryManager = (() => {
  let _history = [];

  function addEntry(entry) {
    _history.unshift(entry);
    if (_history.length > 500) _history.pop();
    _render();
    _updateStats();
  }

  function setHistory(entries) {
    _history = entries || [];
    _render();
    _updateStats();
  }

  function clear() {
    _history = [];
    _render();
    _updateStats();
  }

  function _updateStats() {
    const total   = _history.length;
    const success = _history.filter(h => h.status === 'success').length;
    const failed  = _history.filter(h => h.status === 'failed').length;
    const profit  = _history.filter(h => h.status === 'success').reduce((s,h) => s + (h.netProfitUsd||0), 0);

    setEl('hist-total',        total);
    setEl('hist-success',      success);
    setEl('hist-failed',       failed);
    setEl('hist-total-profit', formatUsd(profit));
  }

  function _render() {
    const tbody = document.getElementById('history-tbody');
    if (!tbody) return;

    if (!_history.length) {
      tbody.innerHTML = '<tr><td colspan="13" class="empty-row">No trade history yet</td></tr>';
      return;
    }

    const network = document.querySelector('.network-pill.active')?.dataset.network || 'bsc';
    const explorerBase = NETWORK_CONFIG[network]?.blockExplorerTx || 'https://bscscan.com/tx/';

    tbody.innerHTML = _history.map(h => {
      const txLink = h.txHash
        ? `<a class="tx-link" href="${explorerBase}${h.txHash}" target="_blank">${shortTxHash(h.txHash)}</a>`
        : '—';
      return `
<tr>
  <td>${formatTime(h.timestamp)}</td>
  <td style="font-weight:700;color:var(--text)">${h.pair || '—'}</td>
  <td>${h.buyDex || '—'}</td>
  <td>${h.sellDex || '—'}</td>
  <td style="font-family:var(--font-mono)">${formatSmallNum(h.buyPrice)}</td>
  <td style="font-family:var(--font-mono)">${formatSmallNum(h.sellPrice)}</td>
  <td style="color:var(--gold)">${formatPercent(h.spread)}</td>
  <td style="color:var(--cyan)">${h.flashLoanAsset || '—'}</td>
  <td style="color:var(--text)">${formatUsd(h.grossProfitUsd)}</td>
  <td style="color:var(--red)">${formatUsd((h.gasFee||0) + (h.dexFees||0))}</td>
  <td style="color:var(--green);font-weight:700">${formatUsd(h.netProfitUsd)}</td>
  <td>${txLink}</td>
  <td><span class="status-pill ${h.status}">${h.status}</span></td>
</tr>`;
    }).join('');
  }

  function formatSmallNum(n) {
    if (n == null || isNaN(n)) return '—';
    if (n < 0.001) return parseFloat(n).toFixed(10);
    if (n < 1)     return parseFloat(n).toFixed(8);
    return parseFloat(n).toFixed(4);
  }

  function setEl(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  return { addEntry, setHistory, clear };
})();
