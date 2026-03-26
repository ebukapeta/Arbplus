"""
AMM Mathematics
Handles price calculation, price impact, and optimal trade size for Uniswap V2 style AMMs.
"""

import math
from decimal import Decimal


def get_amount_out_v2(amount_in: int, reserve_in: int, reserve_out: int, fee_bps: int = 25) -> int:
    """
    Uniswap V2 style getAmountOut.
    fee_bps: fee in basis points (e.g. 25 = 0.25%)
    Returns amount out given amount in and reserves.
    """
    if amount_in <= 0 or reserve_in <= 0 or reserve_out <= 0:
        return 0
    fee_numerator = 10000 - fee_bps
    amount_in_with_fee = amount_in * fee_numerator
    numerator = amount_in_with_fee * reserve_out
    denominator = reserve_in * 10000 + amount_in_with_fee
    return numerator // denominator


def get_amount_in_v2(amount_out: int, reserve_in: int, reserve_out: int, fee_bps: int = 25) -> int:
    """
    Uniswap V2 style getAmountIn.
    Returns amount in required to get a specific amount out.
    """
    if amount_out <= 0 or reserve_in <= 0 or reserve_out <= 0 or amount_out >= reserve_out:
        return 0
    fee_numerator = 10000 - fee_bps
    numerator = reserve_in * amount_out * 10000
    denominator = (reserve_out - amount_out) * fee_numerator
    return (numerator // denominator) + 1


def calc_price_impact(amount_in: int, reserve_in: int) -> float:
    """
    Price impact as a percentage of the input relative to the pool.
    """
    if reserve_in <= 0:
        return 100.0
    return (amount_in / (reserve_in + amount_in)) * 100


def calc_spot_price(reserve_in: int, reserve_out: int, decimals_in: int = 18, decimals_out: int = 18) -> float:
    """
    Spot price of token_out denominated in token_in.
    """
    if reserve_in <= 0:
        return 0
    adj_in = reserve_in / (10 ** decimals_in)
    adj_out = reserve_out / (10 ** decimals_out)
    return adj_out / adj_in if adj_in > 0 else 0


def find_optimal_trade_size(
    reserve_buy_in: int,
    reserve_buy_out: int,
    reserve_sell_in: int,
    reserve_sell_out: int,
    fee_buy_bps: int,
    fee_sell_bps: int,
    flash_fee_bps: int,
    max_price_impact_pct: float = 2.0,
    decimals_base: int = 18,
) -> dict:
    """
    Find the trade size that maximises net profit via binary search.
    
    Strategy:
      1. Borrow `base_token` via flash loan
      2. Buy `quote_token` on DEX A (buy_reserve_in = base, buy_reserve_out = quote)
      3. Sell `quote_token` on DEX B (sell_reserve_in = quote, sell_reserve_out = base)
      4. Repay flash loan
      5. Keep difference as profit
    
    Returns dict with optimal amount and profit breakdown.
    """
    # Cap trade size by max price impact on both pools
    max_by_buy_impact = int(reserve_buy_in * (max_price_impact_pct / 100))
    max_by_sell_impact = int(reserve_sell_in * (max_price_impact_pct / 100))
    max_amount = min(max_by_buy_impact, max_by_sell_impact)

    if max_amount <= 0:
        return {'optimal_amount': 0, 'gross_profit': 0, 'net_profit': 0, 'profitable': False}

    # Binary search for optimal trade size
    lo = max_amount // 1000  # start at 0.1% of max
    hi = max_amount
    best = {'optimal_amount': 0, 'gross_profit': 0, 'net_profit': 0, 'profitable': False}

    for _ in range(60):  # 60 iterations gives sub-percent precision
        if lo >= hi:
            break
        mid = (lo + hi) // 2

        # Step through the arbitrage
        quote_received = get_amount_out_v2(mid, reserve_buy_in, reserve_buy_out, fee_buy_bps)
        if quote_received <= 0:
            hi = mid
            continue

        base_received = get_amount_out_v2(quote_received, reserve_sell_in, reserve_sell_out, fee_sell_bps)
        if base_received <= 0:
            hi = mid
            continue

        gross_profit = base_received - mid
        flash_fee = (mid * flash_fee_bps) // 10000
        net_profit = gross_profit - flash_fee

        if net_profit > best['net_profit']:
            best = {
                'optimal_amount': mid,
                'quote_amount': quote_received,
                'gross_profit': gross_profit,
                'flash_fee': flash_fee,
                'net_profit': net_profit,
                'net_profit_pct': (net_profit / mid * 100) if mid > 0 else 0,
                'buy_price_impact': calc_price_impact(mid, reserve_buy_in),
                'sell_price_impact': calc_price_impact(quote_received, reserve_sell_in),
                'profitable': net_profit > 0,
            }
            lo = mid + 1
        else:
            hi = mid

    return best


def calc_net_profit_usd(
    net_profit_raw: int,
    decimals: int,
    token_price_usd: float,
) -> float:
    """Convert raw net profit (in wei/lamports) to USD value."""
    return (net_profit_raw / (10 ** decimals)) * token_price_usd


def calc_dex_fee_usd(
    amount_in_raw: int,
    decimals: int,
    token_price_usd: float,
    fee_bps: int,
) -> float:
    """Calculate DEX fee in USD for a given trade amount."""
    amount_usd = (amount_in_raw / (10 ** decimals)) * token_price_usd
    return amount_usd * (fee_bps / 10000)


def estimate_gas_cost_usd(gas_units: int = 600_000, gas_price_gwei: float = 3.0, bnb_price_usd: float = 600.0) -> float:
    """Estimate BSC gas cost in USD for a flash loan arbitrage transaction."""
    cost_bnb = (gas_units * gas_price_gwei * 1e-9)
    return cost_bnb * bnb_price_usd


def spread_percentage(buy_price: float, sell_price: float) -> float:
    """Calculate spread percentage between two prices."""
    if buy_price <= 0:
        return 0
    return ((sell_price - buy_price) / buy_price) * 100
