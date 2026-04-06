/**
 * ArbPulse — Network & DEX Configuration
 * 5 networks (BSC, ETH, Arbitrum, Base, Solana) × mainnet/testnet
 * Flash loan provider selection is automatic (backend picks cheapest with reserves).
 */

// ─── Global App State ────────────────────────────────────────────────────────
const AppState = {
  isTestnet: false,
  network:   'bsc',
};

// ─── Network Configurations ──────────────────────────────────────────────────
const NETWORK_CONFIG = {

  // ── BSC ──────────────────────────────────────────────────────────────────
  bsc: {
    mainnet: {
      name: 'BNB Chain', label: 'BNB Chain', dotClass: 'bsc',
      chainId: 56, chainIdHex: '0x38',
      nativeCurrency: { name: 'BNB', symbol: 'BNB', decimals: 18 },
      rpcUrls: ['https://bsc-dataseed1.binance.org/', 'https://rpc.ankr.com/bsc'],
      blockExplorerUrls: ['https://bscscan.com'],
      blockExplorerTx:   'https://bscscan.com/tx/',
      walletType: 'evm',
      baseTokens: [
        { symbol: 'WBNB', address: '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c' },
        { symbol: 'USDT', address: '0x55d398326f99059fF775485246999027B3197955' },
        { symbol: 'USDC', address: '0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d' },
        { symbol: 'BTCB', address: '0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c' },
        { symbol: 'BUSD', address: '0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56' },
        { symbol: 'ETH',  address: '0x2170Ed0880ac9A755fd29B2688956BD959F933F8' },
        { symbol: 'DAI',  address: '0x1AF3F329e8BE154074D8769D1FFa4eE058B1DBc3' },
        { symbol: 'CAKE', address: '0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82' },
      ],
      dexes: [
        'PancakeSwap V2','PancakeSwap V3','ApeSwap','BiSwap',
        'MDEX','BabySwap','Thena','KnightSwap','SushiSwap','Nomiswap',
      ],
    },
    testnet: {
      name: 'BSC Testnet', label: 'BSC Test', dotClass: 'bsc',
      chainId: 97, chainIdHex: '0x61',
      nativeCurrency: { name: 'tBNB', symbol: 'tBNB', decimals: 18 },
      rpcUrls: ['https://data-seed-prebsc-1-s1.binance.org:8545/'],
      blockExplorerUrls: ['https://testnet.bscscan.com'],
      blockExplorerTx:   'https://testnet.bscscan.com/tx/',
      walletType: 'evm',
      baseTokens: [
        { symbol: 'WBNB', address: '0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd' },
        { symbol: 'USDT', address: '0x337610d27c682E347C9cD60BD4b3b107C9d34dDd' },
        { symbol: 'USDC', address: '0x64544969ed7EBf5f083679233325356EbE738930' },
        { symbol: 'BUSD', address: '0xeD24FC36d5Ee211Ea25A80239Fb8C4Cfd80f12Ee' },
        { symbol: 'DAI',  address: '0xEC5dCb5Dbf4B114C9d0F65BcCAb49EC54F6A0867' },
        { symbol: 'BTCB', address: '0x6ce8dA28E2f864420840cF74474eFf5bD8C6feed' },
        { symbol: 'ETH',  address: '0x8BaBbB98678facC7342735486C851ABd7A0d17Cc' },
        { symbol: 'CAKE', address: '0xFa60D973F7642B748046464e165A65B7323b0DEE' },
      ],
      dexes: ['PancakeSwap V2 Testnet'],
    },
  },

  // ── Ethereum ──────────────────────────────────────────────────────────────
  eth: {
    mainnet: {
      name: 'Ethereum', label: 'Ethereum', dotClass: 'eth',
      chainId: 1, chainIdHex: '0x1',
      nativeCurrency: { name: 'Ether', symbol: 'ETH', decimals: 18 },
      rpcUrls: ['https://eth.llamarpc.com', 'https://rpc.ankr.com/eth'],
      blockExplorerUrls: ['https://etherscan.io'],
      blockExplorerTx:   'https://etherscan.io/tx/',
      walletType: 'evm',
      baseTokens: [
        { symbol: 'WETH',  address: '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2' },
        { symbol: 'USDT',  address: '0xdAC17F958D2ee523a2206206994597C13D831ec7' },
        { symbol: 'USDC',  address: '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48' },
        { symbol: 'DAI',   address: '0x6B175474E89094C44Da98b954EedeAC495271d0F' },
        { symbol: 'WBTC',  address: '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599' },
        { symbol: 'FRAX',  address: '0x853d955aCEf822Db058eb8505911ED77F175b99e' },
        { symbol: 'LUSD',  address: '0x5f98805A4E8be255a32880FDeC7F6728C6568bA0' },
        { symbol: 'LINK',  address: '0x514910771AF9Ca656af840dff83E8264EcF986CA' },
        { symbol: 'UNI',   address: '0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984' },
        { symbol: 'AAVE',  address: '0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9' },
      ],
      dexes: [
        'Uniswap V2','Uniswap V3','SushiSwap ETH','Shibaswap',
        'Fraxswap','PancakeSwap V3 ETH','Balancer V2',
      ],
    },
    testnet: {
      name: 'Sepolia', label: 'Sepolia', dotClass: 'eth',
      chainId: 11155111, chainIdHex: '0xaa36a7',
      nativeCurrency: { name: 'SepoliaETH', symbol: 'ETH', decimals: 18 },
      rpcUrls: ['https://rpc.sepolia.org', 'https://ethereum-sepolia.publicnode.com'],
      blockExplorerUrls: ['https://sepolia.etherscan.io'],
      blockExplorerTx:   'https://sepolia.etherscan.io/tx/',
      walletType: 'evm',
      baseTokens: [
        { symbol: 'WETH',  address: '0x7b79995e5f793A07Bc00c21d5351694B20Ca3f2d' },
        { symbol: 'USDC',  address: '0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238' },
        { symbol: 'DAI',   address: '0xFF34B3d4Aee8ddCd6F9AFFFB6Fe49bD371b8a357' },
        { symbol: 'LINK',  address: '0x779877A7B0D9E8603169DdbD7836e478b4624789' },
        { symbol: 'UNI',   address: '0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984' },
        { symbol: 'USDT',  address: '0xaA8E23Fb1079EA71e0a56F48a2aA51851D8433D0' },
        { symbol: 'WBTC',  address: '0x92f3B59a79bFf5dc60c0d59eA13a44D082B2bdFC' },
        { symbol: 'AAVE',  address: '0x88541670E55cC00bEEFD87eB59EDd1b7C511AC9a' },
        { symbol: 'FRAX',  address: '0x853d955aCEf822Db058eb8505911ED77F175b99e' },
        { symbol: 'LUSD',  address: '0x5f98805A4E8be255a32880FDeC7F6728C6568bA0' },
      ],
      dexes: ['Uniswap V2 Sepolia', 'Uniswap V3 Sepolia'],
    },
  },

  // ── Arbitrum ──────────────────────────────────────────────────────────────
  arb: {
    mainnet: {
      name: 'Arbitrum', label: 'Arbitrum', dotClass: 'arb',
      chainId: 42161, chainIdHex: '0xa4b1',
      nativeCurrency: { name: 'Ether', symbol: 'ETH', decimals: 18 },
      rpcUrls: ['https://arb1.arbitrum.io/rpc', 'https://rpc.ankr.com/arbitrum'],
      blockExplorerUrls: ['https://arbiscan.io'],
      blockExplorerTx:   'https://arbiscan.io/tx/',
      walletType: 'evm',
      baseTokens: [
        { symbol: 'WETH',  address: '0x82aF49447D8a07e3bd95BD0d56f35241523fBab1' },
        { symbol: 'USDT',  address: '0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9' },
        { symbol: 'USDC',  address: '0xaf88d065e77c8cC2239327C5EDb3A432268e5831' },
        { symbol: 'DAI',   address: '0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1' },
        { symbol: 'WBTC',  address: '0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f' },
        { symbol: 'ARB',   address: '0x912CE59144191C1204E64559FE8253a0e49E6548' },
        { symbol: 'FRAX',  address: '0x17FC002b466eEc40DaE837Fc4bE5c67993ddBd6F' },
        { symbol: 'GMX',   address: '0xfc5A1A6EB076a2C7aD06eD22C90d7E710E35ad0a' },
      ],
      dexes: [
        'Camelot V2','Uniswap V3 Arb','SushiSwap Arb',
        'Ramses','Trader Joe Arb','Zyberswap',
      ],
    },
    testnet: {
      name: 'Arb Sepolia', label: 'Arb Test', dotClass: 'arb',
      chainId: 421614, chainIdHex: '0x66eee',
      nativeCurrency: { name: 'Ether', symbol: 'ETH', decimals: 18 },
      rpcUrls: ['https://sepolia-rollup.arbitrum.io/rpc'],
      blockExplorerUrls: ['https://sepolia.arbiscan.io'],
      blockExplorerTx:   'https://sepolia.arbiscan.io/tx/',
      walletType: 'evm',
      baseTokens: [
        { symbol: 'WETH',  address: '0x980B62Da83eFf3D4576C647993b0c1D7faf17c73' },
        { symbol: 'USDC',  address: '0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d' },
        { symbol: 'ARB',   address: '0x912CE59144191C1204E64559FE8253a0e49E6548' },
        { symbol: 'DAI',   address: '0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1' },
        { symbol: 'USDT',  address: '0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9' },
        { symbol: 'WBTC',  address: '0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f' },
        { symbol: 'FRAX',  address: '0x17FC002b466eEc40DaE837Fc4bE5c67993ddBd6F' },
        { symbol: 'GMX',   address: '0xfc5A1A6EB076a2C7aD06eD22C90d7E710E35ad0a' },
      ],
      dexes: ['Uniswap V3 Arb Sepolia', 'Camelot V2 Testnet'],
    },
  },

  // ── Base ──────────────────────────────────────────────────────────────────
  base: {
    mainnet: {
      name: 'Base', label: 'Base', dotClass: 'base',
      chainId: 8453, chainIdHex: '0x2105',
      nativeCurrency: { name: 'Ether', symbol: 'ETH', decimals: 18 },
      rpcUrls: ['https://mainnet.base.org', 'https://rpc.ankr.com/base'],
      blockExplorerUrls: ['https://basescan.org'],
      blockExplorerTx:   'https://basescan.org/tx/',
      walletType: 'evm',
      baseTokens: [
        { symbol: 'WETH',  address: '0x4200000000000000000000000000000000000006' },
        { symbol: 'USDC',  address: '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913' },
        { symbol: 'DAI',   address: '0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb' },
        { symbol: 'cbETH', address: '0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22' },
        { symbol: 'AERO',  address: '0x940181a94A35A4569E4529A3CDfB74e38FD98631' },
        { symbol: 'USDbC', address: '0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA' },
        { symbol: 'DEGEN', address: '0x4ed4E862860beD51a9570b96d89aF5E1B0Efefed' },
        { symbol: 'BRETT', address: '0x532f27101965dd16442E59d40670FaF5eBB142E4' },
      ],
      dexes: [
        'Aerodrome','BaseSwap','Uniswap V3 Base',
        'SwapBased','AlienBase','RocketSwap','PancakeSwap V3 Base',
      ],
    },
    testnet: {
      name: 'Base Sepolia', label: 'Base Test', dotClass: 'base',
      chainId: 84532, chainIdHex: '0x14a34',
      nativeCurrency: { name: 'Ether', symbol: 'ETH', decimals: 18 },
      rpcUrls: ['https://sepolia.base.org'],
      blockExplorerUrls: ['https://sepolia.basescan.org'],
      blockExplorerTx:   'https://sepolia.basescan.org/tx/',
      walletType: 'evm',
      baseTokens: [
        { symbol: 'WETH',  address: '0x4200000000000000000000000000000000000006' },
        { symbol: 'USDC',  address: '0x036CbD53842c5426634e7929541eC2318f3dCF7e' },
        { symbol: 'DAI',   address: '0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb' },
        { symbol: 'cbETH', address: '0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22' },
        { symbol: 'AERO',  address: '0x940181a94A35A4569E4529A3CDfB74e38FD98631' },
        { symbol: 'USDbC', address: '0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA' },
        { symbol: 'DEGEN', address: '0x4ed4E862860beD51a9570b96d89aF5E1B0Efefed' },
        { symbol: 'BRETT', address: '0x532f27101965dd16442E59d40670FaF5eBB142E4' },
      ],
      dexes: ['Uniswap V3 Base Sepolia', 'Aerodrome Sepolia'],
    },
  },

  // ── Solana ────────────────────────────────────────────────────────────────
  solana: {
    mainnet: {
      name: 'Solana', label: 'Solana', dotClass: 'sol',
      chainId: null,
      nativeCurrency: { name: 'SOL', symbol: 'SOL', decimals: 9 },
      rpcUrls: ['https://api.mainnet-beta.solana.com'],
      blockExplorerUrls: ['https://solscan.io'],
      blockExplorerTx:   'https://solscan.io/tx/',
      walletType: 'solana',
      baseTokens: [
        { symbol: 'WSOL',    address: 'So11111111111111111111111111111111111111112' },
        { symbol: 'USDC',    address: 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v' },
        { symbol: 'USDT',    address: 'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB' },
        { symbol: 'MSOL',    address: 'mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So' },
        { symbol: 'BONK',    address: 'DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263' },
        { symbol: 'JTO',     address: 'jtojtomepa8bJkZSqEXSJm5Z4e6PdBXuBvC5jNYWqDi' },
        { symbol: 'JITOSOL', address: 'J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn' },
        { symbol: 'BSOL',    address: 'bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1' },
      ],
      dexes: [
        'Raydium V4','Raydium CLMM','Orca Whirlpool','Orca V2',
        'Meteora DLMM','Lifinity V2','GooseFX','Saber',
      ],
    },
    testnet: {
      name: 'Sol Devnet', label: 'Sol Dev', dotClass: 'sol',
      chainId: null,
      nativeCurrency: { name: 'SOL', symbol: 'SOL', decimals: 9 },
      rpcUrls: ['https://api.devnet.solana.com'],
      blockExplorerUrls: ['https://solscan.io/?cluster=devnet'],
      blockExplorerTx:   'https://solscan.io/tx/',
      walletType: 'solana',
      baseTokens: [
        { symbol: 'WSOL',    address: 'So11111111111111111111111111111111111111112' },
        { symbol: 'USDC',    address: 'Gh9ZwEmdLJ8DscKNTkTqPbNwLNNBjuSzaG9Vp2KGtKJr' },
        { symbol: 'USDT',    address: 'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB' },
        { symbol: 'MSOL',    address: 'mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So' },
        { symbol: 'BONK',    address: 'DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263' },
        { symbol: 'JTO',     address: 'jtojtomepa8bJkZSqEXSJm5Z4e6PdBXuBvC5jNYWqDi' },
        { symbol: 'JITOSOL', address: 'J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn' },
        { symbol: 'BSOL',    address: 'bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1' },
      ],
      dexes: ['Raydium Devnet', 'Orca Devnet'],
    },
  },
};

/** Return config for the active network + mainnet/testnet mode. */
function getNetCfg(network, isTestnet) {
  return NETWORK_CONFIG[network]?.[isTestnet ? 'testnet' : 'mainnet']
      || NETWORK_CONFIG.bsc.mainnet;
}

/** Shortcut using AppState. */
function activeCfg() {
  return getNetCfg(AppState.network, AppState.isTestnet);
}

// ─── Token Colors ─────────────────────────────────────────────────────────────
const TOKEN_COLORS = {
  // BSC
  WBNB: '#f0b90b', BTCB: '#f7931a', CAKE: '#ff7e00', BUSD: '#f0b90b',
  BSW:  '#1fc7d4',
  // Stablecoins
  USDT: '#26a17b', USDC: '#2775ca', DAI: '#f9a606', FRAX: '#000000',
  LUSD: '#1542cd', MIM:  '#9695a4', GHO: '#6749d6', crvUSD: '#b5cbff',
  USDbC:'#2775ca', HAY:  '#f8d900',
  // ETH & derivatives
  WETH: '#627eea', ETH: '#627eea', stETH: '#00a3ff', wstETH: '#00a3ff',
  cbETH:'#0052ff', rETH: '#ff8c00', frxETH:'#b5c0ce', ETHX: '#5b4fcf',
  // L1/infrastructure
  WBTC: '#f7931a', LINK: '#2a5ada', UNI: '#ff007a', AAVE: '#b6509e',
  MKR:  '#1aab9b', CRV:  '#d9b27c', CVX:  '#3a3a3a', SNX:  '#00d1ff',
  YFI:  '#0066fa', BAL:  '#1e1e1e', SUSHI:'#fa52a0', COMP: '#00d395',
  GRT:  '#6747ed', LDO:  '#77ccdd', RPL:  '#e8711e', FXS:  '#000000',
  '1INCH':'#94a6c3', PERP:'#25d9bf', DYDX:'#6966ff',
  // Arbitrum
  ARB:  '#12aaff', GMX:  '#03d1cf',
  // Base
  AERO: '#0052ff', DEGEN:'#a855f7', BRETT:'#ff6a00',
  // Solana
  WSOL: '#9945ff', MSOL: '#e84142', BONK: '#ffa500', JTO: '#89f9a5',
  JITOSOL:'#27b580', BSOL:'#00bcd4', WIF: '#9945ff', JUP: '#c8b73a',
  // Meme
  SHIB: '#ff5722', PEPE: '#3cb371', FLOKI:'#f5a623', APE: '#054bde',
  // Gaming
  AXS:  '#0055d5', SAND: '#00adef', MANA: '#ff2d55', ENJ: '#7866d5',
  GALA: '#1d1d1b', ILV:  '#4fff9f', IMX:  '#0d0d0d', BLUR:'#f97316',
};

function getTokenColor(symbol) {
  return TOKEN_COLORS[symbol] || '#64748b';
}

// ─── Shared formatters ────────────────────────────────────────────────────────
function formatAddress(addr) {
  if (!addr) return '';
  return addr.slice(0, 6) + '...' + addr.slice(-4);
}

function formatUsd(val, decimals = 0) {
  if (val === null || val === undefined || isNaN(val)) return '—';
  const abs = Math.abs(val), sign = val < 0 ? '-' : '';
  if (abs >= 1_000_000) return sign + '$' + (abs / 1_000_000).toFixed(2) + 'M';
  if (abs >= 1_000)     return sign + '$' + abs.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return sign + '$' + abs.toFixed(2);
}

function formatTokenAmount(val, symbol, decimals = 4) {
  if (val === null || val === undefined || isNaN(val)) return '—';
  return parseFloat(val).toFixed(decimals) + ' ' + (symbol || '');
}

function formatPercent(val, decimals = 3) {
  if (val === null || val === undefined || isNaN(val)) return '—';
  const sign = val >= 0 ? '+' : '';
  return sign + parseFloat(val).toFixed(decimals) + '%';
}

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString();
}

function formatDate(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString();
}

function shortTxHash(hash) {
  if (!hash) return '';
  return hash.slice(0, 8) + '...' + hash.slice(-6);
}

// Network gas label helper
function networkGasLabel(network) {
  return { bsc:'BSC', eth:'Ethereum', arb:'Arbitrum', base:'Base', solana:'Solana' }[network] || network;
}
