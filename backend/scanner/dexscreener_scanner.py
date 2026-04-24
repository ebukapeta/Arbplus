"""
DexScreener Scanner — Base Class
Uses DexScreener live price API instead of on-chain reserve math.
All EVM network scanners inherit from this class.

Fee model:
  - gas_usd    : fixed tx cost (real-world: same computation regardless of loan size)
  - dex_fee_pct: percentage of trade size (0.3% buy + 0.3% sell = 0.6% default)
  - flash_fee  : percentage of loan (provider's bps / 100)
"""

import time
import logging
import requests
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# Validation modules — imported lazily to avoid circular imports and
# to allow scanners that don't have Web3 (Solana) to still function.
_reserve_fetcher   = None
_router_validator  = None
_execution_engine  = None

def _load_validators():
    global _reserve_fetcher, _router_validator, _execution_engine
    if _reserve_fetcher is None:
        try:
            from . import reserve_fetcher  as _rf
            from . import router_validator as _rv
            from . import execution_engine as _ee
            _reserve_fetcher  = _rf
            _router_validator = _rv
            _execution_engine = _ee
        except Exception as e:
            logging.getLogger(__name__).warning(f"Validators not loaded: {e}")

logger = logging.getLogger(__name__)

# ── DexScreener API helpers ───────────────────────────────────────────────────

def _get(url: str, timeout: int = 12) -> Optional[dict]:
    try:
        r = requests.get(url, timeout=timeout,
                         headers={'User-Agent': 'ArbPulse-Scanner/2.0'})
        if r.status_code == 429:
            logger.warning("DexScreener rate-limited — sleeping 3s")
            time.sleep(3)
            r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.debug(f"DexScreener GET {url[:60]} → {e}")
        return None


def fetch_token_pairs(chain: str, token_address: str) -> list:
    data = _get(f"https://api.dexscreener.com/token-pairs/v1/{chain}/{token_address}")
    if isinstance(data, list):
        return data
    return []


def fetch_token_batch(chain: str, addresses: list) -> list:
    if not addresses:
        return []
    joined = ','.join(addresses[:30])
    data = _get(f"https://api.dexscreener.com/tokens/v1/{chain}/{joined}")
    if isinstance(data, list):
        return data
    return []


def fetch_search_pairs(chain: str, query: str) -> list:
    data = _get(f"https://api.dexscreener.com/latest/dex/search?q={requests.utils.quote(query)}")
    if not isinstance(data, dict):
        return []
    pairs = data.get('pairs') or []
    return [p for p in pairs if isinstance(p, dict)
            and str(p.get('chainId', '')).lower() == chain.lower()]


def parallel_fetch(fn, args_list: list, max_workers: int = 8, delay: float = 0.1) -> list:
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fn, *args): args for args in args_list}
        for f in as_completed(futures):
            try:
                result = f.result()
                if result:
                    results.extend(result)
            except Exception as e:
                logger.debug(f"Parallel fetch error: {e}")
            time.sleep(delay)
    return results


# ── DEX name normalisation ────────────────────────────────────────────────────

def normalize_dex(raw_dex_id: str, alias_map: dict) -> str:
    if not raw_dex_id:
        return ''
    key = raw_dex_id.strip().lower()
    import re as _re
    if _re.match(r'^0x[a-f0-9]{8,}$', key):
        return ''
    if key in alias_map:
        return alias_map[key]
    return ' '.join(w.capitalize() for w in key.replace('-', ' ').replace('_', ' ').split())


# ── Core opportunity derivation ───────────────────────────────────────────────

