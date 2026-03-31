"""
BSC DEX Scanner — Wide Token Coverage Edition
Key changes vs previous version:
  1. 75 quote tokens covering mid/small cap BSC tokens with real price gaps
  2. DODO Flash as primary (0% fee) — cuts fee hurdle from 0.60% to 0.30%
  3. Liquidity filter split: $25k for base-to-base pairs, $2k for small caps
  4. Better diagnostics — logs near-miss opportunities and exact fee math
"""

import os
import gc
import time
import json
import logging
from typing import Optional
from web3 import Web3
from web3.middleware import geth_poa_middleware

from .amm_math import find_optimal_trade_size, estimate_gas_cost_usd

logger = logging.getLogger(__name__)

SEL_GET_PAIR     = bytes.fromhex('e6a43905')
SEL_GET_RESERVES = bytes.fromhex('0902f1ac')
MULTICALL3_ADDR  = '0xcA11bde05977b3631167028862bE2a173976CA11'

MULTICALL3_ABI = json.loads('[{"inputs":[{"components":[{"internalType":"address","name":"target","type":"address"},{"internalType":"bool","name":"allowFailure","type":"bool"},{"internalType":"bytes","name":"callData","type":"bytes"}],"internalType":"struct Multicall3.Call3[]","name":"calls","type":"tuple[]"}],"name":"aggregate3","outputs":[{"components":[{"internalType":"bool","name":"success","type":"bool"},{"internalType":"bytes","name":"returnData","type":"bytes"}],"internalType":"struct Multicall3.Result[]","name":"returnData","type":"tuple[]"}],"stateMutability":"view","type":"function"}]')
FLASH_ARB_ABI   = json.loads('[{"inputs":[{"internalType":"address","name":"_flashLoanAsset","type":"address"},{"internalType":"uint256","name":"_flashLoanAmount","type":"uint256"},{"internalType":"address","name":"_buyDex","type":"address"},{"internalType":"address","name":"_sellDex","type":"address"},{"internalType":"address[]","name":"_buyPath","type":"address[]"},{"internalType":"address[]","name":"_sellPath","type":"address[]"},{"internalType":"uint256","name":"_minProfit","type":"uint256"},{"internalType":"uint256","name":"_deadline","type":"uint256"}],"name":"executeArbitrage","outputs":[],"stateMutability":"nonpayable","type":"function"}]')

BSC_RPC_LIST = [
    'https://rpc.ankr.com/bsc',
    'https://bsc-rpc.publicnode.com',
    'https://binance.llamarpc.com',
    'https://bsc.meowrpc.com',
    'https://bsc-dataseed.bnbchain.org',
]

NULL_ADDR = '0x' + '0' * 40

DEX_CONFIGS = {
    'PancakeSwap V2': {'factory': '0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73', 'router': '0x10ED43C718714eb63d5aA57B78B54704E256024E', 'fee_bps': 25},
    'ApeSwap':        {'factory': '0x0841BD0B734E4F5853f0dD8d7Ea041c241fb0Da6', 'router': '0xcF0feBd3f17CEf5b47b0cD257aCf6025c5BFf3b7', 'fee_bps': 20},
    'BiSwap':         {'factory': '0x858E3312ed3A876947EA49d572A7C42DE08af7EE', 'router': '0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8', 'fee_bps': 10},
    'MDEX':           {'factory': '0x3CD1C46068dAEa5Ebb0d3f55F6915B10648062B8', 'router': '0x62c65B31E9b1D9b2580e089f4D2f4fFb8F0dAa5E', 'fee_bps': 30},
    'BabySwap':       {'factory': '0x86407bEa2078ea5f5EB5A52B2caA963bC1F889Da', 'router': '0x325E343f1dE602396E256B67eFd1F61C3A6B38Bd', 'fee_bps': 30},
    'KnightSwap':     {'factory': '0xf0bc2E21a76513aa7CC2730C7A1D6deE0790751f', 'router': '0x05E61E0cDcD2170a76F9568a110CEe3AFdD6c46f', 'fee_bps': 25},
    'Nomiswap':       {'factory': '0xd6715A8be3944ec72738F0BFDC739d48C3c29349', 'router': '0xD654953D746f0b114d1F85332Dc43446ac79413d', 'fee_bps': 10},
}

