/**
 * ArbPulse — Wallet Manager
 * Per-network wallet state: 5 networks, mainnet/testnet aware chain switching.
 */

const WalletManager = (() => {
  const _state = {
    bsc:    { connected: false, address: '', walletName: '', provider: null },
    eth:    { connected: false, address: '', walletName: '', provider: null },
    arb:    { connected: false, address: '', walletName: '', provider: null },
    base:   { connected: false, address: '', walletName: '', provider: null },
    solana: { connected: false, address: '', walletName: '', provider: null },
  };

  let _activeNetwork     = 'bsc';
  let _onChangeCallbacks = [];

  const WALLET_OPTIONS = {
    evm: [
      { id: 'metamask',      name: 'MetaMask',       desc: 'Most popular EVM wallet',           icon: '🦊',  detected: () => !!window.ethereum?.isMetaMask },
      { id: 'trust',         name: 'Trust Wallet',   desc: 'Mobile-first multichain wallet',    icon: '🛡️', detected: () => !!window.ethereum?.isTrust },
      { id: 'binance',       name: 'Binance Wallet', desc: 'Official Binance Web3 wallet',      icon: '⬡',   detected: () => !!window.BinanceChain },
      { id: 'coinbase',      name: 'Coinbase Wallet',desc: 'Easy onboarding Web3 wallet',       icon: '🔵',  detected: () => !!window.coinbaseWalletExtension },
      { id: 'walletconnect', name: 'WalletConnect',  desc: 'Connect any mobile wallet via QR',  icon: '🔗',  detected: () => false },
    ],
    solana: [
      { id: 'phantom',   name: 'Phantom',       desc: 'Most popular Solana wallet',   icon: '👻', detected: () => !!window.solana?.isPhantom },
      { id: 'solflare',  name: 'Solflare',       desc: 'Feature-rich Solana wallet',   icon: '☀️', detected: () => !!window.solflare },
      { id: 'backpack',  name: 'Backpack',        desc: 'Multi-chain xNFT wallet',      icon: '🎒', detected: () => !!window.xnft },
      { id: 'coinbase',  name: 'Coinbase Wallet', desc: 'Easy onboarding Web3 wallet',  icon: '🔵', detected: () => !!window.coinbaseWalletExtension },
    ],
  };

  // Which wallet type each network uses
  function _walletType(network) {
    return network === 'solana' ? 'solana' : 'evm';
  }

  function onWalletChange(cb) { _onChangeCallbacks.push(cb); }
  function getAddress()       { return _state[_activeNetwork].address; }
  function isConnected()      { return _state[_activeNetwork].connected; }
  function getNetwork()       { return _activeNetwork; }
  function getWalletName()    { return _state[_activeNetwork].walletName; }

  function setNetwork(network) {
    _activeNetwork = network;
    _updateUI();
    _emit();
  }

  // ─── Open wallet picker ────────────────────────────────────────────────
  function openPicker() {
    const modal      = document.getElementById('wallet-picker-modal');
    const titleEl    = document.getElementById('wallet-picker-title');
    const netLabelEl = document.getElementById('wallet-picker-network-label');
    const listEl     = document.getElementById('wallet-picker-list');
    if (!modal) return;

    const cfg    = activeCfg();
    const type   = _walletType(_activeNetwork);
    const wallets= WALLET_OPTIONS[type];

    titleEl.textContent    = `Connect to ${cfg.name}`;
    netLabelEl.textContent = type === 'evm' ? 'EVM Wallets' : 'Solana Wallets';

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

    listEl.querySelectorAll('.wallet-option').forEach(el => {
      el.addEventListener('click', () => {
        closePicker();
        _connectWallet(el.dataset.walletId, el.dataset.walletName);
      });
    });

    modal.classList.remove('hidden');
    modal.onclick = (e) => { if (e.target === modal) closePicker(); };
  }

  function closePicker() {
    document.getElementById('wallet-picker-modal')?.classList.add('hidden');
  }

  // ─── Connect ──────────────────────────────────────────────────────────
  async function _connectWallet(walletId, walletName) {
    if (_walletType(_activeNetwork) === 'solana') {
      await _connectSolana(walletId, walletName);
    } else {
      await _connectEVM(walletId, walletName);
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

      // Switch to the correct chain based on network + testnet toggle
      const cfg = activeCfg();
      try {
        await provider.request({
          method: 'wallet_switchEthereumChain',
          params: [{ chainId: cfg.chainIdHex }],
        });
      } catch (switchErr) {
        if (switchErr.code === 4902) {
          await provider.request({
            method: 'wallet_addEthereumChain',
            params: [{
              chainId:           cfg.chainIdHex,
              chainName:         cfg.name,
              nativeCurrency:    cfg.nativeCurrency,
              rpcUrls:           cfg.rpcUrls,
              blockExplorerUrls: cfg.blockExplorerUrls,
            }],
          });
        }
      }

      _state[_activeNetwork].connected  = true;
      _state[_activeNetwork].address    = accounts[0];
      _state[_activeNetwork].walletName = walletName;
      _state[_activeNetwork].provider   = provider;

      provider.on('accountsChanged', (accs) => {
        _state[_activeNetwork].connected = accs.length > 0;
        _state[_activeNetwork].address   = accs[0] || '';
        _updateUI(); _emit();
      });
      provider.on('chainChanged', () => window.location.reload());

      _updateUI(); _emit();
      AppLog.info(`${walletName} connected on ${cfg.name}: ${_fmtAddr(accounts[0])}`);
    } catch (e) {
      AppLog.error(`${walletName} connection failed: ${e.message}`);
      _showError(e.message);
    }
  }

  async function _connectSolana(walletId, walletName) {
    const solWallet =
      walletId === 'phantom'  ? (window.phantom?.solana || window.solana)
    : walletId === 'solflare' ? window.solflare
    : walletId === 'backpack' ? window.xnft?.solana
    : null;

    if (!solWallet) { _showError(`${walletName} not detected. Please install it and refresh.`); return; }
    try {
      const resp    = await solWallet.connect();
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
    const net  = _activeNetwork;
    const name = _state[net].walletName;
    if (net === 'solana' && _state.solana.provider) {
      try { await _state.solana.provider.disconnect(); } catch {}
    }
    _state[net] = { connected: false, address: '', walletName: '', provider: null };
    _updateUI(); _emit();
    const cfg = activeCfg();
    AppLog.info(`${name} disconnected from ${cfg.name}.`);
  }

  // ─── UI update ────────────────────────────────────────────────────────
  function _updateUI() {
    const ws = _state[_activeNetwork];
    const connectBtn   = document.getElementById('connect-wallet-btn');
    const connectedDiv = document.getElementById('wallet-connected');
    const addrSpan     = document.getElementById('wallet-address');
    const iconImg      = document.getElementById('wallet-icon');

    if (ws.connected) {
      connectBtn?.classList.add('hidden');
      connectedDiv?.classList.remove('hidden');
      if (addrSpan) addrSpan.textContent = _fmtAddr(ws.address);
      if (iconImg)  iconImg.src = _walletIconSrc(ws.walletName);
    } else {
      connectBtn?.classList.remove('hidden');
      connectedDiv?.classList.add('hidden');
    }

    // Green dot on each network pill
    ['bsc','eth','arb','base','solana'].forEach(net => {
      const pill = document.getElementById(`net-pill-${net}`);
      const dot  = document.getElementById(`net-ci-${net}`);
      if (pill) pill.classList.toggle('wallet-connected-on', _state[net].connected);
      if (dot)  dot.style.display = _state[net].connected ? 'block' : 'none';
    });
  }

  function _emit() {
    _onChangeCallbacks.forEach(cb => cb({
      address:   _state[_activeNetwork].address,
      network:   _activeNetwork,
      connected: _state[_activeNetwork].connected,
    }));
  }

  function _fmtAddr(addr) {
    if (!addr) return '';
    return addr.length > 20 ? addr.slice(0,6) + '...' + addr.slice(-4) : addr;
  }

  function _walletIconSrc(name) {
    const icons = {
      'MetaMask':       _svgIcon('#e8831d', '🦊'),
      'Phantom':        _svgIcon('#ab9ff2', '👻'),
      'Solflare':       _svgIcon('#fc9965', '☀️'),
      'Trust Wallet':   _svgIcon('#3375bb', '🛡️'),
      'Binance Wallet': _svgIcon('#f0b90b', '⬡'),
      'Coinbase Wallet':_svgIcon('#0052ff', '🔵'),
      'Backpack':       _svgIcon('#e33e3f', '🎒'),
    };
    return icons[name] || icons['MetaMask'];
  }

  function _svgIcon(bg, emoji) {
    return 'data:image/svg+xml,' + encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96"><circle cx="48" cy="48" r="48" fill="${bg}"/><text x="48" y="62" text-anchor="middle" font-size="36">${emoji}</text></svg>`
    );
  }

  function _showError(msg) {
    const toast = document.createElement('div');
    toast.style.cssText = `position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#1a2236;border:1px solid rgba(255,77,109,0.4);color:#ff4d6d;padding:12px 20px;border-radius:10px;font-size:13px;z-index:9999;font-family:'Syne',sans-serif;box-shadow:0 8px 32px rgba(0,0,0,0.5);max-width:90vw;text-align:center;`;
    toast.textContent = '⚠ ' + msg;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
  }

  return { openPicker, closePicker, disconnect, setNetwork, getAddress, isConnected, getNetwork, getWalletName, onWalletChange };
})();