def derive_opportunities(
    pairs: list,
    main_tokens: set,
    stable_symbols: set,
    dex_alias_map: dict,
    price_fallbacks: dict,
    flash_fee_pct: float,
    gas_usd: float,
    min_net_profit_usd: float = 0.20,
    min_liquidity_usd: float = 30_000,
    loan_cap_ratio: float = 0.0025,
    min_loan_usd: float = 200.0,
    price_impact_mult: float = 1.5,
    # DEX swap fee: 0.3% buy + 0.3% sell = 0.6% of trade size
    # This scales proportionally with loan size (unlike fixed gas_usd)
    dex_fee_pct: float = 0.60,
    min_spread_pct: float = 0.05,
) -> tuple:
    """
    Derive arbitrage opportunities from DexScreener pairs.

    Fee breakdown per opportunity
    ─────────────────────────────
    gas_usd       Fixed blockchain tx cost. Same whether loan is $200 or $200k.
                  Differs per chain (BSC ~$0.32, ETH ~$28, ARB ~$0.12, Base ~$0.05).
    dex_fee_usd   loan_usd × 0.60%  →  scales with trade size.
                  (0.3% on buy DEX + 0.3% on sell DEX — standard V2/V3 fee tier)
    flash_fee_usd loan_usd × provider_bps/100  →  scales with trade size.
                  (DODO 0%, PancakeV3 0.01%, Aave 0.05%, Balancer 0%)

    Returns (opportunities: list, stats: dict).
    """

    # ── Build USD price oracle using stable-pair mean ─────────────────────────
    price_sum: dict = {}
    price_count: dict = {}
    for sym, usd in price_fallbacks.items():
        price_sum[sym.upper()] = usd
        price_count[sym.upper()] = 1

    for pair in pairs:
        liq   = float(pair.get('liquidity', {}).get('usd') or 0)
        price = float(pair.get('priceUsd') or 0)
        if price <= 0 or liq < 80_000:
            continue
        base_sym  = (pair.get('baseToken',  {}).get('symbol') or '').upper()
        quote_sym = (pair.get('quoteToken', {}).get('symbol') or '').upper()
        if not base_sym or not quote_sym:
            continue
        base_is_main  = base_sym  in main_tokens
        quote_is_main = quote_sym in main_tokens
        if not base_is_main and not quote_is_main:
            continue
        main_sym   = base_sym  if base_is_main  else quote_sym
        stable_sym = quote_sym if base_is_main  else base_sym
        if stable_sym not in stable_symbols:
            continue
        price_sum[main_sym]   = price_sum.get(main_sym, 0)   + price
        price_count[main_sym] = price_count.get(main_sym, 0) + 1

    token_usd: dict = {
        sym: price_sum[sym] / max(price_count[sym], 1)
        for sym in price_sum
    }

    # ── Group pairs into buckets ──────────────────────────────────────────────
    buckets: dict = {}
    skipped_liq = 0
    skipped_nomatch = 0

    for pair in pairs:
        price = float(pair.get('priceUsd') or 0)
        liq   = float(pair.get('liquidity', {}).get('usd') or 0)
        if price <= 0 or liq < min_liquidity_usd:
            skipped_liq += 1
            continue

        base_sym  = (pair.get('baseToken',  {}).get('symbol') or '').upper()
        quote_sym = (pair.get('quoteToken', {}).get('symbol') or '').upper()
        if not base_sym or not quote_sym:
            continue

        dex_name = normalize_dex(pair.get('dexId', ''), dex_alias_map)
        if not dex_name:
            skipped_nomatch += 1
            continue

        base_is_main  = base_sym  in main_tokens
        quote_is_main = quote_sym in main_tokens
        if not base_is_main and not quote_is_main:
            skipped_nomatch += 1
            continue

        loan_asset  = base_sym  if base_is_main  else quote_sym
        quote_asset = quote_sym if base_is_main  else base_sym

        if quote_asset not in stable_symbols and quote_asset not in main_tokens:
            skipped_nomatch += 1
            continue

        loan_addr  = (pair.get('baseToken',  {}).get('address') or '') if base_is_main  else (pair.get('quoteToken', {}).get('address') or '')
        quote_addr = (pair.get('quoteToken', {}).get('address') or '') if base_is_main  else (pair.get('baseToken',  {}).get('address') or '')

        key = f"{loan_asset}/{quote_asset}"
        bucket = buckets.setdefault(key, [])
        bucket.append({
            'dex':         dex_name,
            'price_usd':   price,
            'liq_usd':     liq,
            'loan_asset':  loan_asset,
            'quote_asset': quote_asset,
            'loan_addr':   loan_addr,
            'quote_addr':  quote_addr,
            'pool_addr':   pair.get('pairAddress', ''),
            'chain_id':    pair.get('chainId', ''),
        })

    logger.info(f"  Pair buckets: {len(buckets)} | skipped liq={skipped_liq} nomatch={skipped_nomatch}")

    # ── Derive opportunities ──────────────────────────────────────────────────
    opportunities = []
    near_misses   = []
    eligible_pools = sum(len(b) for b in buckets.values())

    for key, bucket in buckets.items():
        if len(bucket) < 2:
            continue
        sorted_b  = sorted(bucket, key=lambda x: x['price_usd'])
        buy       = sorted_b[0]
        sell      = sorted_b[-1]

        if buy['dex'] == sell['dex']:
            continue

        buy_price  = buy['price_usd']
        sell_price = sell['price_usd']
        if buy_price <= 0:
            continue

        spread_pct = ((sell_price - buy_price) / buy_price) * 100
        if spread_pct < min_spread_pct:
            continue
        both_stable = (buy['loan_asset'] in stable_symbols and buy['quote_asset'] in stable_symbols)
        if both_stable and spread_pct > 5.0:
            continue

        pair_liq_usd      = min(buy['liq_usd'], sell['liq_usd'])
        loan_usd          = max(min_loan_usd, pair_liq_usd * loan_cap_ratio)
        loan_asset_usd    = token_usd.get(buy['loan_asset'], 1.0)
        loan_amt          = loan_usd / max(loan_asset_usd, 1e-9)

        price_impact_pct  = (loan_usd / max(pair_liq_usd, 1)) * 100 * price_impact_mult

        # Fee components
        # dex_fee_usd and flash_fee_usd both scale with loan_usd (volume-proportional)
        # gas_usd is fixed regardless of loan size (fixed computation cost on-chain)
        dex_fee_usd       = loan_usd * (dex_fee_pct   / 100)
        flash_fee_usd     = loan_usd * (flash_fee_pct / 100)
        impact_fee_usd    = loan_usd * (price_impact_pct / 100)
        total_fee_usd     = dex_fee_usd + flash_fee_usd + impact_fee_usd

        gross_profit_usd  = loan_usd * (spread_pct / 100)
        net_profit_usd    = gross_profit_usd - total_fee_usd - gas_usd
        net_pct           = (net_profit_usd / loan_usd * 100) if loan_usd > 0 else 0

        if net_profit_usd <= 0:
            near_misses.append({
                'pair': key, 'buy_dex': buy['dex'], 'sell_dex': sell['dex'],
                'spread': round(spread_pct, 4),
                'gross_usd': round(gross_profit_usd, 3),
                'fee_usd': round(total_fee_usd, 3),
                'gas_usd': round(gas_usd, 3),
                'net_usd': round(net_profit_usd, 3),
            })
            continue

        is_profitable = net_profit_usd >= min_net_profit_usd
        status = 'profitable' if is_profitable else 'marginal'

        opportunities.append({
            'id':                f"{buy['loan_asset']}_{buy['quote_asset']}_{buy['dex']}_{sell['dex']}_{int(time.time())}",
            'pair':              key,
            'baseToken':         buy['loan_asset'],
            'quoteToken':        buy['quote_asset'],
            'baseTokenAddress':  buy['loan_addr'],
            'quoteTokenAddress': buy['quote_addr'],
            'buyDex':            buy['dex'],
            'sellDex':           sell['dex'],
            'buyPrice':          round(buy_price,  8),
            'sellPrice':         round(sell_price, 8),
            'spread':            round(spread_pct, 4),
            'flashLoanAsset':    buy['loan_asset'],
            'flashLoanAmount':   round(loan_amt,   6),
            'flashLoanAmountUsd':round(loan_usd,   2),
            'flashLoanProvider': '',
            'flashLoanPool':     '',
            'grossProfit':       round(gross_profit_usd / max(loan_asset_usd, 1e-9), 6),
            'grossProfitUsd':    round(gross_profit_usd, 2),
            'netProfit':         round(net_profit_usd  / max(loan_asset_usd, 1e-9), 6),
            'netProfitUsd':      round(net_profit_usd,  2),
            'gasFee':            round(gas_usd,          2),
            'dexFees':           round(dex_fee_usd,      2),
            'flashFee':          round(flash_fee_usd,    2),
            'netProfitPct':      round(net_pct,    4),
            'buyPoolLiquidity':  round(buy['liq_usd'],  0),
            'sellPoolLiquidity': round(sell['liq_usd'], 0),
            'buyPriceImpact':    round(price_impact_pct / 2, 4),
            'sellPriceImpact':   round(price_impact_pct / 2, 4),
            'status':            status,
            'poolAddress':       buy['pool_addr'],
            'timestamp':         int(time.time()),
        })

    opportunities.sort(key=lambda x: x['netProfitUsd'], reverse=True)

    stats = {
        'bucket_count':    len(buckets),
        'eligible_pools':  eligible_pools,
        'near_misses':     near_misses,
        'token_usd':       token_usd,
    }
    return opportunities, stats


