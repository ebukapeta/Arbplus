"""
ArbPulse — Reserve Fetcher
Fetches real on-chain reserves to detect stale, dead, or fake liquidity pools.
Works for Uniswap V2-style (getReserves) and V3-style (slot0 + liquidity) pools.
"""

import time, logging
from typing import Optional
from web3 import Web3

logger = logging.getLogger(__name__)

# ── ABIs ─────────────────────────────────────────────────────────────────────

_V2_PAIR_ABI = [
    {"name": "getReserves", "type": "function", "stateMutability": "view",
     "inputs": [],
     "outputs": [
         {"name": "_reserve0", "type": "uint112"},
         {"name": "_reserve1", "type": "uint112"},
         {"name": "_blockTimestampLast", "type": "uint32"},
     ]},
    {"name": "token0", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "address"}]},
    {"name": "token1", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "address"}]},
]

_V3_POOL_ABI = [
    {"name": "slot0", "type": "function", "stateMutability": "view",
     "inputs": [],
     "outputs": [
         {"name": "sqrtPriceX96",   "type": "uint160"},
         {"name": "tick",           "type": "int24"},
         {"name": "observationIndex","type": "uint16"},
         {"name": "observationCardinality","type": "uint16"},
         {"name": "observationCardinalityNext","type": "uint16"},
         {"name": "feeProtocol",    "type": "uint8"},
         {"name": "unlocked",       "type": "bool"},
     ]},
    {"name": "liquidity", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "uint128"}]},
]

# ── Max reserve age: if the pool's blockTimestampLast is older than this,
#    treat the pool as stale.
MAX_RESERVE_AGE_SECONDS = 300  # 5 minutes


def get_v2_real_reserves(
    w3: Web3,
    pair_address: str,
    timeout: int = 5,
) -> Optional[dict]:
    """
    Fetch live reserves from a Uniswap V2-style pair contract.
    Returns dict with reserve0, reserve1, token0, token1, age_seconds
    or None if the call fails.
    """
    try:
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(pair_address),
            abi=_V2_PAIR_ABI,
        )
        reserves = contract.functions.getReserves().call()
        token0   = contract.functions.token0().call()
        token1   = contract.functions.token1().call()

        reserve0, reserve1, ts_last = reserves
        age_seconds = int(time.time()) - ts_last

        return {
            'reserve0':    reserve0,
            'reserve1':    reserve1,
            'token0':      token0.lower(),
            'token1':      token1.lower(),
            'ts_last':     ts_last,
            'age_seconds': age_seconds,
        }
    except Exception as e:
        logger.debug(f"get_v2_real_reserves({pair_address}): {e}")
        return None


def get_v3_liquidity_state(
    w3: Web3,
    pool_address: str,
) -> Optional[dict]:
    """
    Fetch slot0 + liquidity from a Uniswap V3-style pool.
    Returns dict with sqrtPriceX96, tick, liquidity, unlocked
    or None if the call fails.
    """
    try:
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(pool_address),
            abi=_V3_POOL_ABI,
        )
        slot0     = contract.functions.slot0().call()
        liquidity = contract.functions.liquidity().call()

        return {
            'sqrtPriceX96': slot0[0],
            'tick':         slot0[1],
            'unlocked':     slot0[6],
            'liquidity':    liquidity,
        }
    except Exception as e:
        logger.debug(f"get_v3_liquidity_state({pool_address}): {e}")
        return None


def verify_reserve_freshness(reserves: dict) -> tuple:
    """
    Check if V2 reserves are valid.
    Returns (is_valid: bool, reason: str).

    NOTE: We do NOT reject based on blockTimestampLast age.
    A pool that hasn't had a swap in the last N minutes is still a valid,
    tradeable pool — it simply hasn't been touched recently.
    blockTimestampLast only reflects the last swap, not pool health.
    The only real dead-pool signals are zero reserves.
    """
    if reserves is None:
        return False, "could not fetch reserves"

    r0 = reserves.get('reserve0', 0)
    r1 = reserves.get('reserve1', 0)

    if r0 == 0 or r1 == 0:
        return False, "zero reserves — pool is empty or drained"

    return True, "reserves valid"


def get_pair_contract_reserves(
    w3: Web3,
    pair_address: str,
    base_token_address: str,
    quote_token_address: str,
    is_v3: bool = False,
) -> dict:
    """
    Unified entry point. Returns a dict with:
      valid        : bool
      reason       : str
      base_reserve : float  (human units, estimated)
      quote_reserve: float  (human units, estimated)
      age_seconds  : int    (V2 only; -1 for V3)
    """
    if not pair_address or len(pair_address) < 10:
        return {'valid': False, 'reason': 'no pool address', 'base_reserve': 0, 'quote_reserve': 0, 'age_seconds': -1}

    if is_v3:
        state = get_v3_liquidity_state(w3, pair_address)
        if state is None:
            return {'valid': False, 'reason': 'V3 slot0 call failed', 'base_reserve': 0, 'quote_reserve': 0, 'age_seconds': -1}
        if state['liquidity'] == 0:
            return {'valid': False, 'reason': 'V3 pool has zero liquidity', 'base_reserve': 0, 'quote_reserve': 0, 'age_seconds': -1}
        if not state['unlocked']:
            return {'valid': False, 'reason': 'V3 pool is locked (reentrancy guard)', 'base_reserve': 0, 'quote_reserve': 0, 'age_seconds': -1}
        return {'valid': True, 'reason': 'V3 pool active', 'base_reserve': 0, 'quote_reserve': 0, 'age_seconds': -1}

    # V2 path
    reserves = get_v2_real_reserves(w3, pair_address)
    fresh, reason = verify_reserve_freshness(reserves)
    if not fresh:
        return {'valid': False, 'reason': reason, 'base_reserve': 0, 'quote_reserve': 0, 'age_seconds': reserves.get('age_seconds', -1) if reserves else -1}

    base_addr  = base_token_address.lower()
    token0     = reserves['token0']
    base_reserve  = reserves['reserve0'] if token0 == base_addr else reserves['reserve1']
    quote_reserve = reserves['reserve1'] if token0 == base_addr else reserves['reserve0']

    return {
        'valid':         True,
        'reason':        'fresh',
        'base_reserve':  base_reserve,
        'quote_reserve': quote_reserve,
        'age_seconds':   reserves['age_seconds'],
    }