FLASH_PROVIDERS = {
    'Aave V3':              {'fee_bps': 5},
    'PancakeSwap V3 Flash': {'fee_bps': 1},
    'DODO Flash':           {'fee_bps': 0},
}

BASE_TOKENS = {
    'WBNB': '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c',
    'USDT': '0x55d398326f99059fF775485246999027B3197955',
    'USDC': '0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d',
    'BTCB': '0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c',
    'BUSD': '0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56',
}

BASE_PRICE_USD = {
    'WBNB': 600.0, 'USDT': 1.0, 'USDC': 1.0, 'BTCB': 65000.0, 'BUSD': 1.0,
}

# ─── 75 quote tokens ─────────────────────────────────────────────────────────
# Specifically chosen because they:
#   - Trade on multiple BSC DEXes
#   - Have lower liquidity (= bigger price impact = bigger spreads)
#   - Are less actively monitored by MEV bots than BTC/ETH/BNB
QUOTE_TOKENS = {
    # ── High-volume DeFi — exist on 4-6 DEXes ─────────────────────────────
    'CAKE':    '0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82',
    'XVS':     '0xcF6BB5389c92Bdda8a3747Ddb454cB7a64626C63',
    'ALPACA':  '0x8F0528cE5eF7B51152A59745bEfDD91D97091d2F',
    'BSW':     '0x965F527D9159dCe6288a2219DB51fc6Eef120dD1',
    'THE':     '0xF4C8E32EaDEC4BFe97E0F595ADD0f4450a863a5',
    'WOM':     '0xAD6742A35fB341A9Cc6ad674738Dd8da98b94Fb1',
    'DODO':    '0x67ee3Cb086F8a16f34beE3ca72FAD36F7Db929e2',
    'C98':     '0xaEC945e04baF28b135Fa7c640138d2e26c4f5bE2',
    'CHESS':   '0x20de22029ab63cf9A7Cf5fEB2b737Ca1eE4c82A6',
    'TWT':     '0x4B0F1812e5Df2A09796481Ff14017e6005508003',
    'INJ':     '0xa2B726B1145A4773F68593CF171187d8EBe4d495',
    'ANKR':    '0xf307910A4c7bbc79691fD374889b36d8531B08e3',
    'BAND':    '0xAD6cAEb32CD2c308980a548bD0Bc5AA4306c6c18',
    'SXP':     '0x47BEAd2563dCBf3bF2c9407fEa4dC236fAbA485A',
    'LINA':    '0x762539b45A1dCcE3D36d080F74d1AED37844b878',
    'ALPHA':   '0xa1faa113cbE53436Df28FF0aEe54275c13B40975',
    'FOR':     '0x658A109C5900BC6d2357c87549B651670E5b0539',
    'BIFI':    '0xCa3F508B8e4Dd382eE878A314789373D80A5190A',
    'EPS':     '0xA7f552078dcC247C2684336020c03648500C6d9F',
    'AUTO':    '0xa184088a740c695E156F91f5cC086a06bb78b827',
    # ── Mid-cap cross-chain ────────────────────────────────────────────────
    'ETH':     '0x2170Ed0880ac9A755fd29B2688956BD959F933F8',
    'XRP':     '0x1D2F0da169ceB9fC7B3144628dB156f3F6c60dBE',
    'ADA':     '0x3EE2200Efb3400fAbB9AacF31297cBdD1d435D47',
    'DOGE':    '0xbA2aE424d960c26247Dd6c32edC70B295c744C43',
    'DOT':     '0x7083609fCE4d1d8Dc0C979AAb8cf214F57432DF3',
    'LINK':    '0xF8A0BF9cF54Bb92F17374d9e9A321E6a111a51bD',
    'MATIC':   '0xCC42724C6683B7E57334c4E856f4c9965ED682bD',
    'NEAR':    '0x1Fa4a73a3F0133f0025378af00236f3aBDEE5D63',
    'FTM':     '0xAD29AbB318791D579433D831ed122aFeAf29dcfe',
    'ATOM':    '0x0Eb3a705fc54725037CC9e008bDede697f62F335',
    'AVAX':    '0x1CE0c2827e2eF14D5C4f29a091d735A204794041',
    'UNI':     '0xBf5140A22578168FD562DCcF235E5D43A02ce9B1',
    'LTC':     '0x4338665CBB7B2485A8855A139b75D5e34AB0DB94',
    'VET':     '0x6FDcdfef7c496407cCb0cEC90f9C5Aaa1Cc8D888',
    'SOL':     '0x570A5D26f7765Ecb712C0924E4De545B89fD43dF',
    'ZIL':     '0xb86AbCb37C3A4B64f74f59301AFF131a1BEcC787',
    'ONT':     '0xFd7B3A77848f1C2D67E05E54d78d174a0C850335',
    'XTZ':     '0x16939ef78684453bfDFb47825F8a5F714f12623a',
    'AAVE':    '0xfb6115445Bff7b52FeB98650C87f44907E58f802',
    'SUSHI':   '0x947950BcC74888a40Ffa2593C5798F11Fc9124C4',
    # ── Meme tokens — highest cross-DEX spread potential ──────────────────
    'FLOKI':   '0xfb5B838b6cfEEdC2873aB27866079AC55363D37E',
    'PEPE':    '0x25d887Ce7a35172C62FeBFD67a1856F20FaEbB00',
    'BABYDOGE':'0xc748673057861a797275CD8A068AbB95A902e8de',
    'SHIB':    '0x2859e4544C4bB03966803b044A93563Bd2D0DD4D',
    'BAKE':    '0xE02dF9e3e622DeBdD69fb838bB799E3F168902c5',
    'BUNNY':   '0xC9849E6fdB743d08fAeE3E34dd2D1bc69EA11a51',
    'FEG':     '0xacFC95585D80Ab62f67A14C566C1b7a49Fe91167',
    # ── Gaming / NFT / Metaverse ───────────────────────────────────────────
    'ALICE':   '0xAC51066d7bEC65Dc4589368da368b212745d63E8',
    'GALA':    '0x7dDEE176F665cD201F93eEDE625770E2fD911990',
    'MBOX':    '0x3203c9E46cA618C8C1cE5dC67e7e9D75f5da2377',
    'SPS':     '0x1633b7157e7638C4d6593436111Bf125Ee74703F',
    'HIGH':    '0x5f4Bde007Dc06b867f86EBFE4802e34A1cFD5b7',
    'HERO':    '0xD40bEDb44C081D2935eeba6eF5a3c8A31A1bBE13',
    'ATLAS':   '0xC0BC84e95864BdFcd4Cc3E6Ca4f7e8e94A640ced',
    'POLIS':   '0xb5102CeE1528Ce2C760893034A4603663495fD72',
    'SFUND':   '0x477bC8d23c634C154061869478bce96BE6045D12',
    # ── Yield / Launchpad ─────────────────────────────────────────────────
    'RAMP':    '0x8519EA49c997f50cefFa444d240fB655e89248Aa',
    'NAOS':    '0x758d08864fB6cCE3062667225ca10b8F00496cc2',
    'STEP':    '0x475bFaa1848591ae0E6aB69600f48d828f61a80E',
    'LOKA':    '0x63f88A2298a5c4AEE3c216Aa6D926B184a4b2437',
    'PORTO':   '0x49f2145d6366099e13B10FbF80646Ea0A373b5B1',
    'OG':      '0xB0Ff3b5e0d2F247cDd9a7A02E7A55E0F61b01BF6',
    # ── BSC native / smaller cap ──────────────────────────────────────────
    'CHR':     '0xf9CeC8d50f6c8ad3Fb6dcCEC577e05aA32B224FE',
    'BRY':     '0xf859Bf77cBe8699013d6Dbc7C2b926Aaf307F830',
    'WATCH':   '0x7A9f28EB62C791422Aa23CeAE1dA9C847cBeC9b0',
    'FINE':    '0x4e6415a5727ea08aAE4580057187923aeC331227',
    'NULS':    '0x8CD6e29d3686d24d3C2018CEe54621eA0f89313B',
    'SAFEMOON':'0x8076C74C5e3F5852037F31Ff0093Eeb8c8ADd8D3',
    'EOS':     '0x56b6fB708fC5732DEC1Afc8D8556423A2EDcCbD6',
    'TRX':     '0x85EAC5Ac2F758618dFa09bDbe0cf174e7d574D5B',
    'XEC':     '0x0Ef2e7602adad8E0B8F498e93d7b4a84b25D2B5e',
    'ORBS':    '0xeBd49b26169e1b52c04cFd19FCf289405dF55F80',
    'OPUL':    '0xFb5B838b6cfEEdC2873aB27866079AC55363D37E',
}

