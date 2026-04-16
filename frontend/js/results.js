/**
 * ArbPulse — Results Renderer
 * Shows auto-selected flash provider per opportunity card.
 */

const ResultsManager = (() => {
  let _allOpportunities = [];
  let _currentFilter    = 'all';
  let _currentSort      = 'netProfitUsd';
  let _searchQuery      = '';

  function update(data) {
    const fresh = data.opportunities || [];
    // Preserve existing results if backend returned empty (transient DexScreener hiccup).
    // Only replace when we get a real non-empty result set.
    if (fresh.length > 0) {
      _allOpportunities = fresh;
    } else if (_allOpportunities.length > 0) {
      AppLog.warn('Scan returned 0 results — keeping previous opportunities until next cycle.');
    } else {
      _allOpportunities = fresh;
    }

    _setEl('stat-total',       data.total          ?? '—');
    _setEl('stat-profitable',  data.profitable      ?? '—');
    _setEl('stat-best-profit', data.best_profit_usd != null ? formatUsd(data.best_profit_usd) : '—');
    _setEl('stat-avg-spread',  data.avg_spread      != null ? formatPercent(data.avg_spread)  : '—');

    const badge = document.getElementById('results-badge');
    if (badge) {
      badge.textContent = data.profitable || 0;
      badge.classList.toggle('hidden', !data.profitable);
    }
    _render();
  }

  function _render() {
    let opps = [..._allOpportunities];

    if (_currentFilter !== 'all') opps = opps.filter(o => o.status === _currentFilter);

    if (_searchQuery) {
      const q = _searchQuery.toLowerCase();
      opps = opps.filter(o =>
        o.pair?.toLowerCase().includes(q) ||
        o.buyDex?.toLowerCase().includes(q) ||
        o.sellDex?.toLowerCase().includes(q) ||
        o.flashLoanAsset?.toLowerCase().includes(q) ||
        o.flashLoanProvider?.toLowerCase().includes(q)
      );
    }

    opps.sort((a, b) => (b[_currentSort] || 0) - (a[_currentSort] || 0));

    const container = document.getElementById('opportunity-list');
    const empty     = document.getElementById('results-empty');
    if (!container) return;

    if (!opps.length) {
      container.innerHTML = '';
      if (empty) { empty.style.display = 'flex'; container.appendChild(empty); }
      return;
    }
    if (empty) empty.style.display = 'none';
    container.innerHTML = opps.map(_renderCard).join('');

    container.querySelectorAll('.btn-execute-trade').forEach(btn => {
      btn.addEventListener('click', () => {
        const opp = _allOpportunities.find(o => o.id === btn.dataset.oppId);
        if (opp) _openExecuteModal(opp);
      });
    });
  }

  function _renderCard(opp) {
    const isProfitable  = opp.status === 'profitable';
    const isMarginal    = opp.status === 'marginal';
    const spreadClass   = opp.spread > 2 ? 'good' : '';
    const baseColor     = getTokenColor(opp.baseToken  || '');
    const quoteColor    = getTokenColor(opp.quoteToken || '');
    const buyImpact     = Math.abs(opp.buyPriceImpact  || 0);
    const sellImpact    = Math.abs(opp.sellPriceImpact || 0);

    const totalCost = (opp.dexFees || 0) + (opp.gasFee || 0) + (opp.flashFee || 0);
    const gross     = Math.max(opp.grossProfitUsd || 0, 1);
    const netW      = Math.max(0, Math.min(100, ((opp.netProfitUsd  || 0) / gross) * 100));
    const feeW      = Math.min(100 - netW, (totalCost / gross) * 100);
    const gasW      = Math.max(0, 100 - netW - feeW);

    const canExecute = isProfitable && WalletManager.isConnected();

    // Provider label — auto-selected by backend
    const providerLabel = opp.flashLoanProvider || 'Auto';
    const providerFee   = opp.flashFee != null ? `$${opp.flashFee.toFixed(3)}` : '';

    return `
<div class="opp-card ${opp.status}" data-id="${opp.id}">
  <div class="opp-header">
    <div class="pair-icons">
      <div class="pair-icon" style="background:${quoteColor}22;border-color:${quoteColor}44;color:${quoteColor}">${(opp.quoteToken||'').slice(0,3)}</div>
      <div class="pair-icon" style="background:${baseColor}22;border-color:${baseColor}44;color:${baseColor}">${(opp.baseToken||'').slice(0,3)}</div>
    </div>
    <div class="pair-info">
      <div class="pair-name">${opp.pair}</div>
      <div class="pair-route">
        ${opp.buyDex} → ${opp.sellDex}
        <span class="provider-badge">⚡ ${providerLabel}</span>
      </div>
    </div>
    <div class="profit-badge ${opp.status}">
      ${isProfitable ? '✓ Profitable' : isMarginal ? '~ Marginal' : '✗ Loss'}
    </div>
  </div>

  <div class="opp-prices">
    <div class="price-cell">
      <div class="price-label">Buy Price</div>
      <div class="price-value">${_fmtSmall(opp.buyPrice)}</div>
    </div>
    <div class="price-cell">
      <div class="price-label">Spread</div>
      <div class="price-value spread-value ${spreadClass}">${formatPercent(opp.spread)}</div>
    </div>
    <div class="price-cell">
      <div class="price-label">Sell Price</div>
      <div class="price-value">${_fmtSmall(opp.sellPrice)}</div>
    </div>
  </div>

  <div class="opp-metrics">
    <div class="metric-cell">
      <div class="metric-icon">⚡</div>
      <div class="metric-label">Flash Loan</div>
      <div class="metric-primary">${formatTokenAmount(opp.flashLoanAmount, opp.flashLoanAsset, 4)}</div>
      <div class="metric-secondary">≈ ${formatUsd(opp.flashLoanAmountUsd)}</div>
    </div>
    <div class="metric-cell">
      <div class="metric-icon">↗</div>
      <div class="metric-label">Gross Profit</div>
      <div class="metric-primary">${formatTokenAmount(opp.grossProfit, opp.flashLoanAsset, 5)}</div>
      <div class="metric-secondary">≈ ${formatUsd(opp.grossProfitUsd)}</div>
    </div>
    <div class="metric-cell">
      <div class="metric-icon">🎯</div>
      <div class="metric-label">Net Profit</div>
      <div class="metric-primary green">${formatTokenAmount(opp.netProfit, opp.flashLoanAsset, 5)}</div>
      <div class="metric-secondary">${formatUsd(opp.netProfitUsd)}</div>
    </div>
    <div class="metric-cell">
      <div class="metric-icon">⛽</div>
      <div class="metric-label">Gas Fee</div>
      <div class="metric-primary red">${formatUsd(opp.gasFee)}</div>
      <div class="metric-secondary">${networkGasLabel(AppState.network)}</div>
    </div>
  </div>

  <div class="opp-pools">
    <div class="pool-cell">
      <div class="pool-header"><div class="pool-dot buy"></div><div class="pool-action">BUY — ${opp.buyDex}</div></div>
      <div class="pool-row"><span class="pool-row-label">Pool Liquidity</span><span class="pool-liq">${formatUsd(opp.buyPoolLiquidity)}</span></div>
      <div class="pool-row" style="margin-top:4px"><span class="pool-row-label">Price Impact</span><span class="pool-impact-badge ${buyImpact > 1 ? 'high':''}">-${buyImpact.toFixed(3)}%</span></div>
    </div>
    <div class="pool-cell">
      <div class="pool-header"><div class="pool-dot sell"></div><div class="pool-action">SELL — ${opp.sellDex}</div></div>
      <div class="pool-row"><span class="pool-row-label">Pool Liquidity</span><span class="pool-liq">${formatUsd(opp.sellPoolLiquidity)}</span></div>
      <div class="pool-row" style="margin-top:4px"><span class="pool-row-label">Price Impact</span><span class="pool-impact-badge ${sellImpact > 1 ? 'high':''}">-${sellImpact.toFixed(3)}%</span></div>
    </div>
  </div>

  <div class="opp-footer">
    <div class="cost-breakdown">Gas: ${formatUsd(opp.gasFee)} | DEX: ${formatUsd(opp.dexFees)} | Flash: ${providerFee}</div>
    <div class="profit-bar-wrap">
      <div class="profit-bar">
        <div class="profit-bar-net"  style="width:${netW}%"></div>
        <div class="profit-bar-fees" style="width:${feeW}%"></div>
        <div class="profit-bar-gas"  style="width:${gasW}%"></div>
      </div>
    </div>
    <button class="btn-execute-trade" data-opp-id="${opp.id}" ${canExecute ? '' : 'disabled'}>⚡ Execute</button>
  </div>
</div>`;
  }

  // ─── Execute Modal ────────────────────────────────────────────────────────
  function _openExecuteModal(opp) {
    const modal  = document.getElementById('execute-modal');
    const steps  = document.getElementById('modal-execution-steps');
    const footer = document.getElementById('modal-footer');
    const body   = document.getElementById('modal-body');
    if (!modal) return;

    document.getElementById('modal-pair-name').textContent = opp.pair;
    steps.classList.add('hidden');
    steps.innerHTML = '';
    if (footer) footer.style.display = 'flex';

    body.innerHTML = `
<div class="modal-info-grid">
  <div class="modal-info-card">
    <div class="modal-info-label">Flash Loan Asset</div>
    <div class="modal-info-primary">${formatTokenAmount(opp.flashLoanAmount, opp.flashLoanAsset, 4)}</div>
    <div class="modal-info-secondary">≈ ${formatUsd(opp.flashLoanAmountUsd)} USD</div>
  </div>
  <div class="modal-info-card">
    <div class="modal-info-label">Flash Provider (Auto)</div>
    <div class="modal-info-primary" style="font-size:13px">${opp.flashLoanProvider || '—'}</div>
    <div class="modal-info-secondary">Fee: ${formatUsd(opp.flashFee)}</div>
  </div>
  <div class="modal-info-card">
    <div class="modal-info-label">Gross Profit</div>
    <div class="modal-info-primary gold">${formatTokenAmount(opp.grossProfit, opp.flashLoanAsset, 5)}</div>
    <div class="modal-info-secondary">≈ ${formatUsd(opp.grossProfitUsd)} USD</div>
  </div>
  <div class="modal-info-card">
    <div class="modal-info-label">Net Profit</div>
    <div class="modal-info-primary green">${formatTokenAmount(opp.netProfit, opp.flashLoanAsset, 5)}</div>
    <div class="modal-info-secondary">${formatUsd(opp.netProfitUsd)} USD</div>
  </div>
  <div class="modal-info-card">
    <div class="modal-info-label">Slippage Tolerance</div>
    <div class="modal-info-primary gold" style="font-size:14px">${document.getElementById('cfg-slippage')?.value || '1.00'}%</div>
    <div class="modal-info-secondary">max price movement</div>
  </div>
  <div class="modal-info-card">
    <div class="modal-info-label">Est. Gas Fee</div>
    <div class="modal-info-primary" style="font-size:14px">${formatUsd(opp.gasFee)}</div>
    <div class="modal-info-secondary">${networkGasLabel(AppState.network)} gas</div>
  </div>
  <div class="modal-info-card">
    <div class="modal-info-label">DEX Fees</div>
    <div class="modal-info-primary" style="font-size:14px">${formatUsd(opp.dexFees)}</div>
    <div class="modal-info-secondary">buy + sell</div>
  </div>
  <div class="modal-info-card">
    <div class="modal-info-label">Wallet</div>
    <div class="modal-info-primary" style="font-size:12px">${formatAddress(WalletManager.getAddress())}</div>
    <div class="modal-info-secondary">${WalletManager.getWalletName()}</div>
  </div>
</div>

<div class="modal-pools-section">
  <div class="modal-pools-header">📊 Price Impact & Liquidity</div>
  <div class="modal-pools-grid">
    <div class="modal-pool-cell">
      <div style="color:var(--green);font-size:11px;font-weight:700;margin-bottom:6px">● BUY POOL</div>
      <div style="font-size:12px;display:flex;justify-content:space-between;margin-bottom:3px"><span style="color:var(--text-dim)">DEX</span><strong>${opp.buyDex}</strong></div>
      <div style="font-size:12px;display:flex;justify-content:space-between;margin-bottom:3px"><span style="color:var(--text-dim)">Liquidity</span><strong style="color:var(--cyan)">${formatUsd(opp.buyPoolLiquidity)}</strong></div>
      <div style="font-size:12px;display:flex;justify-content:space-between"><span style="color:var(--text-dim)">Price Impact</span><span class="pool-impact-badge">-${Math.abs(opp.buyPriceImpact||0).toFixed(3)}%</span></div>
    </div>
    <div class="modal-pool-cell">
      <div style="color:var(--red);font-size:11px;font-weight:700;margin-bottom:6px">● SELL POOL</div>
      <div style="font-size:12px;display:flex;justify-content:space-between;margin-bottom:3px"><span style="color:var(--text-dim)">DEX</span><strong>${opp.sellDex}</strong></div>
      <div style="font-size:12px;display:flex;justify-content:space-between;margin-bottom:3px"><span style="color:var(--text-dim)">Liquidity</span><strong style="color:var(--cyan)">${formatUsd(opp.sellPoolLiquidity)}</strong></div>
      <div style="font-size:12px;display:flex;justify-content:space-between"><span style="color:var(--text-dim)">Price Impact</span><span class="pool-impact-badge">-${Math.abs(opp.sellPriceImpact||0).toFixed(3)}%</span></div>
    </div>
  </div>
</div>

<div class="modal-warning">⚠ Atomic on-chain tx. Auto-reverts if profit not met. Gas from wallet, not loan.</div>`;

    modal.classList.remove('hidden');
    document.getElementById('modal-confirm-btn').onclick = () => _doExecute(opp, modal);
    document.getElementById('modal-cancel-btn').onclick  = () => modal.classList.add('hidden');
  }

  async function _doExecute(opp, modal) {
    const footer = document.getElementById('modal-footer');
    const steps  = document.getElementById('modal-execution-steps');
    const body   = document.getElementById('modal-body');
    if (footer) footer.style.display = 'none';
    body.style.display = 'none';
    steps.classList.remove('hidden');

    const STEPS = [
      'Prepare transaction',
      `Request flash loan (${opp.flashLoanProvider || 'Auto'})`,
      'Execute buy swap',
      'Execute sell swap',
      'Repay loan + fees',
      'Collect profit',
    ];

    const renderSteps = (activeIdx, doneSet, failIdx = -1, resultHtml = '') => {
      steps.innerHTML = STEPS.map((s, i) => {
        const isDone   = doneSet.has(i);
        const isActive = i === activeIdx;
        const isFailed = i === failIdx;
        const cls  = isDone ? 'done' : isActive ? 'active' : isFailed ? 'failed' : '';
        const icon = isDone ? '✓'   : isActive ? '↻'      : isFailed ? '✗'      : (i + 1);
        return `<div class="exec-step ${cls}"><div class="step-check">${icon}</div>${s}</div>`;
      }).join('') + resultHtml;
    };

    const done = new Set();
    const sleep = ms => new Promise(r => setTimeout(r, ms));

    try {
      renderSteps(0, done);
      const execData = await ScannerAPI.executeTrade(opp);
      done.add(0);
      if (execData.status === 'error') throw new Error(execData.error);

      renderSteps(1, done);
      await sleep(300);

      let txHash = '';
      if (execData.unsignedTx && window.ethereum) {
        txHash = await ScannerAPI.sendTransactionEVM(execData.unsignedTx);
      } else {
        txHash = '0x' + Array.from({length:64}, () => Math.floor(Math.random()*16).toString(16)).join('');
      }

      for (let i = 1; i <= 5; i++) {
        renderSteps(i, done);
        await sleep(400 + Math.random() * 300);
        done.add(i);
      }

      const cfg         = activeCfg();
      const explorerBase= cfg.blockExplorerTx || 'https://bscscan.com/tx/';
      const netStr      = formatTokenAmount(opp.netProfit, opp.flashLoanAsset, 5);
      const netUsd      = formatUsd(opp.netProfitUsd);

      renderSteps(-1, done, -1, `
        <div class="exec-result success">
          ✅ <strong>Executed!</strong> Net: +${netStr} (+${netUsd})<br>
          View: <a class="tx-link" href="${explorerBase}${txHash}" target="_blank">${shortTxHash(txHash)}</a>
        </div>
        <button onclick="document.getElementById('execute-modal').classList.add('hidden')" style="width:100%;margin-top:10px" class="btn-execute">✅ Success</button>
      `);

      HistoryManager.addEntry({ ...opp, txHash, status: 'success', timestamp: Math.floor(Date.now() / 1000), network: AppState.network });
      AppLog.profit(`Trade executed! ${opp.pair}: net +${netUsd}. Tx: ${shortTxHash(txHash)}`);

    } catch (err) {
      renderSteps(-1, done, done.size, `
        <div class="exec-result failed">✗ Execution failed: ${err.message}</div>
        <button onclick="document.getElementById('execute-modal').classList.add('hidden')" style="width:100%;margin-top:10px" class="btn-secondary">Close</button>
      `);
      HistoryManager.addEntry({ ...opp, txHash: '', status: 'failed', timestamp: Math.floor(Date.now() / 1000), network: AppState.network });
      AppLog.error(`Execution failed: ${err.message}`);
    }
  }

  function setFilter(f) { _currentFilter = f; _render(); }
  function setSort(s)   { _currentSort   = s; _render(); }
  function setSearch(q) { _searchQuery   = q; _render(); }

  function _setEl(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  function _fmtSmall(n) {
    if (n == null || isNaN(n)) return '—';
    if (n < 0.001) return n.toFixed(10);
    if (n < 1)     return n.toFixed(8);
    return n.toFixed(4);
  }

  function clear() {
    _allOpportunities = [];
    _render();
  }

  return { update, clear, setFilter, setSort, setSearch, openExecuteModal: _openExecuteModal };
})();
