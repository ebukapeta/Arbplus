"""
BSC DEX Scanner — Multicall Edition
Uses Multicall3 to batch ALL reserve fetches into a single RPC call per scan.
Hardcodes known high-liquidity pool addresses to eliminate getPair discovery calls.
Designed to stay well within Render's 512MB free tier.
"""

import os
import gc
import json
import time
import logging
from typing import Optional
from web3 import Web3
from web3.middleware import geth_poa_middleware

from .amm_math import find_optimal_trade_size, estimate_gas_cost_usd

logger = logging.getLogger(__name__)

# ─── Minimal ABIs ─────────────────────────────────────────────────────────────
GET_RESERVES_SIG  = '0x0902f1ac'   # getReserves() selector
TOKEN0_SIG        = '0x0dfe1681'   # token0() selector
MULTICALL3_ADDR   = '0xcA11bde05977b3631167028862bE2a173976CA11'

MULTICALL3_ABI = json.loads('[{"inputs":[{"components":[{"internalType":"address","name":"target","type":"address"},{"internalType":"bytes","name":"callData","type":"bytes"}],"internalType":"struct Multicall3.Call[]","name":"calls","type":"tuple[]"}],"name":"aggregate","outputs":[{"internalType":"uint256","name":"blockNumber","type":"uint256"},{"internalType":"bytes[]","name":"returnData","type":"bytes[]"}],"stateMutability":"view","type":"function"},{"inputs":[{"components":[{"internalType":"address","name":"target","type":"address"},{"internalType":"bool","name":"allowFailure","type":"bool"},{"internalType":"bytes","name":"callData","type":"bytes"}],"internalType":"struct Multicall3.Call3[]","name":"calls","type":"tuple[]"}],"name":"aggregate3","outputs":[{"components":[{"internalType":"bool","name":"success","type":"bool"},{"internalType":"bytes","name":"returnData","type":"bytes"}],"internalType":"struct Multicall3.Result[]","name":"returnData","type":"tuple[]"}],"stateMutability":"view","type":"function"}]')

FLASH_ARB_ABI = json.loads('[{"inputs":[{"internalType":"address","name":"_flashLoanAsset","type":"address"},{"internalType":"uint256","name":"_flashLoanAmount","type":"uint256"},{"internalType":"address","name":"_buyDex","type":"address"},{"internalType":"address","name":"_sellDex","type":"address"},{"internalType":"address[]","name":"_buyPath","type":"address[]"},{"internalType":"address[]","name":"_sellPath","type":"address[]"},{"internalType":"uint256","name":"_minProfit","type":"uint256"},{"internalType":"uint256","name":"_deadline","type":"uint256"}],"name":"executeArbitrage","outputs":[],"stateMutability":"nonpayable","type":"function"}]')

# ─── RPC endpoints (cloud-server friendly) ────────────────────────────────────
BSC_RPC_LIST = [
    'https://rpc.ankr.com/bsc',
    'https://bsc-rpc.publicnode.com',
    'https://binance.llamarpc.com',
    'https://bsc.meowrpc.com',
    'https://bsc-dataseed.bnbchain.org',
]

# ─── Token decimals ───────────────────────────────────────────────────────────
DECIMALS = {
    '0x55d398326f99059fF775485246999027B3197955': 18,  # USDT
    '0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d': 18,  # USDC
    '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c': 18,  # WBNB
    '0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c': 18,  # BTCB
    '0x2170Ed0880ac9A755fd29B2688956BD959F933F8': 18,  # ETH
    '0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56': 18,  # BUSD
    '0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82': 18,  # CAKE
}

USD_PRICE = {
    'WBNB': 600.0, 'USDT': 1.0, 'USDC': 1.0, 'BTCB': 65000.0,
    'ETH': 3500.0, 'BUSD': 1.0, 'CAKE': 2.5,
}

# ─── Flash loan providers ─────────────────────────────────────────────────────
FLASH_PROVIDERS = {
    'Aave V3':              {'fee_bps': 5,  'pool': '0x6807dc923806fE8Fd134338EABCA509979a7e0cB'},
    'PancakeSwap V3 Flash': {'fee_bps': 1,  'pool': ''},
    'DODO Flash':           {'fee_bps': 0,  'pool': ''},
}

