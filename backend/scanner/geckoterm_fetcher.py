"""
ArbPulse — GeckoTerminal Fetcher
Fetches DEX pair data from GeckoTerminal (CoinGecko's DEX product).
Used alongside DexScreener to widen pool coverage.

Key difference from DexScreener:
  - Different pool discovery — catches pairs DexScreener misses
  - Token endpoints indexed by contract address (not symbol)
  - Free tier: 30 requests/minute, no API key needed

Output pairs are normalised to the same dict shape as DexScreener pairs
so they drop into derive_opportunities() without any changes.
"""

import time
import logging
import requests
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

BASE_URL = 'https://api.geckoterminal.com/api/v2'

# GeckoTerminal chain slugs mapped from our internal chain names
CHAIN_SLUGS = {
    # DexScreener chain IDs (what DEXSCREENER_CHAIN is set to in each scanner)
    'bsc':       'bsc',
    'ethereum':  'eth',      # ETH scanner uses DEXSCREENER_CHAIN = 'ethereum'
    'arbitrum':  'arbitrum',
    'base':      'base',
    'solana':    'solana',
    # Short aliases (kept for any direct callers)
    'eth':       'eth',
    'arb':       'arbitrum',
}

# DexID aliases — map GeckoTerminal dex_id to the same names our scanners use
# so they resolve correctly in DEX_ALIASES → DEX_ROUTERS_MAINNET
GECKO_DEX_ALIASES = {
    # BSC
    'pancakeswap_v2':          'pancakeswap-amm',
    'pancakeswap_v3':          'pancakeswap-amm-v3',
    'biswap':                  'biswap',
    'apeswap':                 'apeswap',
    'thena':                   'thena',
    'babyswap':                'babyswap',
    'knightswap':              'knightswap',
    'sushiswap':               'sushiswap',
    'nomiswap':                'nomiswap',
    'mdex':                    'mdex',
    'squadswap':               'squadswap',
    # Ethereum
    'uniswap_v2':              'uniswap-v2',
    'uniswap_v3':              'uniswap-v3',
    'sushiswap_v2':            'sushiswap',
    'shibaswap':               'shibaswap',
    'curve':                   'curve',
    'balancer_v2':             'balancer-v2',
    'fraxswap':                'fraxswap',
    'kyberswap_elastic':       'kyberswap',
    # Arbitrum
    'camelot_v2':              'camelot-v2',
    'camelot':                 'camelot-v2',
    'ramses_v2':               'ramses',
    'trader_joe_v2':           'trader-joe-v2',
    'zyberswap_v3':            'zyberswap',
    'chronos':                 'chronos',
    'woofi':                   'woofi',
    # Base
    'aerodrome_slipstream':    'aerodrome-slipstream',
    'aerodrome_v1':            'aerodrome-v1',
    'baseswap':                'baseswap',
    'alienbase_v2':            'alienbase-v2',
    'swapbased':               'swapbased',
    'rocketswap':              'rocketswap',
    # Solana
    'raydium':                 'raydium',
    'raydium_clmm':            'raydium-clmm',
    'orca':                    'orca',
    'orca_whirlpool':          'orca-whirlpools',
    'meteora':                 'meteora-dlmm',
    'lifinity_v2':             'lifinity-v2',
}


def _get(url: str, params: dict = None, timeout: int = 12) -> Optional[dict]:
    try:
        r = requests.get(
            url,
            params=params,
            timeout=timeout,
            headers={
                'User-Agent': 'ArbPulse/2.0',
                'Accept':     'application/json',
            }
        )
        if r.status_code == 429:
            logger.warning("GeckoTerminal rate-limited — sleeping 4s")
            time.sleep(4)
            r = requests.get(url, params=params, timeout=timeout,
                             headers={'User-Agent': 'ArbPulse/2.0'})
        if r.status_code != 200:
            logger.debug(f"GeckoTerminal {url[-50:]} → HTTP {r.status_code}")
            return None
        return r.json()
    except Exception as e:
        logger.debug(f"GeckoTerminal GET error: {e}")
        return None


