/**
 * ArbPulse — Network & DEX Configuration
 * All BSC and Solana network constants used across the frontend.
 */

const NETWORK_CONFIG = {
  bsc: {
    name: 'BNB Chain',
    chainId: 56,
    chainIdHex: '0x38',
    nativeCurrency: { name: 'BNB', symbol: 'BNB', decimals: 18 },
    rpcUrls: [
      'https://bsc-dataseed1.binance.org/',
      'https://bsc-dataseed2.binance.org/',
      'https://bsc-dataseed3.binance.org/',
    ],
    blockExplorerUrls: ['https://bscscan.com'],
    flashProviders: [
      { label: 'Aave V3 (0.05%)',         value: 'Aave V3',              fee: 0.05 },
      { label: 'PancakeSwap V3 (0.01%)',  value: 'PancakeSwap V3 Flash', fee: 0.01 },
      { label: 'DODO Flash (0%)',         value: 'DODO Flash',           fee: 0.00 },
    ],
    baseTokens: [
      { symbol: 'USDT',  address: '0x55d398326f99059fF775485246999027B3197955' },
      { symbol: 'WBNB',  address: '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c' },
      { symbol: 'BTCB',  address: '0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c' },
      { symbol: 'USDC',  address: '0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d' },
    ],
    dexes: [
      'PancakeSwap V2', 'PancakeSwap V3', 'ApeSwap', 'BiSwap',
      'MDEX', 'BabySwap', 'Thena', 'KnightSwap', 'SushiSwap', 'Nomiswap',
    ],
    blockExplorerTx: 'https://bscscan.com/tx/',
    walletType: 'evm',
  },
  solana: {
    name: 'Solana',
    chainId: null,
    nativeCurrency: { name: 'SOL', symbol: 'SOL', decimals: 9 },
    flashProviders: [
      { label: 'MarginFi (0%)',    value: 'MarginFi', fee: 0.00 },
      { label: 'Kamino (0.09%)',   value: 'Kamino',   fee: 0.09 },
      { label: 'Solend (0.30%)',   value: 'Solend',   fee: 0.30 },
    ],
    baseTokens: [
      { symbol: 'USDC',  address: 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v' },
      { symbol: 'WSOL',  address: 'So11111111111111111111111111111111111111112' },
      { symbol: 'MSOL',  address: 'mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So' },
      { symbol: 'USDT',  address: 'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB' },
    ],
    dexes: [
      'Raydium V4', 'Raydium CLMM', 'Orca Whirlpool', 'Orca V2',
      'Meteora DLMM', 'Lifinity V2', 'GooseFX', 'Saber',
    ],
    blockExplorerTx: 'https://solscan.io/tx/',
    walletType: 'solana',
  },
};

const TOKEN_COLORS = {
  USDT: '#26a17b', WBNB: '#f0b90b', BTCB: '#f7931a', USDC: '#2775ca',
  WSOL: '#9945ff', MSOL: '#e84142', ETH:  '#627eea', BNB:  '#f0b90b',
  CAKE: '#ff7e00', BSW:  '#1fc7d4', BUSD: '#f0b90b', DAI:  '#f9a606',
};

function getTokenColor(symbol) {
  return TOKEN_COLORS[symbol] || '#64748b';
}

function formatAddress(addr) {
  if (!addr) return '';
  return addr.slice(0, 6) + '...' + addr.slice(-4);
}

function formatUsd(val, decimals = 0) {
  if (val === null || val === undefined || isNaN(val)) return '—';
  const abs = Math.abs(val);
  const sign = val < 0 ? '-' : '';
  if (abs >= 1000000) return sign + '$' + (abs / 1000000).toFixed(2) + 'M';
  if (abs >= 1000)    return sign + '$' + abs.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return sign + '$' + abs.toFixed(2);
}

function formatTokenAmount(val, symbol, decimals = 4) {
  if (val === null || val === undefined || isNaN(val)) return '—';
  return parseFloat(val).toFixed(decimals) + ' ' + symbol;
}

function formatPercent(val, decimals = 3) {
  if (val === null || val === undefined || isNaN(val)) return '—';
  const sign = val >= 0 ? '+' : '';
  return sign + parseFloat(val).toFixed(decimals) + '%';
}

function formatTime(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString();
}

function formatDate(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString();
}

function shortTxHash(hash) {
  if (!hash) return '';
  return hash.slice(0, 8) + '...' + hash.slice(-6);
}
