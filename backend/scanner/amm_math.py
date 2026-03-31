"""
AMM Mathematics — Fixed Trade Size Optimizer
Key fix: separate price impact cap (for optimizer) from execution slippage (for contract).
The optimizer now searches up to 5% price impact and starts from the minimum loan
that actually covers gas costs, not from an arbitrary tiny fraction of the pool.
"""

import math


def get_amount_out_v2(amount_in: int, reserve_in: int, reserve_out: int, fee_bps: int = 25) -> int:
    """Uniswap V2 getAmountOut."""
    if amount_in <= 0 or reserve_in <= 0 or reserve_out <= 0:
        return 0
    fee_num = 10000 - fee_bps
    amount_with_fee = amount_in * fee_num
    return (amount_with_fee * reserve_out) // (reserve_in * 10000 + amount_with_fee)


def get_amount_in_v2(amount_out: int, reserve_in: int, reserve_out: int, fee_bps: int = 25) -> int:
    """Uniswap V2 getAmountIn."""
    if amount_out <= 0 or reserve_in <= 0 or reserve_out <= 0 or amount_out >= reserve_out:
        return 0
    fee_num = 10000 - fee_bps
    return (reserve_in * amount_out * 10000) // ((reserve_out - amount_out) * fee_num) + 1


def calc_price_impact(amount_in: int, reserve_in: int) -> float:
    if reserve_in <= 0:
        return 100.0
    return (amount_in / (reserve_in + amount_in)) * 100


def estimate_gas_cost_usd(
    gas_units: int = 600_000,
    gas_price_gwei: float = 3.0,
    bnb_price_usd: float = 600.0,
) -> float:
    return (gas_units * gas_price_gwei * 1e-9) * bnb_price_usd


def find_optimal_trade_size(
    reserve_buy_in: int,
    reserve_buy_out: int,
    reserve_sell_in: int,
    reserve_sell_out: int,
    fee_buy_bps: int,
    fee_sell_bps: int,
    flash_fee_bps: int,
    max_price_impact_pct: float = 5.0,   # optimizer cap — NOT execution slippage
    decimals_base: int = 18,
    gas_usd: float = 0.0,               # gas cost in USD (used to set minimum loan floor)
    base_price_usd: float = 1.0,        # price of base token in USD
) -> dict:
    """
    Find the loan size that maximises net profit (post flash-fee, pre gas).

    Two-stage approach:
      Stage 1 — Compute minimum loan that could possibly cover gas:
                 min_loan_tokens = gas_usd / (max_achievable_net_pct / 100)
      Stage 2 — Binary search between min_loan and max_loan (5% price impact)
                 to find the peak of the profit curve.

    The slippage_tolerance the user sets in the UI is used as the execution
    guard in the smart contract (minProfit parameter), NOT as the price impact
    cap here. This lets the optimizer find larger, profitable trades.
    """
    EMPTY = {'optimal_amount': 0, 'gross_profit': 0, 'net_profit': 0,
             'profitable': False, 'reason': ''}

    if reserve_buy_in <= 0 or reserve_buy_out <= 0 or reserve_sell_in <= 0 or reserve_sell_out <= 0:
        return {**EMPTY, 'reason': 'zero reserves'}

    # ── Upper bound: 5% price impact on both pools ─────────────────────────
    max_amount = min(
        int(reserve_buy_in  * (max_price_impact_pct / 100)),
        int(reserve_sell_in * (max_price_impact_pct / 100)),
    )
    if max_amount <= 0:
        return {**EMPTY, 'reason': 'max_amount zero'}

    # ── Lower bound: minimum loan that could cover gas ─────────────────────
    # Estimate: best-case net from the spread at a tiny trade size
    tiny = max(1, max_amount // 10000)
    q_tiny   = get_amount_out_v2(tiny, reserve_buy_in,  reserve_buy_out,  fee_buy_bps)
    out_tiny = get_amount_out_v2(q_tiny, reserve_sell_in, reserve_sell_out, fee_sell_bps)
    gross_tiny  = max(0, out_tiny - tiny)
    flash_tiny  = (tiny * flash_fee_bps) // 10000
    net_pct_est = ((gross_tiny - flash_tiny) / tiny * 100) if tiny > 0 else 0

    if net_pct_est <= 0:
        return {**EMPTY, 'reason': 'no positive spread at tiny size'}

    # Minimum loan to beat gas: gas_usd / (net_pct_est / 100) in USD → convert to tokens
    if gas_usd > 0 and base_price_usd > 0:
        min_loan_usd    = gas_usd / (net_pct_est / 100)
        min_loan_tokens = int((min_loan_usd / base_price_usd) * (10 ** decimals_base))
        lo = max(tiny, min(min_loan_tokens, max_amount // 2))
    else:
        lo = max(1, max_amount // 1000)

    hi   = max_amount
    best = {**EMPTY}

    # ── Binary search for peak of profit curve ─────────────────────────────
    # The profit curve is unimodal (rises then falls due to price impact),
    # so binary search on the derivative converges to the peak.
    for _ in range(80):
        if lo >= hi:
            break
        mid = (lo + hi) // 2

        q   = get_amount_out_v2(mid, reserve_buy_in,  reserve_buy_out,  fee_buy_bps)
        out = get_amount_out_v2(q,   reserve_sell_in, reserve_sell_out, fee_sell_bps)
        if q <= 0 or out <= 0:
            hi = mid
            continue

        gross  = out - mid
        flash  = (mid * flash_fee_bps) // 10000
        net    = gross - flash

        # Also evaluate mid+1 to determine slope direction
        mid2   = mid + max(1, mid // 1000)
        q2     = get_amount_out_v2(mid2, reserve_buy_in,  reserve_buy_out,  fee_buy_bps)
        out2   = get_amount_out_v2(q2,   reserve_sell_in, reserve_sell_out, fee_sell_bps)
        gross2 = out2 - mid2
        flash2 = (mid2 * flash_fee_bps) // 10000
        net2   = gross2 - flash2

        if net > best.get('net_profit', -1):
            best = {
                'optimal_amount':    mid,
                'quote_amount':      q,
                'gross_profit':      gross,
                'flash_fee':         flash,
                'net_profit':        net,
                'net_profit_pct':    (net / mid * 100) if mid > 0 else 0,
                'buy_price_impact':  calc_price_impact(mid, reserve_buy_in),
                'sell_price_impact': calc_price_impact(q, reserve_sell_in),
                'profitable':        net > 0,
                'reason':            '',
            }

        # Move toward the peak
        if net2 > net:
            lo = mid + 1   # profit still increasing, go right
        else:
            hi = mid       # profit decreasing, go left

    if best['optimal_amount'] == 0:
        return {**EMPTY, 'reason': 'binary search found no improvement'}

    return best


def spread_percentage(buy_price: float, sell_price: float) -> float:
    if buy_price <= 0:
        return 0
    return ((sell_price - buy_price) / buy_price) * 100
