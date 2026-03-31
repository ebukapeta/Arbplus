"""
BSC DEX Scanner — Fixed Reserve Ordering + Spread Logging
Key fix: UniswapV2 always makes token0 the lower address. We compute
this from addresses directly — no extra RPC call needed.
This eliminates the reserve-swap bug that was causing all spreads to
appear near-zero and no opportunities to be found.
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

# ─── Function selectors ───────────────────────────────────────────────────────
SEL_GET_PAIR     = bytes.fromhex('e6a43905')   # getPair(address,address)
SEL_GET_RESERVES = bytes.fromhex('0902f1ac')   # getReserves()
MULTICALL3_ADDR  = '0xcA11bde05977b3631167028862bE2a173976CA11'

MULTICALL3_ABI = json.loads('[{"inputs":[{"components":[{"internalType":"address","name":"target","type":"address"},{"internalType":"bool","name":"allowFailure","type":"bool"},{"internalType":"bytes","name":"callData","type":"bytes"}],"internalType":"struct Multicall3.Call3[]","name":"calls","type":"tuple[]"}],"name":"aggregate3","outputs":[{"components":[{"internalType":"bool","name":"success","type":"bool"},{"internalType":"bytes","name":"returnData","type":"bytes"}],"internalType":"struct Multicall3.Result[]","name":"returnData","type":"tuple[]"}],"stateMutability":"view","type":"function"}]')

FLASH_ARB_ABI = json.loads('[{"inputs":[{"internalType":"address","name":"_flashLoanAsset","type":"address"},{"internalType":"uint256","name":"_flashLoanAmount","type":"uint256"},{"internalType":"address","name":"_buyDex","type":"address"},{"internalType":"address","name":"_sellDex","type":"address"},{"internalType":"address[]","name":"_buyPath","type":"address[]"},{"internalType":"address[]","name":"_sellPath","type":"address[]"},{"internalType":"uint256","name":"_minProfit","type":"uint256"},{"internalType":"uint256","name":"_deadline","type":"uint256"}],"name":"executeArbitrage","outputs":[],"stateMutability":"nonpayable","type":"function"}]')

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

# Mid-cap tokens with real cross-DEX price differences
QUOTE_TOKENS = {
    'CAKE':    '0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82',
    'XVS':     '0xcF6BB5389c92Bdda8a3747Ddb454cB7a64626C63',
    'ALPACA':  '0x8F0528cE5eF7B51152A59745bEfDD91D97091d2F',
    'BSW':     '0x965F527D9159dCe6288a2219DB51fc6Eef120dD1',
    'THE':     '0xF4C8E32EaDEC4BFe97E0F595ADD0f4450a863a5',
    'WOM':     '0xAD6742A35fB341A9Cc6ad674738Dd8da98b94Fb1',
    'DODO':    '0x67ee3Cb086F8a16f34beE3ca72FAD36F7Db929e2',
    'C98':     '0xaEC945e04baF28b135Fa7c640138d2e26c4f5bE2',
    'CHESS':   '0x20de22029ab63cf9A7Cf5fEB2b737Ca1eE4c82A6',
    'FLOKI':   '0xfb5B838b6cfEEdC2873aB27866079AC55363D37E',
    'PEPE':    '0x25d887Ce7a35172C62FeBFD67a1856F20FaEbB00',
    'BABYDOGE':'0xc748673057861a797275CD8A068AbB95A902e8de',
    'SHIB':    '0x2859e4544C4bB03966803b044A93563Bd2D0DD4D',
    'ALICE':   '0xAC51066d7bEC65Dc4589368da368b212745d63E8',
    'GALA':    '0x7dDEE176F665cD201F93eEDE625770E2fD911990',
    'MBOX':    '0x3203c9E46cA618C8C1cE5dC67e7e9D75f5da2377',
    'ETH':     '0x2170Ed0880ac9A755fd29B2688956BD959F933F8',
    'XRP':     '0x1D2F0da169ceB9fC7B3144628dB156f3F6c60dBE',
    'ADA':     '0x3EE2200Efb3400fAbB9AacF31297cBdD1d435D47',
    'DOGE':    '0xbA2aE424d960c26247Dd6c32edC70B295c744C43',
    'DOT':     '0x7083609fCE4d1d8Dc0C979AAb8cf214F57432DF3',
    'LINK':    '0xF8A0BF9cF54Bb92F17374d9e9A321E6a111a51bD',
    'MATIC':   '0xCC42724C6683B7E57334c4E856f4c9965ED682bD',
    'NEAR':    '0x1Fa4a73a3F0133f0025378af00236f3aBDEE5D63',
    'FTM':     '0xAD29AbB318791D579433D831ed122aFeAf29dcfe',
}

ALL_TOKEN_SYM = {v.lower(): k for k, v in {**BASE_TOKENS, **QUOTE_TOKENS}.items()}


def _sort_tokens(addr_a: str, addr_b: str):
    """
    UniswapV2 always assigns token0 = the address with lower numeric value.
    Returns (token0_addr_lower, token1_addr_lower).
    No RPC call needed — it's deterministic from the addresses alone.
    """
    a = addr_a.lower()
    b = addr_b.lower()
    if int(a, 16) < int(b, 16):
        return a, b
    return b, a


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
        self._pair_cache: dict = {}  # (base_low, quote_low, dex) -> pool_addr_lower
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
        """calls = list of (target_str, calldata_bytes). Returns [(success, returnData)]."""
        if not calls or not self._mc:
            return []
        results = []
        CHUNK = 200
        for i in range(0, len(calls), CHUNK):
            chunk = calls[i:i + CHUNK]
            mc_calls = [
                (Web3.to_checksum_address(t.lower()), True, cd)
                for t, cd in chunk
            ]
            try:
                res = self._mc.functions.aggregate3(mc_calls).call()
                results.extend(res)
            except Exception as e:
                logger.warning(f"Multicall chunk {i // CHUNK} failed: {e}")
                results.extend([(False, b'')] * len(chunk))
        return results

    # ─── Phase 1: Discover real pool addresses ────────────────────────────
    def _discover_pools(self, base_tokens: list, selected_dexes: list) -> dict:
        """
        Calls getPair(base, quote) on every factory for every combo.
        Returns { (base_low, quote_low, dex): pool_addr_lower }
        Results are cached so only called once per server restart.
        """
        factories = {dex: DEX_CONFIGS[dex]['factory']
                     for dex in selected_dexes if dex in DEX_CONFIGS}

        to_discover = []
        for base_sym in base_tokens:
            if base_sym not in BASE_TOKENS:
                continue
            base_addr = BASE_TOKENS[base_sym].lower()
            for quote_sym, quote_addr_raw in QUOTE_TOKENS.items():
                quote_addr = quote_addr_raw.lower()
                for dex, factory in factories.items():
                    key = (base_addr, quote_addr, dex)
                    if key not in self._pair_cache:
                        to_discover.append((base_addr, quote_addr, dex, factory, key))

        if to_discover:
            calls = [(item[3], _encode_get_pair(item[0], item[1]))
                     for item in to_discover]
            logger.info(f"getPair multicall: {len(calls)} pairs")
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
            logger.info(f"getPair: {found} real pools discovered")
        else:
            logger.info("All pairs already in cache")

        return {k: v for k, v in self._pair_cache.items() if v != NULL_ADDR}

    # ─── Phase 2: Fetch reserves for all discovered pools ────────────────
    def _fetch_reserves(self, pool_addrs: list) -> dict:
        """Returns { pool_addr_lower: (r0, r1) }"""
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
                        # Which reserve is WBNB? Use address sort
                        t0, _ = _sort_tokens(wbnb, usdt)
                        if t0 == wbnb:
                            price = r1 / r0  # r0=WBNB, r1=USDT
                        else:
                            price = r0 / r1  # r0=USDT, r1=WBNB
                        if 100 < price < 10000:
                            self._last_bnb_price = price
                            self._last_bnb_update = now
                            logger.info(f"BNB price updated: ${price:.2f}")
        except Exception as e:
            logger.warning(f"BNB price fetch error: {e}")
        return self._last_bnb_price

    # ─── Main scan ────────────────────────────────────────────────────────
    def scan(self, config: dict) -> dict:
        if not self._ensure_connected():
            return {'opportunities': [], 'total': 0, 'profitable': 0,
                    'best_profit_usd': 0, 'avg_spread': 0,
                    'error': 'Cannot connect to BSC RPC'}

        min_net_profit_pct = float(config.get('minNetProfitPct', 0.30))
        min_liquidity_usd  = float(config.get('minLiquidityUsd', 25000))
        slippage_pct       = float(config.get('slippageTolerance', 0.5))
        flash_provider     = config.get('flashLoanProvider', 'Aave V3')
        selected_dexes     = [d for d in config.get('dexes', []) if d in DEX_CONFIGS]
        base_tokens        = config.get('baseTokens', ['USDT', 'WBNB', 'BTCB', 'USDC'])

        flash_fee_bps = FLASH_PROVIDERS.get(flash_provider, {}).get('fee_bps', 5)
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
        # pair_data[pair_key] = { base_sym, quote_sym, ..., dexes: { dex: {...} } }
        pair_data: dict = {}

        for (base_low, quote_low, dex), pool_addr in pool_map.items():
            pool_low = pool_addr.lower()
            if pool_low not in reserves_map:
                continue
            r0, r1 = reserves_map[pool_low]

            base_sym  = ALL_TOKEN_SYM.get(base_low,  base_low[:8])
            quote_sym = ALL_TOKEN_SYM.get(quote_low, quote_low[:8])

            if base_sym not in BASE_TOKENS or base_sym not in base_tokens:
                continue

            # ── KEY FIX: Use address sort to determine which reserve is which ──
            # UniswapV2 always makes token0 = lower address, token1 = higher address.
            # No RPC call needed — it's a pure math operation on the addresses.
            t0, t1 = _sort_tokens(base_low, quote_low)
            if t0 == base_low:
                # base is token0 → r0 = base reserve, r1 = quote reserve
                r_base, r_quote = r0, r1
            else:
                # quote is token0 → r0 = quote reserve, r1 = base reserve
                r_base, r_quote = r1, r0

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
                'r_base':  r_base,
                'r_quote': r_quote,
                'liq_usd': liq_usd,
                'fee_bps': DEX_CONFIGS[dex]['fee_bps'],
                'router':  DEX_CONFIGS[dex]['router'],
            }

        pairs_multi = {k: v for k, v in pair_data.items() if len(v['dexes']) >= 2}
        logger.info(f"Pairs with ≥1 DEX: {len(pair_data)} | ≥2 DEXes (arb candidates): {len(pairs_multi)}")

        # ── Phase 3: Scan every DEX combination for every pair ────────────
        opportunities = []
        all_spreads   = []   # collect all spreads for logging even if not profitable

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

                    # Price of base in terms of quote on each DEX
                    # (how many quote tokens per 1 base token)
                    buy_spot  = bd['r_quote'] / bd['r_base']
                    sell_spot = sd['r_quote'] / sd['r_base']

                    if buy_spot <= 0 or sell_spot <= 0:
                        continue

                    # Spread: if sell_spot > buy_spot, base is "worth more"
                    # on the sell DEX, so we buy quote cheap on buy DEX
                    # and sell quote expensive on sell DEX for a base profit
                    spread = ((sell_spot - buy_spot) / buy_spot) * 100
                    all_spreads.append((pair_key, buy_dex, sell_dex, spread))

                    if spread <= 0:
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
                        decimals_base=dec,
                    )

                    if not result.get('profitable') or result.get('optimal_amount', 0) <= 0:
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
                    buy_price  = bd['r_base']  / bd['r_quote']  if bd['r_quote']  > 0 else 0
                    sell_price = sd['r_base']  / sd['r_quote']  if sd['r_quote']  > 0 else 0

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

        # ── Always log top spreads so you can see what's happening ────────
        if all_spreads:
            all_spreads.sort(key=lambda x: x[3], reverse=True)
            logger.info("Top 8 spreads found (positive only):")
            for pair, bdex, sdex, sp in [s for s in all_spreads if s[3] > 0][:8]:
                logger.info(f"  {pair:20s}  {bdex} → {sdex}  spread={sp:.4f}%")

            # Also log total fee cost so user can see the hurdle rate
            min_fee = (flash_fee_bps + 10 + 10) / 100  # flash + cheapest buy + cheapest sell
            max_fee = (flash_fee_bps + 30 + 30) / 100
            logger.info(f"Fee hurdle: {min_fee:.2f}% – {max_fee:.2f}% (flash={flash_fee_bps/100:.2f}% + DEX fees)")
        else:
            logger.info("No positive spreads found in any direction")

        gc.collect()

        opportunities.sort(key=lambda x: x['netProfitUsd'], reverse=True)
        profitable = [o for o in opportunities if o['netProfitUsd'] > 0]
        avg_spread = (sum(o['spread'] for o in opportunities) / len(opportunities)
                      if opportunities else 0)

        logger.info(f"Scan done: {len(opportunities)} opps, {len(profitable)} profitable, "
                    f"best ${opportunities[0]['netProfitUsd'] if opportunities else 0:.2f}")

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
            dec = 18

            flash_amount = int(opportunity['flashLoanAmount'] * (10 ** dec))
            min_profit   = int(opportunity['netProfit'] * 0.9 * (10 ** dec))
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