def _normalise_pair(raw: dict, chain_slug: str) -> Optional[dict]:
    """
    Convert a GeckoTerminal pool object into the same dict shape
    that DexScreener returns, so derive_opportunities() works unchanged.
    """
    try:
        attrs  = raw.get('attributes', {})
        rels   = raw.get('relationships', {})

        price_usd = float(attrs.get('base_token_price_usd') or 0)
        liq_usd   = float((attrs.get('reserve_in_usd') or attrs.get('fdv_usd') or 0))
        if price_usd <= 0:
            return None

        # Resolve dex name
        dex_id_raw = (rels.get('dex', {}).get('data', {}).get('id') or '').lower()
        dex_id     = GECKO_DEX_ALIASES.get(dex_id_raw, dex_id_raw.replace('_', '-'))

        # Token info from relationships
        base_token  = rels.get('base_token',  {}).get('data', {})
        quote_token = rels.get('quote_token', {}).get('data', {})

        # GeckoTerminal token IDs look like "bsc_0xabc123" — extract address
        def extract_addr(token_data: dict) -> str:
            tid = token_data.get('id', '')
            parts = tid.split('_')
            return parts[-1].lower() if parts else ''

        base_addr  = extract_addr(base_token)
        quote_addr = extract_addr(quote_token)

        # Symbols from attributes — pool name looks like "WETH / USDC" or "WETH/USDC"
        raw_name  = attrs.get('name', '') or ''
        # Normalise: strip spaces around slash, then split
        name_parts = [p.strip() for p in raw_name.replace(' / ', '/').split('/')]
        base_sym  = (name_parts[0] if len(name_parts) >= 1 else '').upper()
        quote_sym = (name_parts[1] if len(name_parts) >= 2 else '').upper()

        pair_addr = raw.get('id', '').split('_')[-1] if raw.get('id') else ''

        return {
            'chainId':    chain_slug,
            'dexId':      dex_id,
            'pairAddress': pair_addr,
            'baseToken':  {
                'address': base_addr,
                'symbol':  base_sym,
                'name':    base_sym,
            },
            'quoteToken': {
                'address': quote_addr,
                'symbol':  quote_sym,
                'name':    quote_sym,
            },
            'priceUsd':   str(price_usd),
            'liquidity':  {'usd': liq_usd},
            '_source':    'geckoterm',
        }
    except Exception as e:
        logger.debug(f"GeckoTerminal normalise error: {e}")
        return None


def fetch_token_pools_gecko(chain_slug: str, token_address: str, page: int = 1) -> list:
    """
    Fetch pools for a specific token address from GeckoTerminal.
    Returns list of normalised pair dicts.
    """
    url  = f"{BASE_URL}/networks/{chain_slug}/tokens/{token_address}/pools"
    data = _get(url, params={'page': page, 'sort': 'h24_volume_usd_liquidity_desc'})
    if not data or 'data' not in data:
        return []
    return [p for p in (_normalise_pair(r, chain_slug) for r in data['data']) if p]


def fetch_top_pools_gecko(chain_slug: str, page: int = 1) -> list:
    """
    Fetch top pools by volume on a chain.
    Good for discovering new high-volume pools not in our base token list.
    """
    url  = f"{BASE_URL}/networks/{chain_slug}/pools"
    data = _get(url, params={'page': page, 'sort': 'h24_volume_usd_desc'})
    if not data or 'data' not in data:
        return []
    return [p for p in (_normalise_pair(r, chain_slug) for r in data['data']) if p]


def fetch_geckoterm_pairs(
    chain: str,
    base_token_addresses: list,
    max_workers: int = 4,
    delay: float = 0.25,
) -> list:
    """
    Main entry point — name matches the call in dexscreener_scanner.py.
    Fetches pairs for all base tokens in parallel.
    Returns de-duplicated list of normalised pair dicts.

    chain: internal chain name (matches DEXSCREENER_CHAIN in each scanner,
           e.g. 'ethereum', 'arbitrum', 'base', 'bsc', 'solana')
    """
    chain_slug = CHAIN_SLUGS.get(chain)
    if not chain_slug:
        logger.warning(f"GeckoTerminal: no slug for chain '{chain}'")
        return []

    logger.info(f"[GeckoTerminal] Fetching {len(base_token_addresses)} tokens on {chain_slug}…")

    all_pairs = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(fetch_token_pools_gecko, chain_slug, addr): addr
            for addr in base_token_addresses
        }
        for f in as_completed(futures):
            try:
                pairs = f.result()
                all_pairs.extend(pairs)
            except Exception as e:
                logger.debug(f"GeckoTerminal pool fetch error: {e}")
            time.sleep(delay)

    # Also fetch top pools by volume to catch pairs we might have missed
    try:
        top = fetch_top_pools_gecko(chain_slug, page=1)
        all_pairs.extend(top)
    except Exception as e:
        logger.debug(f"GeckoTerminal top pools error: {e}")

    # De-duplicate by pairAddress
    seen    = {}
    unique  = []
    for p in all_pairs:
        key = f"{p.get('chainId','')}-{p.get('pairAddress','')}-{p.get('dexId','')}"
        if key not in seen:
            seen[key] = True
            unique.append(p)

    logger.info(f"[GeckoTerminal] {len(unique)} unique pairs for {chain_slug}")
    return unique