# ── DexScreenerScanner base class ────────────────────────────────────────────

class DexScreenerScanner:
    DEXSCREENER_CHAIN = 'bsc'
    NETWORK_NAME      = 'Network'
    BASE_TOKENS_MAINNET: dict = {}
    BASE_TOKENS_TESTNET: dict = {}
    PRICE_FALLBACKS: dict = {}
    DEX_ALIASES: dict = {}
    STABLE_SYMBOLS: set = {'USDT','USDC','DAI','BUSD','FRAX','LUSD','GHO','USDbC','USDR'}
    FLASH_PROVIDERS_MAINNET: list = []
    FLASH_PROVIDERS_TESTNET: list = []
    GAS_UNITS:  int   = 350_000
    GAS_GWEI_MAINNET: float = 5.0
    GAS_GWEI_TESTNET: float = 3.0
    NATIVE_PRICE_USD: float = 600.0

    def __init__(self, testnet: bool = False):
        self.testnet = testnet
        label = 'Testnet' if testnet else 'Mainnet'
        logger.info(f"{self.NETWORK_NAME} {label} scanner initialised (DexScreener mode)")

    @property
    def _base_tokens(self) -> dict:
        return self.BASE_TOKENS_TESTNET if self.testnet else self.BASE_TOKENS_MAINNET

    @property
    def _flash_providers(self) -> list:
        return self.FLASH_PROVIDERS_TESTNET if self.testnet else self.FLASH_PROVIDERS_MAINNET

    def _gas_usd(self) -> float:
        gwei = self.GAS_GWEI_TESTNET if self.testnet else self.GAS_GWEI_MAINNET
        return self.GAS_UNITS * gwei * 1e-9 * self.NATIVE_PRICE_USD

    def _select_flash_provider(self, base_sym: str) -> dict:
        for p in self._flash_providers:
            supported = p.get('assets', [])
            if not supported or base_sym in supported:
                return p
        return self._flash_providers[0] if self._flash_providers else {'name': 'Auto', 'fee_bps': 5}

    def _fetch_all_pairs(self, base_tokens: list, config: dict) -> list:
        chain = self.DEXSCREENER_CHAIN
        logger.info(f"[{self.NETWORK_NAME}] Fetching DexScreener pairs for {len(base_tokens)} base tokens …")

        primary_pairs = parallel_fetch(
            fetch_token_pairs,
            [(chain, addr) for addr in base_tokens],
            max_workers=6, delay=0.15,
        )
        logger.info(f"  Primary fetch: {len(primary_pairs)} raw pairs")

        min_exp_liq   = 40_000 if self.DEXSCREENER_CHAIN == 'ethereum' else 80_000
        exp_limit     = 140 if self.DEXSCREENER_CHAIN != 'ethereum' else 420
        base_addr_set = {a.lower() for a in base_tokens}

        expansion_addrs = list(dict.fromkeys([
            (p.get('quoteToken', {}).get('address') or ''
             if (p.get('baseToken',  {}).get('address') or '').lower() in base_addr_set
             else p.get('baseToken', {}).get('address') or '')
            for p in sorted(primary_pairs,
                            key=lambda x: float(x.get('liquidity', {}).get('usd') or 0),
                            reverse=True)
            if float(p.get('liquidity', {}).get('usd') or 0) >= min_exp_liq
            and (p.get('baseToken',  {}).get('address') or '').lower() in base_addr_set
               != (p.get('quoteToken', {}).get('address') or '').lower() in base_addr_set
        ][:exp_limit]))
        expansion_addrs = [a for a in expansion_addrs if a and len(a) > 10]

        expansion_pairs = []
        if expansion_addrs:
            chunks = [expansion_addrs[i:i+30] for i in range(0, len(expansion_addrs), 30)]
            expansion_pairs = parallel_fetch(
                fetch_token_batch,
                [(chain, chunk) for chunk in chunks],
                max_workers=4, delay=0.2,
            )
            logger.info(f"  Expansion fetch: {len(expansion_addrs)} tokens → {len(expansion_pairs)} pairs")

        main_syms = list(self._base_tokens.keys())
        search_queries = []
        for sym in main_syms[:8]:
            search_queries += [sym, f"{sym}/USDT", f"{sym}/USDC"]
        searched_pairs = parallel_fetch(
            fetch_search_pairs,
            [(chain, q) for q in search_queries],
            max_workers=4, delay=0.2,
        )
        logger.info(f"  Search fetch: {len(search_queries)} queries → {len(searched_pairs)} pairs")

        all_pairs  = primary_pairs + expansion_pairs + searched_pairs
        seen       = {}
        unique     = []
        for p in all_pairs:
            key = f"{p.get('chainId','')}-{p.get('pairAddress','')}-{p.get('dexId','')}"
            if key not in seen:
                seen[key] = True
                unique.append(p)

        logger.info(f"  Total unique pairs: {len(unique)}")
        return unique

    def scan(self, config: dict) -> dict:
        label        = 'Testnet' if self.testnet else 'Mainnet'
        base_tokens  = config.get('baseTokens', list(self._base_tokens.keys()))
        min_net_pct  = float(config.get('minNetProfitPct', 0.05))
        min_liq_usd  = float(config.get('minLiquidityUsd', 30_000))

        gas_usd = self._gas_usd()
        logger.info(
            f"\n{'='*60}\n"
            f"[{self.NETWORK_NAME} {label}] Scan start\n"
            f"  Base tokens : {base_tokens}\n"
            f"  Gas est.    : ${gas_usd:.4f} (fixed tx cost)\n"
            f"  DEX fee     : 0.60% of trade size (0.3% buy + 0.3% sell)\n"
            f"{'='*60}"
        )

        base_addrs = [self._base_tokens[s] for s in base_tokens if s in self._base_tokens]
        if not base_addrs:
            logger.error("No valid base token addresses found")
            return {'opportunities':[],'total':0,'profitable':0,'best_profit_usd':0,'avg_spread':0,'error':'No valid base tokens'}

        start = __import__('time').time()
        all_pairs = self._fetch_all_pairs(base_addrs, config)
        fetch_time = round(__import__('time').time() - start, 2)

        if not all_pairs:
            logger.warning("No pairs returned from DexScreener")
            return {'opportunities':[],'total':0,'profitable':0,'best_profit_usd':0,'avg_spread':0}

        cheapest_provider = self._flash_providers[0] if self._flash_providers else {'name':'Auto','fee_bps':5}
        flash_fee_pct     = cheapest_provider['fee_bps'] / 100

        opps, stats = derive_opportunities(
            pairs           = all_pairs,
            main_tokens     = set(t.upper() for t in list(self._base_tokens.keys())),
            stable_symbols  = self.STABLE_SYMBOLS,
            dex_alias_map   = self.DEX_ALIASES,
            price_fallbacks = self.PRICE_FALLBACKS,
            flash_fee_pct   = flash_fee_pct,
            gas_usd         = gas_usd,
            min_net_profit_usd = 0.10,
            min_liquidity_usd  = min_liq_usd,
        )

        for opp in opps:
            provider = self._select_flash_provider(opp['baseToken'])
            opp['flashLoanProvider'] = provider['name']
            opp['flashLoanPool']     = provider.get('pool', '')
            opp['testnet']           = self.testnet
            opp['executionStatus']   = 'candidate'

        # ── Verification gate ─────────────────────────────────────────────
        # Run reserve + router checks on EVM chains (requires Web3).
        # Solana validation is handled in SolanaScanner.scan() override.
        w3 = getattr(self, 'w3', None)
        if w3 and not self.testnet:
            _load_validators()
            opps = self._verify_opportunities(opps, w3)

        profitable = [o for o in opps
                      if o['netProfitUsd'] > 0
                      and o['netProfitPct'] >= min_net_pct
                      and o.get('executionStatus') != 'rejected']
        # Filter out rejected opps before sending to frontend and computing stats
        visible_opps = [o for o in opps if o.get('executionStatus') != 'rejected']
        rejected_count = len(opps) - len(visible_opps)

        avg_spread = round(sum(o['spread'] for o in visible_opps) / len(visible_opps), 4) if visible_opps else 0
        best_profit = visible_opps[0]['netProfitUsd'] if visible_opps else 0

        logger.info(
            f"\n[{self.NETWORK_NAME} {label}] Scan complete in {fetch_time}s\n"
            f"  Unique pools  : {len(all_pairs)}\n"
            f"  Pair buckets  : {stats['bucket_count']}\n"
            f"  Eligible pools: {stats['eligible_pools']}\n"
            f"  Opportunities : {len(visible_opps)} visible | {rejected_count} rejected | {len(profitable)} profitable\n"
            f"  Avg spread    : {avg_spread:.4f}%\n"
            + (f"  Best net profit: ${best_profit:.2f}" if visible_opps else "  No opportunities found")
        )

        if visible_opps:
            logger.info(f"\n[{self.NETWORK_NAME}] TOP {min(10, len(visible_opps))} OPPORTUNITIES:")
            for i, opp in enumerate(visible_opps[:10], 1):
                logger.info(
                    f"  #{i:2d} {opp['pair']:25s} "
                    f"{opp['buyDex']:20s} → {opp['sellDex']:20s} "
                    f"spread={opp['spread']:.4f}% "
                    f"loan=${opp['flashLoanAmountUsd']:,.0f} "
                    f"dex_fee=${opp['dexFees']:.2f} "
                    f"gas=${opp['gasFee']:.2f} "
                    f"net=${opp['netProfitUsd']:.2f} "
                    f"[{opp['flashLoanProvider']}] [{opp.get('executionStatus','?')}]"
                )

        near = stats['near_misses']
        if near:
            logger.info(f"\n[{self.NETWORK_NAME}] NEAR MISSES (top 5):")
            for nm in sorted(near, key=lambda x: x['net_usd'], reverse=True)[:5]:
                logger.info(
                    f"  {nm['pair']:25s} {nm['buy_dex']} → {nm['sell_dex']:20s} "
                    f"spread={nm['spread']:.3f}% gross=${nm['gross_usd']:.2f} "
                    f"fees=${nm['fee_usd']:.2f} gas=${nm['gas_usd']:.2f} "
                    f"net=${nm['net_usd']:.2f}"
                )

        return {
            'opportunities':    visible_opps[:50],
            'total':            len(visible_opps),
            'profitable':       len(profitable),
            'best_profit_usd':  best_profit,
            'avg_spread':       avg_spread,
            'rejected_count':   rejected_count,
            'pool_universe':    len(all_pairs),
            'bucket_count':     stats['bucket_count'],
            'gas_estimate_usd': round(gas_usd, 4),
            'fetch_time_s':     fetch_time,
            'scan_timestamp':   int(__import__('time').time()),
        }

    def _verify_opportunities(self, opps: list, w3) -> list:
        """
        Run on-chain verification for each opportunity.
        Uses reserve_fetcher and router_validator.
        Max 8 verifications per scan to limit RPC latency.
        """
        if not _reserve_fetcher or not _router_validator or not _execution_engine:
            return opps

        routers   = getattr(self, '_dex_routers', {})
        price_map = {k.upper(): v for k, v in getattr(self, 'PRICE_FALLBACKS', {}).items()}

        verified_count = 0
        MAX_VERIFY     = 8

        for opp in opps:
            if verified_count >= MAX_VERIFY:
                break
            if opp.get('executionStatus') == 'rejected':
                continue

            spread      = opp.get('spread', 0)
            pool_addr   = opp.get('poolAddress', '')
            buy_router  = routers.get(opp['buyDex'],  '')
            sell_router = routers.get(opp['sellDex'], '')
            base_token  = opp.get('baseToken', '')
            base_price  = price_map.get(base_token.upper(), 1.0)
            loan_usd    = opp.get('flashLoanAmountUsd', 200)

            # Step 1: Flash loan size check (no RPC needed)
            size_ok, size_reason = _execution_engine.verify_flashloan_size_limits(
                opp, self._flash_providers
            )
            if not size_ok:
                _execution_engine.mark_rejected(opp, size_reason)
                logger.info(f"  REJECTED {opp['pair']}: {size_reason}")
                continue

            # Step 2: Reserve freshness (requires pool address)
            if pool_addr and len(pool_addr) > 10:
                reserves = _reserve_fetcher.get_pair_contract_reserves(
                    w3, pool_addr,
                    opp.get('baseTokenAddress', ''),
                    opp.get('quoteTokenAddress', ''),
                )
                if not reserves['valid']:
                    _execution_engine.mark_rejected(opp, reserves['reason'])
                    logger.info(f"  REJECTED {opp['pair']}: {reserves['reason']}")
                    verified_count += 1
                    continue

            # Step 3: Router validation (requires both routers known)
            # Use _resolve_router if available (chain subclasses), else routers.get()
            if not buy_router or not sell_router:
                resolve = getattr(self, '_resolve_router', None)
                if resolve:
                    buy_router  = resolve(opp['buyDex'])
                    sell_router = resolve(opp['sellDex'])

            if buy_router and sell_router:
                result = _router_validator.verify_router_execution(
                    w3, buy_router, sell_router,
                    opp.get('baseTokenAddress', ''),
                    opp.get('quoteTokenAddress', ''),
                    loan_usd, base_price, spread,
                )
                verified_count += 1
                if not result['valid']:
                    # candidate = unverified but still showable; rejected = confirmed bad
                    if result.get('status') == 'candidate':
                        opp['executionStatus'] = 'candidate'
                        opp['status']          = 'candidate'
                    else:
                        _execution_engine.mark_rejected(opp, result['reason'])
                        logger.info(f"  REJECTED {opp['pair']}: {result['reason']}")
                    continue
                _execution_engine.mark_verified(opp, result['confirmed_spread'])
                _execution_engine.mark_execution_ready(opp)
                logger.info(f"  VERIFIED {opp['pair']}: {result['reason']}")
            else:
                # Router not in our table — leave as candidate, don't reject
                opp['executionStatus'] = 'candidate'
                opp['status']          = 'candidate'

        return opps

    def execute_trade(self, opportunity: dict, wallet_address: str, contract_address: str) -> dict:
        return {'status': 'error', 'error': 'execute_trade not implemented in base class'}