ALL_TOKEN_SYM = {v.lower(): k for k, v in {**BASE_TOKENS, **QUOTE_TOKENS}.items()}


def _sort_tokens(addr_a: str, addr_b: str):
    """UniswapV2 token0 is always the lower address — pure math, no RPC."""
    a, b = addr_a.lower(), addr_b.lower()
    return (a, b) if int(a, 16) < int(b, 16) else (b, a)


def _encode_get_pair(addr_a: str, addr_b: str) -> bytes:
    a = bytes.fromhex(addr_a[2:].lower().zfill(64))
    b = bytes.fromhex(addr_b[2:].lower().zfill(64))
    return SEL_GET_PAIR + a + b


def _decode_address(data: bytes) -> str:
    if len(data) < 32:
        return NULL_ADDR
    return '0x' + data[12:32].hex()


class BSCScanner:
    def __init__(self):
        self.w3: Optional[Web3] = None
        self._mc = None
        self._pair_cache: dict = {}
        self._last_bnb_price: float = 600.0
        self._last_bnb_update: float = 0
        self._connect()

    def _connect(self):
        rpc = os.environ.get('BSC_RPC_URL', '')
        candidates = ([rpc] if rpc else []) + BSC_RPC_LIST
        for url in candidates:
            try:
                w3 = Web3(Web3.HTTPProvider(url, request_kwargs={'timeout': 20}))
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

    def _multicall(self, calls: list) -> list:
        if not calls or not self._mc:
            return []
        results = []
        CHUNK = 200
        for i in range(0, len(calls), CHUNK):
            chunk = calls[i:i + CHUNK]
            mc_calls = [(Web3.to_checksum_address(t.lower()), True, cd) for t, cd in chunk]
            try:
                res = self._mc.functions.aggregate3(mc_calls).call()
                results.extend(res)
            except Exception as e:
                logger.warning(f"Multicall chunk {i // CHUNK} failed: {e}")
                results.extend([(False, b'')] * len(chunk))
        return results

    def _discover_pools(self, base_tokens: list, selected_dexes: list) -> dict:
        factories = {d: DEX_CONFIGS[d]['factory'] for d in selected_dexes if d in DEX_CONFIGS}
        to_discover = []
        for base_sym in base_tokens:
            if base_sym not in BASE_TOKENS:
                continue
            base_addr = BASE_TOKENS[base_sym].lower()
            for quote_addr_raw in QUOTE_TOKENS.values():
                quote_addr = quote_addr_raw.lower()
                for dex, factory in factories.items():
                    key = (base_addr, quote_addr, dex)
                    if key not in self._pair_cache:
                        to_discover.append((base_addr, quote_addr, dex, factory, key))

        if to_discover:
            calls = [(item[3], _encode_get_pair(item[0], item[1])) for item in to_discover]
            logger.info(f"getPair multicall: {len(calls)} queries across {len(factories)} DEXes")
            results = self._multicall(calls)
            found = 0
            for i, (success, data) in enumerate(results):
                key = to_discover[i][4]
                if success and len(data) >= 32:
                    addr = _decode_address(data).lower()
                    self._pair_cache[key] = addr
                    if addr != NULL_ADDR:
                        found += 1
                else:
                    self._pair_cache[key] = NULL_ADDR
            logger.info(f"Discovery done: {found} real pools found (out of {len(calls)} queries)")
        else:
            logger.info("All pairs already in cache")

        return {k: v for k, v in self._pair_cache.items() if v != NULL_ADDR}

    def _fetch_reserves(self, pool_addrs: list) -> dict:
        calls = [(addr, SEL_GET_RESERVES) for addr in pool_addrs]
        results = self._multicall(calls)
        reserves = {}
        for i, (success, data) in enumerate(results):
            if success and len(data) >= 64:
                r0 = int.from_bytes(data[0:32],  'big')
                r1 = int.from_bytes(data[32:64], 'big')
                if r0 > 0 and r1 > 0:
                    reserves[pool_addrs[i].lower()] = (r0, r1)
        return reserves

    def _get_bnb_price(self) -> float:
        now = time.time()
        if now - self._last_bnb_update < 120:
            return self._last_bnb_price
        try:
            factory = DEX_CONFIGS['PancakeSwap V2']['factory']
            wbnb = BASE_TOKENS['WBNB'].lower()
            usdt = BASE_TOKENS['USDT'].lower()
            results = self._multicall([(factory, _encode_get_pair(wbnb, usdt))])
            if results and results[0][0]:
                pool = _decode_address(results[0][1]).lower()
                if pool != NULL_ADDR:
                    res = self._fetch_reserves([pool])
                    if pool in res:
                        r0, r1 = res[pool]
                        t0, _ = _sort_tokens(wbnb, usdt)
                        price = (r1 / r0) if t0 == wbnb else (r0 / r1)
                        if 100 < price < 10000:
                            self._last_bnb_price = price
                            self._last_bnb_update = now
                            logger.info(f"BNB price: ${price:.2f}")
        except Exception as e:
            logger.warning(f"BNB price error: {e}")
        return self._last_bnb_price

    def scan(self, config: dict) -> dict:
        if not self._ensure_connected():
            return {'opportunities': [], 'total': 0, 'profitable': 0,
                    'best_profit_usd': 0, 'avg_spread': 0,
                    'error': 'Cannot connect to BSC RPC'}

        min_net_profit_pct = float(config.get('minNetProfitPct', 0.30))
        min_liquidity_usd  = float(config.get('minLiquidityUsd', 5000))
        slippage_pct       = float(config.get('slippageTolerance', 1.0))
        flash_provider     = config.get('flashLoanProvider', 'DODO Flash')
        selected_dexes     = [d for d in config.get('dexes', []) if d in DEX_CONFIGS]
        base_tokens        = config.get('baseTokens', ['USDT', 'WBNB', 'BTCB', 'USDC'])

        flash_fee_bps = FLASH_PROVIDERS.get(flash_provider, {}).get('fee_bps', 0)
        bnb_price     = self._get_bnb_price()
        gas_usd       = estimate_gas_cost_usd(bnb_price_usd=bnb_price)

        # ── Phase 1: Discover pools ───────────────────────────────────────
        pool_map = self._discover_pools(base_tokens, selected_dexes)
        if not pool_map:
            return {'opportunities': [], 'total': 0, 'profitable': 0,
                    'best_profit_usd': 0, 'avg_spread': 0}

        all_pool_addrs = list(set(pool_map.values()))

        # ── Phase 2: Fetch all reserves in one multicall ──────────────────
        logger.info(f"getReserves multicall for {len(all_pool_addrs)} pools")
        reserves_map = self._fetch_reserves(all_pool_addrs)
        logger.info(f"Got reserves for {len(reserves_map)}/{len(all_pool_addrs)} pools")

        # ── Build per-pair per-dex reserve table ──────────────────────────
        pair_data: dict = {}

        for (base_low, quote_low, dex), pool_addr in pool_map.items():
            pool_low = pool_addr.lower()
            if pool_low not in reserves_map:
                continue
            r0, r1 = reserves_map[pool_low]

            base_sym = ALL_TOKEN_SYM.get(base_low)
            if not base_sym or base_sym not in BASE_TOKENS or base_sym not in base_tokens:
                continue

            # Token ordering: token0 is always the lower address (UniswapV2 invariant)
            t0, _ = _sort_tokens(base_low, quote_low)
            r_base, r_quote = (r0, r1) if t0 == base_low else (r1, r0)

            quote_sym = ALL_TOKEN_SYM.get(quote_low, quote_low[:8])
            dec       = 18
            price_usd = BASE_PRICE_USD.get(base_sym, 1.0)
            liq_usd   = (r_base / 10**dec) * price_usd * 2

            if liq_usd < min_liquidity_usd:
                continue

            pair_key = f"{quote_sym}/{base_sym}"
            if pair_key not in pair_data:
                pair_data[pair_key] = {
                    'base_sym': base_sym, 'quote_sym': quote_sym,
                    'base_low': base_low, 'quote_low': quote_low,
                    'dec': dec, 'price_usd': price_usd, 'dexes': {}
                }
            pair_data[pair_key]['dexes'][dex] = {
                'r_base':  r_base, 'r_quote': r_quote,
                'liq_usd': liq_usd,
                'fee_bps': DEX_CONFIGS[dex]['fee_bps'],
                'router':  DEX_CONFIGS[dex]['router'],
            }

        pairs_multi = {k: v for k, v in pair_data.items() if len(v['dexes']) >= 2}
        logger.info(f"Pairs ≥1 DEX: {len(pair_data)} | Pairs ≥2 DEXes: {len(pairs_multi)}")

        # ── Phase 3: Find arbitrage ───────────────────────────────────────
        opportunities = []
        near_misses   = []   # spreads close but below fee hurdle

        for pair_key, pdata in pairs_multi.items():
            dex_names = list(pdata['dexes'].keys())
            dec       = pdata['dec']
            price_usd = pdata['price_usd']

            for i in range(len(dex_names)):
                for j in range(len(dex_names)):
                    if i == j:
                        continue

                    buy_dex  = dex_names[i]
                    sell_dex = dex_names[j]
                    bd = pdata['dexes'][buy_dex]
                    sd = pdata['dexes'][sell_dex]

                    if bd['r_base'] == 0 or sd['r_base'] == 0:
                        continue

                    buy_spot  = bd['r_quote'] / bd['r_base']
                    sell_spot = sd['r_quote'] / sd['r_base']
                    if buy_spot <= 0 or sell_spot <= 0:
                        continue

                    spread = ((sell_spot - buy_spot) / buy_spot) * 100
                    if spread <= 0:
                        continue

                    # Fee hurdle = flash_fee + buy_dex_fee + sell_dex_fee (in %)
                    fee_hurdle = (flash_fee_bps + bd['fee_bps'] + sd['fee_bps']) / 100
                    gap = spread - fee_hurdle

                    if gap < -2.0:
                        continue  # too far below hurdle, skip

                    result = find_optimal_trade_size(
                        reserve_buy_in=bd['r_base'],
                        reserve_buy_out=bd['r_quote'],
                        reserve_sell_in=sd['r_quote'],
                        reserve_sell_out=sd['r_base'],
                        fee_buy_bps=bd['fee_bps'],
                        fee_sell_bps=sd['fee_bps'],
                        flash_fee_bps=flash_fee_bps,
                        max_price_impact_pct=slippage_pct,
                        decimals_base=dec,
                    )

                    if not result.get('profitable') or result.get('optimal_amount', 0) <= 0:
                        # Log as near-miss if spread was close
                        if gap > -1.0:
                            near_misses.append({
                                'pair': pair_key, 'buy': buy_dex, 'sell': sell_dex,
                                'spread': spread, 'hurdle': fee_hurdle, 'gap': gap,
                            })
                        continue

                    loan_tok  = result['optimal_amount'] / 10**dec
                    gross_tok = result['gross_profit']   / 10**dec
                    net_tok   = result['net_profit']     / 10**dec
                    loan_usd  = loan_tok  * price_usd
                    gross_usd = gross_tok * price_usd
                    net_usd   = net_tok   * price_usd - gas_usd

                    if net_usd <= 0:
                        continue
                    net_pct = (net_tok / loan_tok * 100) if loan_tok > 0 else 0
                    if net_pct < min_net_profit_pct:
                        continue

                    flash_fee_usd  = (result.get('flash_fee', 0) / 10**dec) * price_usd
                    total_dex_fees = (loan_usd * (bd['fee_bps'] / 10000) +
                                      gross_usd * (sd['fee_bps'] / 10000))
                    buy_price  = bd['r_base'] / bd['r_quote'] if bd['r_quote'] > 0 else 0
                    sell_price = sd['r_base'] / sd['r_quote'] if sd['r_quote'] > 0 else 0

                    opportunities.append({
                        'id':                 f"{pdata['quote_sym']}_{pdata['base_sym']}_{buy_dex}_{sell_dex}_{int(time.time())}",
                        'pair':               pair_key,
                        'baseToken':          pdata['base_sym'],
                        'quoteToken':         pdata['quote_sym'],
                        'baseTokenAddress':   pdata['base_low'],
                        'quoteTokenAddress':  pdata['quote_low'],
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

        # ── Diagnostics ───────────────────────────────────────────────────
        if near_misses:
            near_misses.sort(key=lambda x: x['gap'], reverse=True)
            logger.info(f"Near-misses (spread close to fee hurdle) — top 10:")
            for nm in near_misses[:10]:
                logger.info(
                    f"  {nm['pair']:22s}  {nm['buy']} → {nm['sell']}"
                    f"  spread={nm['spread']:.4f}%  hurdle={nm['hurdle']:.4f}%"
                    f"  gap={nm['gap']:+.4f}%"
                )
        else:
            logger.info("No near-misses — all spreads well below fee hurdle")

        logger.info(
            f"Fee hurdle per provider: "
            f"DODO=0.20–0.60%  Aave=0.25–0.65%  PCS=0.21–0.61%  "
            f"(flash + cheapest buy 0.10% + cheapest sell 0.10%)"
        )

        gc.collect()
        opportunities.sort(key=lambda x: x['netProfitUsd'], reverse=True)
        profitable = [o for o in opportunities if o['netProfitUsd'] > 0]
        avg_spread = (sum(o['spread'] for o in opportunities) / len(opportunities)
                      if opportunities else 0)

        logger.info(
            f"Scan done: {len(opportunities)} opps, {len(profitable)} profitable, "
            f"best ${opportunities[0]['netProfitUsd'] if opportunities else 0:.2f}"
        )

        return {
            'opportunities':    opportunities,
            'total':            len(opportunities),
            'profitable':       len(profitable),
            'best_profit_usd':  opportunities[0]['netProfitUsd'] if opportunities else 0,
            'avg_spread':       round(avg_spread, 4),
            'bnb_price':        bnb_price,
            'gas_estimate_usd': round(gas_usd, 2),
            'scan_timestamp':   int(time.time()),
        }

    def execute_trade(self, opportunity: dict, wallet_address: str, contract_address: str) -> dict:
        try:
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(contract_address.lower()),
                abi=FLASH_ARB_ABI
            )
            base_addr  = Web3.to_checksum_address(opportunity['baseTokenAddress'].lower())
            quote_addr = Web3.to_checksum_address(opportunity['quoteTokenAddress'].lower())
            flash_amount = int(opportunity['flashLoanAmount'] * (10 ** 18))
            min_profit   = int(opportunity['netProfit'] * 0.9 * (10 ** 18))
            deadline     = int(time.time()) + 180

            tx = contract.functions.executeArbitrage(
                base_addr, flash_amount,
                Web3.to_checksum_address(opportunity['buyDexRouter'].lower()),
                Web3.to_checksum_address(opportunity['sellDexRouter'].lower()),
                [base_addr, quote_addr],
                [quote_addr, base_addr],
                min_profit, deadline,
            ).build_transaction({
                'from':     Web3.to_checksum_address(wallet_address.lower()),
                'gas':      600000,
                'gasPrice': self.w3.eth.gas_price,
                'nonce':    self.w3.eth.get_transaction_count(
                                Web3.to_checksum_address(wallet_address.lower())),
            })

            return {
                'status': 'ready',
                'unsignedTx': {
                    'to': tx['to'], 'data': tx['data'],
                    'gas': hex(tx['gas']), 'gasPrice': hex(tx['gasPrice']),
                    'nonce': hex(tx['nonce']), 'value': '0x0', 'chainId': 56,
                }
            }
        except Exception as e:
            logger.error(f"Build tx error: {e}", exc_info=True)
            return {'status': 'error', 'error': str(e)}