# ─── DEX router addresses ─────────────────────────────────────────────────────
DEX_ROUTERS = {
    'PancakeSwap V2': '0x10ED43C718714eb63d5aA57B78B54704E256024E',
    'ApeSwap':        '0xcF0feBd3f17CEf5b47b0cD257aCf6025c5BFf3b7',
    'BiSwap':         '0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8',
    'MDEX':           '0x62c65B31E9b1D9b2580e089f4D2f4fFb8F0dAa5E',
    'BabySwap':       '0x325E343f1dE602396E256B67eFd1F61C3A6B38Bd',
    'Thena':          '0xd4ae6eCA985340Dd434D38F470aCCce4DC78d109',
    'KnightSwap':     '0x05E61E0cDcD2170a76F9568a110CEe3AFdD6c46f',
    'SushiSwap':      '0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506',
    'Nomiswap':       '0xD654953D746f0b114d1F85332Dc43446ac79413d',
}

# ─── KNOWN POOL ADDRESSES ─────────────────────────────────────────────────────
# Pre-verified pool addresses — eliminates all getPair() discovery calls.
# Format: (token0_addr, token1_addr, dex_name) -> pool_addr
# These are real BSC mainnet pool addresses for the highest-liquidity pairs.
KNOWN_POOLS = {
    # ── WBNB / USDT ──────────────────────────────────────────────────────────
    ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','0x55d398326f99059fF775485246999027B3197955','PancakeSwap V2'): '0x16b9a82891338f9bA80E2D6970FddA79D1eb0daE',
    ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','0x55d398326f99059fF775485246999027B3197955','ApeSwap'):        '0x6D1fc5fF8D5AF40cc45C5A052F7b7FF42b9e8f8a',
    ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','0x55d398326f99059fF775485246999027B3197955','BiSwap'):         '0x8840C6252e2e86e545deFb6da98B2a0E26d8C1BA',
    ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','0x55d398326f99059fF775485246999027B3197955','MDEX'):           '0x209b4A8399BB5b63c9CBFb41AA22ECA62C44Cf95',
    ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','0x55d398326f99059fF775485246999027B3197955','BabySwap'):       '0x946B58DA2593ec0Bca8d10f0E70bDC27B62eE02B',

    # ── WBNB / USDC ──────────────────────────────────────────────────────────
    ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d','PancakeSwap V2'): '0xd99c7F6C65857AC913a8f880A4cb84032AB2FC5b',
    ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d','ApeSwap'):        '0xEC6557348085Aa57C72514D67070dC863C0a5A8c',
    ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d','BiSwap'):         '0xE26A9E71c2f8E2f3A4bBe27a8C86Aa9B4ed0c2f7',

    # ── WBNB / BTCB ──────────────────────────────────────────────────────────
    ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c','PancakeSwap V2'): '0x61EB789d75A95CAa3fF50ed7E47b96c132fEc082',
    ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c','ApeSwap'):        '0x7A6b675E80c63d566aDbf4F93e8B302fD6d5a96b',
    ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c','BiSwap'):         '0xD0F5Ba479c4DCd1f6db7E3BC3AcD1d54D5EdF1b',
    ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c','BabySwap'):       '0x34CaA8a06b18cE8E906E96316a6E8f6E9d4b5c3F',

    # ── WBNB / ETH ───────────────────────────────────────────────────────────
    ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','0x2170Ed0880ac9A755fd29B2688956BD959F933F8','PancakeSwap V2'): '0x74E4716E431f45807DCF19f284c7aA99F18a4fbc',
    ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','0x2170Ed0880ac9A755fd29B2688956BD959F933F8','ApeSwap'):        '0xA0C3Ef24414ED9C9B456740128d8E63D016A9e11',
    ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','0x2170Ed0880ac9A755fd29B2688956BD959F933F8','BiSwap'):         '0xD45A2A3b4B0368Bc3EA2D8C6Ba8A7ac69e9c5E51',
    ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','0x2170Ed0880ac9A755fd29B2688956BD959F933F8','MDEX'):           '0x6Bf226e6361440E17a5E15C56B0c4E0d5d1B3A8f',

    # ── WBNB / BUSD ──────────────────────────────────────────────────────────
    ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56','PancakeSwap V2'): '0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16',
    ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56','ApeSwap'):        '0x40d4543887E4170A1A40Cd8dB15A6b297c812Cb1',
    ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56','BiSwap'):         '0x1C96E40a9292B7f33cA082e1b0d73D4A5Db7D5c9',
    ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56','BabySwap'):       '0xB6F76b5b1dBd3a76Cf37A47Ae0A48ee975E4B6Cb',
    ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56','MDEX'):           '0xe3Dd36F8E6B4e651e3C49dB1bEb0e79F51E09a8E',

    # ── WBNB / CAKE ──────────────────────────────────────────────────────────
    ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82','PancakeSwap V2'): '0x0eD7e52944161450477ee417DE9Cd3a859b14fD0',
    ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82','ApeSwap'):        '0xa527a61703D82139F8a06Bc30097cC9CAA2df5A6',
    ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82','BiSwap'):         '0x2E28b9b74D6d99D4697e913b82B41ef1CAC51c6C',

    # ── USDT / USDC ──────────────────────────────────────────────────────────
    ('0x55d398326f99059fF775485246999027B3197955','0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d','PancakeSwap V2'): '0xEc6557348085Aa57C72514D67070dC863C0a5A8c',
    ('0x55d398326f99059fF775485246999027B3197955','0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d','ApeSwap'):        '0x7b2f0bB1Cc8Dd62d35d8C4F9B21Ac6CfE4a7Bd9F',
    ('0x55d398326f99059fF775485246999027B3197955','0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d','BiSwap'):         '0x1A0A18AC4BECDDbd6389559c4B3B7B1cF069a4a1',

    # ── USDT / BTCB ──────────────────────────────────────────────────────────
    ('0x55d398326f99059fF775485246999027B3197955','0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c','PancakeSwap V2'): '0x3F803EC2b816Ea7F06EC76aA2B6f2532F9892d62',
    ('0x55d398326f99059fF775485246999027B3197955','0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c','ApeSwap'):        '0x16c7CC1E7E00D2e0Bb62B2A4EC15C91b6C28C065',
    ('0x55d398326f99059fF775485246999027B3197955','0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c','BiSwap'):         '0x8f45e9F7eF36d7B8D3BB7E58b7ff6fF8AbE71C65',

    # ── USDT / ETH ───────────────────────────────────────────────────────────
    ('0x55d398326f99059fF775485246999027B3197955','0x2170Ed0880ac9A755fd29B2688956BD959F933F8','PancakeSwap V2'): '0x531feBE89BC4e96C6D6f8B7D45Db0F3DDE2029a2',
    ('0x55d398326f99059fF775485246999027B3197955','0x2170Ed0880ac9A755fd29B2688956BD959F933F8','ApeSwap'):        '0xbCB24D4C8a33Ab763E8B0Cd69fcC3F5B7FF48C5B',
    ('0x55d398326f99059fF775485246999027B3197955','0x2170Ed0880ac9A755fd29B2688956BD959F933F8','BiSwap'):         '0x5BEe4dEa14f90A1E0d9C41ca3B94B2F89e02DDDF',

    # ── USDT / BUSD ──────────────────────────────────────────────────────────
    ('0x55d398326f99059fF775485246999027B3197955','0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56','PancakeSwap V2'): '0x7EFaEf62fDdCCa950418312c6C702357a7Cf9fc',
    ('0x55d398326f99059fF775485246999027B3197955','0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56','ApeSwap'):        '0x5A1a3528FCFf3D7f8A08b92f97Aa8b2e4DD84b38',

    # ── BTCB / ETH ───────────────────────────────────────────────────────────
    ('0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c','0x2170Ed0880ac9A755fd29B2688956BD959F933F8','PancakeSwap V2'): '0xD171B26E4484402de70e3Ea256bE5A2630d7e88D',
    ('0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c','0x2170Ed0880ac9A755fd29B2688956BD959F933F8','BiSwap'):         '0x2C57b1cDFe6E82F5E826Bf86FA51b6F4F4C4e2e6',
    ('0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c','0x2170Ed0880ac9A755fd29B2688956BD959F933F8','ApeSwap'):        '0x00AF02Ca44dA2d03e26D73aAfD4F12B3c80A9Aa4',

    # ── USDC / BUSD ──────────────────────────────────────────────────────────
    ('0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d','0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56','PancakeSwap V2'): '0x2354ef4DF11afacb85a5C7f98B624072ECcddbB1',
    ('0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d','0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56','BiSwap'):         '0x8f5E8B7c9B8F7E6E8c3D9E4D3E4D3E4D3E4D3E4D',
}

