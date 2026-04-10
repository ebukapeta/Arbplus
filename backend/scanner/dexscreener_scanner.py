"""
DexScreener Scanner — Base Class
Uses DexScreener live price API (same approach as App.tsx) instead of on-chain reserve math.
All EVM network scanners inherit from this class.

DexScreener API endpoints used:
  GET /token-pairs/v1/{chain}/{tokenAddress}   — pairs for a single token
  GET /tokens/v1/{chain}/{addr1,addr2,...}      — batch token pairs
  GET /latest/dex/search?q={query}             — search by symbol

This replicates the deriveOpportunities() logic from App.tsx in Python.
"""

import time
import logging
import requests
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

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
    """Fetch all pairs for a single token address."""
    data = _get(f"https://api.dexscreener.com/token-pairs/v1/{chain}/{token_address}")
    if isinstance(data, list):
        return data
    return []


def fetch_token_batch(chain: str, addresses: list) -> list:
    """Fetch pairs for up to 30 token addresses in one request."""
    if not addresses:
        return []
    joined = ','.join(addresses[:30])
    data = _get(f"https://api.dexscreener.com/tokens/v1/{chain}/{joined}")
    if isinstance(data, list):
        return data
    return []


def fetch_search_pairs(chain: str, query: str) -> list:
    """Search DexScreener by symbol/query, filter to chain."""
    data = _get(f"https://api.dexscreener.com/latest/dex/search?q={requests.utils.quote(query)}")
    if not isinstance(data, dict):
        return []
    pairs = data.get('pairs') or []
    return [p for p in pairs if isinstance(p, dict)
            and str(p.get('chainId', '')).lower() == chain.lower()]


def parallel_fetch(fn, args_list: list, max_workers: int = 8, delay: float = 0.1) -> list:
    """Run fetch calls in parallel, return merged list."""
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
    """Map DexScreener dexId to canonical DEX name.
    Returns empty string for hex addresses (pool addresses, not dex names)
    so they are skipped — same logic as App.tsx normalizeDexName().
    """
    if not raw_dex_id:
        return ''
    key = raw_dex_id.strip().lower()
    # Skip if dexId is actually a contract/pool address (0x + hex chars)
    import re as _re
    if _re.match(r'^0x[a-f0-9]{8,}$', key):
        return ''
    if key in alias_map:
        return alias_map[key]
    # Prettify unknown IDs (capitalise each word)
    return ' '.join(w.capitalize() for w in key.replace('-', ' ').replace('_', ' ').split())


# ── Core opportunity derivation (replicates App.tsx deriveOpportunities) ─────

