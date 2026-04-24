"""
ArbPulse — Router Validator
Calls router.getAmountsOut() on-chain to verify a spread is real and executable.
Rejects stale/fake spreads that DexScreener shows but routers won't honour.
"""

import logging
from typing import Optional
from web3 import Web3

logger = logging.getLogger(__name__)

_V2_ROUTER_ABI = [
    {
        "name": "getAmountsOut",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "amountIn",  "type": "uint256"},
            {"name": "path",      "type": "address[]"},
        ],
        "outputs": [
            {"name": "amounts", "type": "uint256[]"},
        ],
    }
]

# Spread must be at least this fraction of the DexScreener spread to count as real.
# e.g. 0.3 means the router must confirm at least 30% of the reported spread.
MIN_CONFIRMED_SPREAD_RATIO = 0.30

# Maximum spread we trust from DexScreener without router confirmation.
# Anything above this (e.g. 5%) is almost certainly stale data.
MAX_UNVERIFIED_SPREAD_PCT = 5.0


def get_router_quote(
    w3: Web3,
    router_address: str,
    amount_in: int,       # in token's smallest unit (wei)
    path: list,           # [token_in_address, token_out_address]
) -> Optional[int]:
    """
    Call router.getAmountsOut() and return the output amount.
    Returns None if the call reverts (pool doesn't exist or has no liquidity).
    """
    try:
        router = w3.eth.contract(
            address=Web3.to_checksum_address(router_address),
            abi=_V2_ROUTER_ABI,
        )
        cs_path = [Web3.to_checksum_address(a) for a in path]
        amounts = router.functions.getAmountsOut(amount_in, cs_path).call()
        return amounts[-1]
    except Exception as e:
        logger.debug(f"getAmountsOut revert — router={router_address} path={path}: {e}")
        return None


def check_path_validity(
    w3: Web3,
    router_address: str,
    token_in: str,
    token_out: str,
    amount_in_usd: float,
    token_in_price_usd: float,
) -> tuple:
    """
    Verify that a swap path actually resolves on the router.
    Returns (valid: bool, amount_out_raw: int or 0).
    """
    if token_in_price_usd <= 0:
        return False, 0

    # Use a small test amount (1/10 of loan) to avoid price impact skewing result
    test_usd   = min(amount_in_usd * 0.1, 500.0)
    amount_in  = int((test_usd / token_in_price_usd) * 1e18)
    if amount_in == 0:
        return False, 0

    out = get_router_quote(w3, router_address, amount_in, [token_in, token_out])
    if out is None or out == 0:
        return False, 0
    return True, out


def validate_buy_route(
    w3: Web3,
    buy_router_address: str,
    base_token_address: str,
    quote_token_address: str,
    loan_amount_usd: float,
    base_price_usd: float,
) -> tuple:
    """
    Validate the buy leg: base_token → quote_token.
    Returns (valid: bool, reason: str, quote_out_raw: int).
    """
    valid, out = check_path_validity(
        w3, buy_router_address,
        base_token_address, quote_token_address,
        loan_amount_usd, base_price_usd,
    )
    if not valid:
        return False, "buy route reverted — pool does not exist or has no liquidity", 0
    return True, "buy route confirmed", out


def validate_sell_route(
    w3: Web3,
    sell_router_address: str,
    quote_token_address: str,
    base_token_address: str,
    quote_amount_raw: int,
) -> tuple:
    """
    Validate the sell leg: quote_token → base_token.
    Returns (valid: bool, reason: str, base_out_raw: int).
    """
    if quote_amount_raw == 0:
        return False, "no quote tokens to sell (buy route returned 0)", 0

    out = get_router_quote(
        w3, sell_router_address,
        quote_amount_raw,
        [quote_token_address, base_token_address],
    )
    if out is None or out == 0:
        return False, "sell route reverted — pool does not exist or has no liquidity", 0
    return True, "sell route confirmed", out


def verify_router_execution(
    w3: Web3,
    buy_router:  str,
    sell_router: str,
    base_token:  str,
    quote_token: str,
    loan_amount_usd:   float,
    base_price_usd:    float,
    dexscreener_spread_pct: float,
) -> dict:
    """
    Full round-trip router validation:
      1. Reject if DexScreener spread is unrealistically high
      2. Call getAmountsOut on buy router
      3. Call getAmountsOut on sell router with the buy output
      4. Compute the router-confirmed spread
      5. Reject if confirmed spread < MIN_CONFIRMED_SPREAD_RATIO × reported spread

    Returns dict with:
      valid           : bool
      status          : str   ('verified' | 'candidate' | 'rejected')
      reason          : str
      confirmed_spread: float  (router-confirmed spread %)
    """
    # Gate 1: if spread is very high, skip router verification (it will always
    # fail for stale data) but mark as candidate, not rejected — the user
    # can still attempt execution and the on-chain contract will protect them.
    if dexscreener_spread_pct > MAX_UNVERIFIED_SPREAD_PCT:
        return {
            'valid':            False,
            'status':           'candidate',
            'reason':           f'spread {dexscreener_spread_pct:.2f}% above {MAX_UNVERIFIED_SPREAD_PCT}% — skipping router check, marked as candidate',
            'confirmed_spread': 0.0,
        }

    # Gate 2: buy route
    buy_ok, buy_reason, quote_out = validate_buy_route(
        w3, buy_router, base_token, quote_token, loan_amount_usd, base_price_usd
    )
    if not buy_ok:
        return {'valid': False, 'status': 'rejected', 'reason': buy_reason, 'confirmed_spread': 0.0}

    # Gate 3: sell route
    sell_ok, sell_reason, base_out = validate_sell_route(
        w3, sell_router, quote_token, base_token, quote_out
    )
    if not sell_ok:
        return {'valid': False, 'status': 'rejected', 'reason': sell_reason, 'confirmed_spread': 0.0}

    # Gate 4: compute confirmed spread
    # test_amount_in is 10% of loan in token units
    test_usd      = min(loan_amount_usd * 0.1, 500.0)
    amount_in_raw = int((test_usd / max(base_price_usd, 1e-9)) * 1e18)

    if amount_in_raw == 0:
        confirmed_spread = 0.0
    else:
        # base_out is in same units as amount_in_raw
        confirmed_spread = ((base_out - amount_in_raw) / amount_in_raw) * 100.0

    # Gate 5: confirmed spread must be a meaningful fraction of reported spread
    min_required = dexscreener_spread_pct * MIN_CONFIRMED_SPREAD_RATIO
    if confirmed_spread < min_required:
        return {
            'valid':            False,
            'status':           'candidate',
            'reason':           f'router confirms only {confirmed_spread:.3f}% vs {dexscreener_spread_pct:.3f}% reported — marked as candidate',
            'confirmed_spread': round(confirmed_spread, 4),
        }

    return {
        'valid':            True,
        'status':           'verified',
        'reason':           f'router confirmed {confirmed_spread:.3f}% spread',
        'confirmed_spread': round(confirmed_spread, 4),
    }