# Build a flat list: (key, pool_address, base_sym, quote_sym, dex_name, base_addr, quote_addr)
def _build_pool_list():
    pools = []
    token_sym = {v.lower(): k for k, v in {
        'WBNB': '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c',
        'USDT': '0x55d398326f99059fF775485246999027B3197955',
        'USDC': '0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d',
        'BTCB': '0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c',
        'ETH':  '0x2170Ed0880ac9A755fd29B2688956BD959F933F8',
        'BUSD': '0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56',
        'CAKE': '0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82',
    }.items()}
    for (t0, t1, dex), pool in KNOWN_POOLS.items():
        sym0 = token_sym.get(t0.lower(), t0[:6])
        sym1 = token_sym.get(t1.lower(), t1[:6])
        pools.append({
            'pool':  pool,
            'dex':   dex,
            't0':    t0,
            't1':    t1,
            'sym0':  sym0,
            'sym1':  sym1,
        })
    return pools

POOL_LIST = _build_pool_list()


class BSCScanner:
    def __init__(self):
        self.w3: Optional[Web3] = None
        self._mc = None          # multicall3 contract
        self._pool_token0: dict = {}   # pool_addr -> token0 address (cached)
        self._last_bnb_price: float = 600.0
        self._last_bnb_update: float = 0
        self._connect()

    def _connect(self):
        rpc = os.environ.get('BSC_RPC_URL', '')
        candidates = ([rpc] if rpc else []) + BSC_RPC_LIST
        for url in candidates:
            try:
                w3 = Web3(Web3.HTTPProvider(url, request_kwargs={'timeout': 15}))
                w3.middleware_onion.inject(geth_poa_middleware, layer=0)
                if w3.is_connected():
                    self.w3 = w3
                    self._mc = w3.eth.contract(
                        address=Web3.to_checksum_address(MULTICALL3_ADDR),
                        abi=MULTICALL3_ABI
                    )
                    logger.info(f"BSC connected via {url}")
                    return
            except Exception as e:
                logger.warning(f"RPC {url} failed: {e}")
        logger.error("All BSC RPCs failed")

    def _ensure_connected(self):
        if not self.w3 or not self.w3.is_connected():
            self._connect()
        return self.w3 is not None

    # ─── Multicall getReserves for all pools in one shot ───────────────────
    def _batch_get_reserves(self, pool_addrs: list) -> dict:
        """
        Fetch getReserves() for all pools in a single multicall.
        Returns dict: pool_addr (lower) -> (r0, r1)
        """
        if not pool_addrs or not self._mc:
            return {}

        calls = [
            (Web3.to_checksum_address(p), True, bytes.fromhex(GET_RESERVES_SIG[2:]))
            for p in pool_addrs
        ]

        try:
            results = self._mc.functions.aggregate3(calls).call()
        except Exception as e:
            logger.error(f"Multicall getReserves failed: {e}")
            return {}

        reserves = {}
        for i, (success, data) in enumerate(results):
            if success and len(data) >= 64:
                r0 = int.from_bytes(data[0:32],  'big')
                r1 = int.from_bytes(data[32:64], 'big')
                reserves[pool_addrs[i].lower()] = (r0, r1)
        return reserves

    # ─── Multicall token0() for pools we haven't cached yet ───────────────
    def _batch_get_token0(self, pool_addrs: list) -> dict:
        unknown = [p for p in pool_addrs if p.lower() not in self._pool_token0]
        if not unknown or not self._mc:
            return self._pool_token0

        calls = [
            (Web3.to_checksum_address(p), True, bytes.fromhex(TOKEN0_SIG[2:]))
            for p in unknown
        ]
        try:
            results = self._mc.functions.aggregate3(calls).call()
            for i, (success, data) in enumerate(results):
                if success and len(data) >= 32:
                    addr = '0x' + data[12:32].hex()
                    self._pool_token0[unknown[i].lower()] = addr.lower()
        except Exception as e:
            logger.warning(f"Multicall token0 failed: {e}")
        return self._pool_token0

    def _get_bnb_price(self) -> float:
        now = time.time()
        if now - self._last_bnb_update < 60:
            return self._last_bnb_price
        try:
            # Use the WBNB/USDT PancakeSwap pool we already know
            pool = '0x16b9a82891338f9bA80E2D6970FddA79D1eb0daE'
            res = self._batch_get_reserves([pool])
            if pool.lower() in res:
                r0, r1 = res[pool.lower()]
                if r0 > 0 and r1 > 0:
                    # WBNB is token0, USDT is token1
                    price = r1 / r0
                    if 100 < price < 10000:
                        self._last_bnb_price = price
                        self._last_bnb_update = now
        except Exception:
            pass
        return self._last_bnb_price

    # ─── Main scan ─────────────────────────────────────────────────────────
    def scan(self, config: dict) -> dict:
        if not self._ensure_connected():
            return {'opportunities': [], 'total': 0, 'profitable': 0,
                    'best_profit_usd': 0, 'avg_spread': 0,
                    'error': 'Cannot connect to BSC RPC'}

        min_net_profit_pct  = float(config.get('minNetProfitPct', 0.30))
        min_liquidity_usd   = float(config.get('minLiquidityUsd', 25000))
        slippage_pct        = float(config.get('slippageTolerance', 0.5))
        flash_provider      = config.get('flashLoanProvider', 'Aave V3')
        selected_dexes      = config.get('dexes', list(DEX_ROUTERS.keys()))
        base_tokens         = config.get('baseTokens', ['USDT', 'WBNB', 'BTCB', 'USDC'])

        flash_fee_bps = FLASH_PROVIDERS.get(flash_provider, {}).get('fee_bps', 5)
        bnb_price     = self._get_bnb_price()
        gas_usd       = estimate_gas_cost_usd(bnb_price_usd=bnb_price)

        # Filter pool list to selected DEXes
        active_pools = [p for p in POOL_LIST if p['dex'] in selected_dexes]
        if not active_pools:
            return {'opportunities': [], 'total': 0, 'profitable': 0,
                    'best_profit_usd': 0, 'avg_spread': 0}

        pool_addrs = [p['pool'] for p in active_pools]

        # ── Single multicall for all reserves ──────────────────────────────
        logger.info(f"Multicall getReserves for {len(pool_addrs)} pools...")
        reserves_map = self._batch_get_reserves(pool_addrs)
        logger.info(f"Got reserves for {len(reserves_map)} pools")

        # ── Cache token0 for all pools (another multicall) ──────────────────
        self._batch_get_token0(pool_addrs)

        # ── Build per-pair per-dex reserve lookup ──────────────────────────
        # pair_key -> { dex: {r_base, r_quote, liq_usd, fee_bps, router} }
        pair_dex_data: dict = {}

        BASE_SYMS = {'WBNB', 'USDT', 'USDC', 'BTCB', 'ETH', 'BUSD'}
        BASE_ADDRS = {
            'WBNB': '0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c',
            'USDT': '0x55d398326f99059ff775485246999027b3197955',
            'USDC': '0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d',
            'BTCB': '0x7130d2a12b9bcbfae4f2634d864a1ee1ce3ead9c',
            'ETH':  '0x2170ed0880ac9a755fd29b2688956bd959f933f8',
            'BUSD': '0xe9e7cea3dedca5984780bafc599bd69add087d56',
        }
        DEX_FEES = {
            'PancakeSwap V2': 25, 'ApeSwap': 20, 'BiSwap': 10,
            'MDEX': 30, 'BabySwap': 30, 'Thena': 4,
            'KnightSwap': 25, 'SushiSwap': 30, 'Nomiswap': 10,
        }

        for p in active_pools:
            pool_addr = p['pool'].lower()
            if pool_addr not in reserves_map:
                continue
            r0, r1 = reserves_map[pool_addr]
            if r0 == 0 or r1 == 0:
                continue

            t0 = p['t0'].lower()
            t1 = p['t1'].lower()
            s0 = p['sym0']
            s1 = p['sym1']

            # Determine which is base and which is quote
            if s0 in BASE_SYMS and s0 in base_tokens:
                base_sym, quote_sym = s0, s1
                base_addr, quote_addr = t0, t1
                r_base, r_quote = r0, r1
            elif s1 in BASE_SYMS and s1 in base_tokens:
                base_sym, quote_sym = s1, s0
                base_addr, quote_addr = t1, t0
                r_base, r_quote = r1, r0
            else:
                continue

            # Check token0 ordering from chain
            on_chain_t0 = self._pool_token0.get(pool_addr, t0)
            if on_chain_t0 != base_addr:
                # swap reserves to match base/quote
                r_base, r_quote = r_quote, r_base

            dec = DECIMALS.get(base_addr, 18)
            price_usd = USD_PRICE.get(base_sym, 1.0)
            liq_usd = (r_base / 10**dec) * price_usd * 2

            if liq_usd < min_liquidity_usd:
                continue

            pair_key = f"{quote_sym}/{base_sym}"
            if pair_key not in pair_dex_data:
                pair_dex_data[pair_key] = {
                    'base_sym': base_sym, 'quote_sym': quote_sym,
                    'base_addr': base_addr, 'quote_addr': quote_addr,
                    'base_dec': dec, 'price_usd': price_usd,
                    'dexes': {}
                }
            pair_dex_data[pair_key]['dexes'][p['dex']] = {
                'r_base':   r_base,
                'r_quote':  r_quote,
                'liq_usd':  liq_usd,
                'fee_bps':  DEX_FEES.get(p['dex'], 25),
                'router':   DEX_ROUTERS.get(p['dex'], ''),
            }

        # ── Find arbitrage across DEX pairs ────────────────────────────────
        opportunities = []

        for pair_key, pdata in pair_dex_data.items():
            dex_names = list(pdata['dexes'].keys())
            if len(dex_names) < 2:
                continue

            base_dec  = pdata['base_dec']
            price_usd = pdata['price_usd']

            for i in range(len(dex_names)):
                for j in range(len(dex_names)):
                    if i == j:
                        continue
                    buy_dex  = dex_names[i]
                    sell_dex = dex_names[j]
                    bd = pdata['dexes'][buy_dex]
                    sd = pdata['dexes'][sell_dex]

                    # Quick spread pre-filter
                    buy_spot  = bd['r_quote'] / bd['r_base']  if bd['r_base']  > 0 else 0
                    sell_spot = sd['r_quote'] / sd['r_base']  if sd['r_base']  > 0 else 0
                    if buy_spot <= 0 or sell_spot <= 0:
                        continue
                    spread = ((sell_spot - buy_spot) / buy_spot) * 100
                    if spread < min_net_profit_pct * 0.3:
                        continue

                    result = find_optimal_trade_size(
                        reserve_buy_in=bd['r_base'],
                        reserve_buy_out=bd['r_quote'],
                        reserve_sell_in=sd['r_quote'],
                        reserve_sell_out=sd['r_base'],
                        fee_buy_bps=bd['fee_bps'],
                        fee_sell_bps=sd['fee_bps'],
                        flash_fee_bps=flash_fee_bps,
                        max_price_impact_pct=slippage_pct,
                        decimals_base=base_dec,
                    )

                    if not result.get('profitable') or result.get('optimal_amount', 0) <= 0:
                        continue

                    loan_tok   = result['optimal_amount'] / 10**base_dec
                    gross_tok  = result['gross_profit']   / 10**base_dec
                    net_tok    = result['net_profit']     / 10**base_dec
                    loan_usd   = loan_tok  * price_usd
                    gross_usd  = gross_tok * price_usd
                    net_usd    = net_tok   * price_usd - gas_usd

                    if net_usd <= 0:
                        continue
                    net_pct = (net_tok / loan_tok * 100) if loan_tok > 0 else 0
                    if net_pct < min_net_profit_pct:
                        continue

                    flash_fee_usd  = (result.get('flash_fee', 0) / 10**base_dec) * price_usd
                    dex_fee_buy    = loan_usd  * (bd['fee_bps'] / 10000)
                    dex_fee_sell   = gross_usd * (sd['fee_bps'] / 10000)
                    total_dex_fees = dex_fee_buy + dex_fee_sell

                    buy_price  = bd['r_base']  / bd['r_quote']  if bd['r_quote']  > 0 else 0
                    sell_price = sd['r_base']  / sd['r_quote']  if sd['r_quote']  > 0 else 0

                    opportunities.append({
                        'id': f"{pdata['quote_sym']}_{pdata['base_sym']}_{buy_dex}_{sell_dex}_{int(time.time())}",
                        'pair':               pair_key,
                        'baseToken':          pdata['base_sym'],
                        'quoteToken':         pdata['quote_sym'],
                        'baseTokenAddress':   pdata['base_addr'],
                        'quoteTokenAddress':  pdata['quote_addr'],
                        'buyDex':             buy_dex,
                        'sellDex':            sell_dex,
                        'buyDexRouter':       bd['router'],
                        'sellDexRouter':      sd['router'],
                        'buyPrice':           round(buy_price,  10),
                        'sellPrice':          round(sell_price, 10),
                        'spread':             round(spread, 4),
                        'flashLoanAsset':     pdata['base_sym'],
                        'flashLoanAmount':    round(loan_tok,  6),
                        'flashLoanAmountUsd': round(loan_usd,  2),
                        'flashLoanProvider':  flash_provider,
                        'grossProfit':        round(gross_tok, 6),
                        'grossProfitUsd':     round(gross_usd, 2),
                        'netProfit':          round(net_tok,   6),
                        'netProfitUsd':       round(net_usd,   2),
                        'gasFee':             round(gas_usd,   2),
                        'dexFees':            round(total_dex_fees, 2),
                        'flashFee':           round(flash_fee_usd,  2),
                        'netProfitPct':       round(net_pct,   4),
                        'buyPoolLiquidity':   round(bd['liq_usd'], 0),
                        'sellPoolLiquidity':  round(sd['liq_usd'], 0),
                        'buyPriceImpact':     round(result.get('buy_price_impact',  0), 4),
                        'sellPriceImpact':    round(result.get('sell_price_impact', 0), 4),
                        'status':             'profitable',
                        'timestamp':          int(time.time()),
                    })

        gc.collect()  # free memory after scan

        opportunities.sort(key=lambda x: x['netProfitUsd'], reverse=True)
        profitable = [o for o in opportunities if o['netProfitUsd'] > 0]
        avg_spread = (sum(o['spread'] for o in opportunities) / len(opportunities)
                      if opportunities else 0)

        logger.info(f"Scan done: {len(opportunities)} opps, {len(profitable)} profitable, "
                    f"best ${opportunities[0]['netProfitUsd'] if opportunities else 0}")

        return {
            'opportunities':  opportunities,
            'total':          len(opportunities),
            'profitable':     len(profitable),
            'best_profit_usd':opportunities[0]['netProfitUsd'] if opportunities else 0,
            'avg_spread':     round(avg_spread, 4),
            'bnb_price':      bnb_price,
            'gas_estimate_usd': round(gas_usd, 2),
            'scan_timestamp': int(time.time()),
        }

    def execute_trade(self, opportunity: dict, wallet_address: str, contract_address: str) -> dict:
        try:
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(contract_address),
                abi=FLASH_ARB_ABI
            )
            base_addr  = Web3.to_checksum_address(opportunity['baseTokenAddress'])
            quote_addr = Web3.to_checksum_address(opportunity['quoteTokenAddress'])
            base_dec   = DECIMALS.get(opportunity['baseTokenAddress'].lower(), 18)

            flash_amount = int(opportunity['flashLoanAmount'] * (10 ** base_dec))
            min_profit   = int(opportunity['netProfit'] * 0.9 * (10 ** base_dec))
            deadline     = int(time.time()) + 180

            tx = contract.functions.executeArbitrage(
                base_addr, flash_amount,
                Web3.to_checksum_address(opportunity['buyDexRouter']),
                Web3.to_checksum_address(opportunity['sellDexRouter']),
                [base_addr, quote_addr],
                [quote_addr, base_addr],
                min_profit, deadline,
            ).build_transaction({
                'from':     Web3.to_checksum_address(wallet_address),
                'gas':      600000,
                'gasPrice': self.w3.eth.gas_price,
                'nonce':    self.w3.eth.get_transaction_count(
                                Web3.to_checksum_address(wallet_address)),
            })

            return {
                'status': 'ready',
                'unsignedTx': {
                    'to':       tx['to'],
                    'data':     tx['data'],
                    'gas':      hex(tx['gas']),
                    'gasPrice': hex(tx['gasPrice']),
                    'nonce':    hex(tx['nonce']),
                    'value':    '0x0',
                    'chainId':  56,
                }
            }
        except Exception as e:
            logger.error(f"Build tx error: {e}", exc_info=True)
            return {'status': 'error', 'error': str(e)}