def derive_opportunities(
    pairs: list,
    main_tokens: set,          # set of upper-case symbols e.g. {'WBNB', 'USDT', ...}
    stable_symbols: set,       # e.g. {'USDT', 'USDC', 'DAI', 'BUSD', ...}
    dex_alias_map: dict,       # dexId → canonical name
    price_fallbacks: dict,     # symbol → USD price fallback
    flash_fee_pct: float,      # e.g. 0.0 for DODO, 0.05 for Aave
    gas_usd: float,            # estimated gas cost in USD
    min_net_profit_usd: float = 0.20,
    min_liquidity_usd: float = 30_000,
    loan_cap_ratio: float = 0.0025,   # 0.25% of pool liquidity
    min_loan_usd: float = 200.0,
    price_impact_mult: float = 1.5,
    dex_fee_pct: float = 0.08,        # combined estimate (buy + sell)
    min_spread_pct: float = 0.05,
) -> tuple:
    """
    Derive arbitrage opportunities from DexScreener pairs.
    Returns (opportunities: list, stats: dict).
    """

    # ── Build USD price oracle using stable-pair mean ─────────────────────────
    price_sum: dict = {}
    price_count: dict = {}
    # Seed with fallbacks
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
        prev_sum   = price_sum.get(main_sym, 0)
        prev_count = price_count.get(main_sym, 0)
        price_sum[main_sym]   = prev_sum   + price
        price_count[main_sym] = prev_count + 1

    token_usd: dict = {
        sym: price_sum[sym] / max(price_count[sym], 1)
        for sym in price_sum
    }

    # ── Group pairs into buckets by loanAsset/quoteAsset ────────────────────
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

    # ── Derive opportunities from buckets ─────────────────────────────────────
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
        # Skip stable/stable pairs with unrealistic spread (> 5%) — stale price data
        both_stable = (buy['loan_asset'] in stable_symbols and buy['quote_asset'] in stable_symbols)
        if both_stable and spread_pct > 5.0:
            continue

        pair_liq_usd  = min(buy['liq_usd'], sell['liq_usd'])
        loan_usd      = max(min_loan_usd, pair_liq_usd * loan_cap_ratio)
        loan_asset_usd= token_usd.get(buy['loan_asset'], 1.0)
        loan_amt      = loan_usd / max(loan_asset_usd, 1e-9)

        price_impact_pct  = (loan_usd / max(pair_liq_usd, 1)) * 100 * price_impact_mult
        total_fee_pct     = flash_fee_pct + dex_fee_pct + price_impact_pct
        gross_profit_usd  = loan_usd * (spread_pct / 100)
        total_fee_usd     = loan_usd * (total_fee_pct / 100)
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
            'flashLoanProvider': '',      # filled by subclass
            'flashLoanPool':     '',      # filled by subclass
            'grossProfit':       round(gross_profit_usd / max(loan_asset_usd, 1e-9), 6),
            'grossProfitUsd':    round(gross_profit_usd, 2),
            'netProfit':         round(net_profit_usd  / max(loan_asset_usd, 1e-9), 6),
            'netProfitUsd':      round(net_profit_usd,  2),
            'gasFee':            round(gas_usd,          2),
            'dexFees':           round(loan_usd * (dex_fee_pct / 100), 2),
            'flashFee':          round(loan_usd * (flash_fee_pct / 100), 2),
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
    """
    Base scanner that uses DexScreener live prices for opportunity detection.
    Subclasses provide network-specific constants and execute_trade().
    """

    # ── Override in subclass ──────────────────────────────────────────────────
    DEXSCREENER_CHAIN = 'bsc'           # chain ID for DexScreener API
    NETWORK_NAME      = 'Network'
    BASE_TOKENS_MAINNET: dict = {}      # symbol → address
    BASE_TOKENS_TESTNET: dict = {}
    PRICE_FALLBACKS: dict = {}          # symbol → USD fallback
    DEX_ALIASES: dict = {}              # dexId → canonical name
    STABLE_SYMBOLS: set = {'USDT','USDC','DAI','BUSD','FRAX','LUSD','GHO','USDbC','USDR'}
    FLASH_PROVIDERS_MAINNET: list = []
    FLASH_PROVIDERS_TESTNET: list = []
    GAS_UNITS:  int   = 350_000
    GAS_GWEI_MAINNET: float = 5.0
    GAS_GWEI_TESTNET: float = 3.0
    NATIVE_PRICE_USD: float = 600.0
    # ── End overrides ─────────────────────────────────────────────────────────

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
        """Return cheapest provider that supports the base token."""
        for p in self._flash_providers:
            supported = p.get('assets', [])
            if not supported or base_sym in supported:
                return p
        return self._flash_providers[0] if self._flash_providers else {'name': 'Auto', 'fee_bps': 5}

    def _fetch_all_pairs(self, base_tokens: list, config: dict) -> list:
        """
        Full DexScreener fetch pipeline (mirrors App.tsx runScanCycle):
          1. Primary pairs for each base token
          2. Expansion tokens discovered from primary pairs
          3. Batch fetch expansion tokens
          4. Search by symbol for each base token
        """
        chain = self.DEXSCREENER_CHAIN
        logger.info(f"[{self.NETWORK_NAME}] Fetching DexScreener pairs for {len(base_tokens)} base tokens …")

        # ── Step 1: Primary pairs ──────────────────────────────────────────────
        primary_pairs = parallel_fetch(
            fetch_token_pairs,
            [(chain, addr) for addr in base_tokens],
            max_workers=6, delay=0.15,
        )
        logger.info(f"  Primary fetch: {len(primary_pairs)} raw pairs")

        # ── Step 2: Discover expansion tokens ────────────────────────────────
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

        # ── Step 3: Batch fetch expansion tokens ─────────────────────────────
        expansion_pairs = []
        if expansion_addrs:
            chunks = [expansion_addrs[i:i+30] for i in range(0, len(expansion_addrs), 30)]
            expansion_pairs = parallel_fetch(
                fetch_token_batch,
                [(chain, chunk) for chunk in chunks],
                max_workers=4, delay=0.2,
            )
            logger.info(f"  Expansion fetch: {len(expansion_addrs)} tokens → {len(expansion_pairs)} pairs")

        # ── Step 4: Search by symbol ──────────────────────────────────────────
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

        # ── Merge & deduplicate ───────────────────────────────────────────────
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
        label     = 'Testnet' if self.testnet else 'Mainnet'
        base_tokens  = config.get('baseTokens', list(self._base_tokens.keys()))
        min_net_pct  = float(config.get('minNetProfitPct', 0.05))
        min_liq_usd  = float(config.get('minLiquidityUsd', 30_000))

        gas_usd = self._gas_usd()
        logger.info(
            f"\n{'='*60}\n"
            f"[{self.NETWORK_NAME} {label}] Scan start\n"
            f"  Base tokens : {base_tokens}\n"
            f"  Gas est.    : ${gas_usd:.4f}\n"
            f"{'='*60}"
        )

        # Resolve base token addresses
        base_addrs = [self._base_tokens[s] for s in base_tokens if s in self._base_tokens]
        if not base_addrs:
            logger.error("No valid base token addresses found")
            return {'opportunities':[],'total':0,'profitable':0,'best_profit_usd':0,'avg_spread':0,'error':'No valid base tokens'}

        # Fetch pairs from DexScreener
        start = __import__('time').time()
        all_pairs = self._fetch_all_pairs(base_addrs, config)
        fetch_time = round(__import__('time').time() - start, 2)

        if not all_pairs:
            logger.warning("No pairs returned from DexScreener")
            return {'opportunities':[],'total':0,'profitable':0,'best_profit_usd':0,'avg_spread':0}

        # Select cheapest flash provider for fee calculation
        # (each opportunity will get its own provider assigned below)
        cheapest_provider = self._flash_providers[0] if self._flash_providers else {'name':'Auto','fee_bps':5}
        flash_fee_pct     = cheapest_provider['fee_bps'] / 100

        # Derive opportunities
        opps, stats = derive_opportunities(
            pairs          = all_pairs,
            main_tokens    = set(t.upper() for t in list(self._base_tokens.keys())),
            stable_symbols = self.STABLE_SYMBOLS,
            dex_alias_map  = self.DEX_ALIASES,
            price_fallbacks= self.PRICE_FALLBACKS,
            flash_fee_pct  = flash_fee_pct,
            gas_usd        = gas_usd,
            min_net_profit_usd = 0.10,
            min_liquidity_usd  = min_liq_usd,
        )

        # Assign flash providers to each opportunity
        for opp in opps:
            provider = self._select_flash_provider(opp['baseToken'])
            opp['flashLoanProvider'] = provider['name']
            opp['flashLoanPool']     = provider.get('pool', '')
            opp['testnet']           = self.testnet

        # Filter by min net profit %
        profitable = [o for o in opps if o['netProfitUsd'] > 0 and o['netProfitPct'] >= min_net_pct]
        avg_spread = round(sum(o['spread'] for o in opps) / len(opps), 4) if opps else 0

        # ── Logging ────────────────────────────────────────────────────────────
        logger.info(
            f"\n[{self.NETWORK_NAME} {label}] Scan complete in {fetch_time}s\n"
            f"  Unique pools  : {len(all_pairs)}\n"
            f"  Pair buckets  : {stats['bucket_count']}\n"
            f"  Eligible pools: {stats['eligible_pools']}\n"
            f"  Opportunities : {len(opps)} total | {len(profitable)} profitable\n"
            f"  Avg spread    : {avg_spread:.4f}%\n"
            f"  Best net profit: ${opps[0]['netProfitUsd']:.2f}" if opps else "  No opportunities found"
        )

        if opps:
            logger.info(f"\n[{self.NETWORK_NAME}] TOP {min(10, len(opps))} OPPORTUNITIES:")
            for i, opp in enumerate(opps[:10], 1):
                logger.info(
                    f"  #{i:2d} {opp['pair']:25s} "
                    f"{opp['buyDex']:20s} → {opp['sellDex']:20s} "
                    f"spread={opp['spread']:.4f}% "
                    f"loan=${opp['flashLoanAmountUsd']:,.0f} "
                    f"net=${opp['netProfitUsd']:.2f} "
                    f"[{opp['flashLoanProvider']}]"
                )

        near = stats['near_misses']
        if near:
            logger.info(f"\n[{self.NETWORK_NAME}] NEAR MISSES (top 5 — just below gas threshold):")
            for nm in sorted(near, key=lambda x: x['net_usd'], reverse=True)[:5]:
                logger.info(
                    f"  {nm['pair']:25s} {nm['buy_dex']} → {nm['sell_dex']:20s} "
                    f"spread={nm['spread']:.3f}% gross=${nm['gross_usd']:.2f} "
                    f"fees=${nm['fee_usd']:.2f} gas=${nm['gas_usd']:.2f} "
                    f"net=${nm['net_usd']:.2f}"
                )

        return {
            'opportunities':    opps[:50],
            'total':            len(opps),
            'profitable':       len(profitable),
            'best_profit_usd':  opps[0]['netProfitUsd'] if opps else 0,
            'avg_spread':       avg_spread,
            'pool_universe':    len(all_pairs),
            'bucket_count':     stats['bucket_count'],
            'gas_estimate_usd': round(gas_usd, 4),
            'fetch_time_s':     fetch_time,
            'scan_timestamp':   int(__import__('time').time()),
        }

    def execute_trade(self, opportunity: dict, wallet_address: str, contract_address: str) -> dict:
        """Override in subclass for network-specific execution."""
        return {'status': 'error', 'error': 'execute_trade not implemented in base class'}
