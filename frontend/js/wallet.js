/**
 * ArbPulse — Wallet Manager
 * Per-network wallet state: switching networks NEVER disconnects another network's wallet.
 * BSC: MetaMask, Trust Wallet, Binance Wallet, WalletConnect
 * Solana: Phantom, Solflare, Backpack, Coinbase Wallet
 */

const WalletManager = (() => {
  // Each network maintains its own independent wallet connection
  const _state = {
    bsc:    { connected: false, address: '', walletName: '', provider: null },
    solana: { connected: false, address: '', walletName: '', provider: null },
  };

  let _activeNetwork = 'bsc';
  let _onChangeCallbacks = [];

  // ─── Wallet options per network ──────────────────────────────────────────
  const WALLET_OPTIONS = {
    bsc: [
      { id: 'metamask',     name: 'MetaMask',       desc: 'Most popular EVM wallet',           icon: '🦊',  detected: () => !!window.ethereum?.isMetaMask },
      { id: 'trust',        name: 'Trust Wallet',   desc: 'Mobile-first multichain wallet',    icon: '🛡️', detected: () => !!window.ethereum?.isTrust },
      { id: 'binance',      name: 'Binance Wallet', desc: 'Official Binance Web3 wallet',      icon: '⬡',   detected: () => !!window.BinanceChain },
      { id: 'walletconnect',name: 'WalletConnect',  desc: 'Connect any mobile wallet via QR',  icon: '🔗',  detected: () => false },
    ],
    solana: [
      { id: 'phantom',  name: 'Phantom',         desc: 'Most popular Solana wallet',        icon: '👻', detected: () => !!window.solana?.isPhantom },
      { id: 'solflare', name: 'Solflare',         desc: 'Feature-rich Solana wallet',        icon: '☀️', detected: () => !!window.solflare },
      { id: 'backpack', name: 'Backpack',          desc: 'Multi-chain xNFT wallet',           icon: '🎒', detected: () => !!window.xnft },
      { id: 'coinbase', name: 'Coinbase Wallet',   desc: 'Easy onboarding Web3 wallet',       icon: '🔵', detected: () => !!window.coinbaseWalletExtension },
    ],
  };

  // ─── Public API ───────────────────────────────────────────────────────────
  function onWalletChange(cb) { _onChangeCallbacks.push(cb); }
  function getAddress()       { return _state[_activeNetwork].address; }
  function isConnected()      { return _state[_activeNetwork].connected; }
  function getNetwork()       { return _activeNetwork; }
  function getWalletName()    { return _state[_activeNetwork].walletName; }

  function setNetwork(network) {
    _activeNetwork = network;
    // Restore wallet UI for the newly active network without touching the other
    _updateUI();
    _emit();
  }

  // ─── Open wallet picker ────────────────────────────────────────────────
  function openPicker() {
    const modal       = document.getElementById('wallet-picker-modal');
    const titleEl     = document.getElementById('wallet-picker-title');
    const netLabelEl  = document.getElementById('wallet-picker-network-label');
    const listEl      = document.getElementById('wallet-picker-list');
    if (!modal) return;

    const netName = _activeNetwork === 'bsc' ? 'BNB Chain' : 'Solana';
    titleEl.textContent    = `Connect to ${netName}`;
    netLabelEl.textContent = _activeNetwork === 'bsc' ? 'EVM Wallets' : 'Solana Wallets';

    const wallets = WALLET_OPTIONS[_activeNetwork];
    listEl.innerHTML = wallets.map(w => {
      const det = w.detected();
      return `
        <div class="wallet-option ${det ? 'detected' : ''}" data-wallet-id="${w.id}" data-wallet-name="${w.name}">
          <div class="wallet-option-icon">${w.icon}</div>
          <div class="wallet-option-info">
            <div class="wallet-option-name">${w.name}</div>
            <div class="wallet-option-desc">${w.desc}</div>
          </div>
          <span class="wallet-status-badge ${det ? 'detected' : 'install'}">${det ? 'Detected' : 'Install'}</span>
        </div>`;
    }).join('');

    // Attach click handlers
    listEl.querySelectorAll('.wallet-option').forEach(el => {
      el.addEventListener('click', () => {
        const walletId   = el.dataset.walletId;
        const walletName = el.dataset.walletName;
        closePicker();
        _connectWallet(walletId, walletName);
      });
    });

    modal.classList.remove('hidden');

    // Close on backdrop click
    modal.onclick = (e) => { if (e.target === modal) closePicker(); };
  }

  function closePicker() {
    const modal = document.getElementById('wallet-picker-modal');
    if (modal) modal.classList.add('hidden');
  }

  // ─── Connect ──────────────────────────────────────────────────────────
  async function _connectWallet(walletId, walletName) {
    if (_activeNetwork === 'bsc') {
      await _connectEVM(walletId, walletName);
    } else {
      await _connectSolana(walletId, walletName);
    }
  }

  async function _connectEVM(walletId, walletName) {
    const provider = window.ethereum || window.BinanceChain;
    if (!provider) {
      _showError(`${walletName} not detected. Please install it and refresh.`);
      return;
    }
    try {
      const accounts = await provider.request({ method: 'eth_requestAccounts' });
      if (!accounts.length) throw new Error('No accounts returned');

      // Switch to BSC (chainId 56)
      try {
        await provider.request({
          method: 'wallet_switchEthereumChain',
          params: [{ chainId: '0x38' }],
        });
      } catch (switchErr) {
        if (switchErr.code === 4902) {
          await provider.request({
            method: 'wallet_addEthereumChain',
            params: [{
              chainId: '0x38',
              chainName: 'BNB Smart Chain',
              nativeCurrency: { name: 'BNB', symbol: 'BNB', decimals: 18 },
              rpcUrls: ['https://bsc-dataseed1.binance.org/'],
              blockExplorerUrls: ['https://bscscan.com'],
            }],
          });
        }
      }

      _state.bsc.connected   = true;
      _state.bsc.address     = accounts[0];
      _state.bsc.walletName  = walletName;
      _state.bsc.provider    = provider;

      provider.on('accountsChanged', (accs) => {
        _state.bsc.connected = accs.length > 0;
        _state.bsc.address   = accs[0] || '';
        if (_activeNetwork === 'bsc') { _updateUI(); _emit(); }
      });
      provider.on('chainChanged', () => window.location.reload());

      _updateUI(); _emit();
      AppLog.info(`${walletName} connected on BNB Chain: ${_fmtAddr(accounts[0])}`);
    } catch (e) {
      AppLog.error(`${walletName} connection failed: ${e.message}`);
      _showError(e.message);
    }
  }

  async function _connectSolana(walletId, walletName) {
    const solWallet = walletId === 'phantom'  ? window.phantom?.solana || window.solana
                    : walletId === 'solflare' ? window.solflare
                    : walletId === 'backpack' ? window.xnft?.solana
                    : null;

    if (!solWallet) {
      _showError(`${walletName} not detected. Please install it and refresh.`);
      return;
    }
    try {
      const resp = await solWallet.connect();
      const address = resp.publicKey.toString();

      _state.solana.connected  = true;
      _state.solana.address    = address;
      _state.solana.walletName = walletName;
      _state.solana.provider   = solWallet;

      solWallet.on('disconnect', () => {
        _state.solana.connected = false;
        _state.solana.address   = '';
        if (_activeNetwork === 'solana') { _updateUI(); _emit(); }
      });

      _updateUI(); _emit();
      AppLog.info(`${walletName} connected on Solana: ${_fmtAddr(address)}`);
    } catch (e) {
      AppLog.error(`${walletName} connection failed: ${e.message}`);
      _showError(e.message);
    }
  }

  // ─── Disconnect ───────────────────────────────────────────────────────
  async function disconnect() {
    const net = _activeNetwork;
    const name = _state[net].walletName;

    if (net === 'solana' && _state.solana.provider) {
      try { await _state.solana.provider.disconnect(); } catch {}
    }

    _state[net].connected  = false;
    _state[net].address    = '';
    _state[net].walletName = '';
    _state[net].provider   = null;

    _updateUI(); _emit();
    AppLog.info(`${name} disconnected from ${net === 'bsc' ? 'BNB Chain' : 'Solana'}.`);
  }

  // ─── UI update ────────────────────────────────────────────────────────
  function _updateUI() {
    const ws = _state[_activeNetwork];
    const connectBtn  = document.getElementById('connect-wallet-btn');
    const connectedDiv= document.getElementById('wallet-connected');
    const addrSpan    = document.getElementById('wallet-address');
    const iconImg     = document.getElementById('wallet-icon');

    if (ws.connected) {
      if (connectBtn)   connectBtn.classList.add('hidden');
      if (connectedDiv) connectedDiv.classList.remove('hidden');
      if (addrSpan)     addrSpan.textContent = _fmtAddr(ws.address);
      if (iconImg)      iconImg.src = _walletIconSrc(ws.walletName);
    } else {
      if (connectBtn)   connectBtn.classList.remove('hidden');
      if (connectedDiv) connectedDiv.classList.add('hidden');
    }

    // Update the green connected-dot indicator on each network pill
    ['bsc', 'solana'].forEach(net => {
      const pill = document.getElementById(`net-pill-${net}`);
      const dot  = document.getElementById(`net-ci-${net}`);
      if (pill) pill.classList.toggle('wallet-connected-on', _state[net].connected);
      if (dot)  dot.style.display = _state[net].connected ? 'block' : 'none';
    });
  }

  // ─── Helpers ──────────────────────────────────────────────────────────
  function _emit() {
    _onChangeCallbacks.forEach(cb => cb({
      address: _state[_activeNetwork].address,
      network: _activeNetwork,
      connected: _state[_activeNetwork].connected,
    }));
  }

  function _fmtAddr(addr) {
    if (!addr) return '';
    return addr.slice(0, 6) + '...' + addr.slice(-4);
  }

  function _walletIconSrc(name) {
    const icons = {
      'MetaMask':       'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96"><circle cx="48" cy="48" r="48" fill="#e8831d"/><text x="48" y="62" text-anchor="middle" fill="white" font-size="36">🦊</text></svg>'),
      'Phantom':        'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96"><circle cx="48" cy="48" r="48" fill="#ab9ff2"/><text x="48" y="62" text-anchor="middle" font-size="36">👻</text></svg>'),
      'Solflare':       'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96"><circle cx="48" cy="48" r="48" fill="#fc9965"/><text x="48" y="62" text-anchor="middle" font-size="36">☀️</text></svg>'),
      'Trust Wallet':   'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96"><circle cx="48" cy="48" r="48" fill="#3375bb"/><text x="48" y="62" text-anchor="middle" font-size="36">🛡️</text></svg>'),
      'Binance Wallet': 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96"><circle cx="48" cy="48" r="48" fill="#f0b90b"/><text x="48" y="62" text-anchor="middle" font-size="30" fill="#000">⬡</text></svg>'),
    };
    return icons[name] || icons['MetaMask'];
  }

  function _showError(msg) {
    const toast = document.createElement('div');
    toast.style.cssText = `position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#1a2236;border:1px solid rgba(255,77,109,0.4);color:#ff4d6d;padding:12px 20px;border-radius:10px;font-size:13px;z-index:9999;font-family:'Syne',sans-serif;box-shadow:0 8px 32px rgba(0,0,0,0.5);max-width:90vw;text-align:center;`;
    toast.textContent = '⚠ ' + msg;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
  }

  return {
    openPicker,
    closePicker,
    disconnect,
    setNetwork,
    getAddress,
    isConnected,
    getNetwork,
    getWalletName,
    onWalletChange,
  };
})();
