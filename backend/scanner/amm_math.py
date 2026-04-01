"""
AMM Mathematics — Sampling-based trade size optimizer.
Replaces binary search (which was silently failing) with geometric sampling:
  Step 1: sample 40 loan sizes log-spaced from tiny to 5% impact
  Step 2: find which sample has highest net profit
  Step 3: refine with 20 steps around that sample
This is simpler, more reliable, and easier to debug.
"""


def get_amount_out_v2(
    amount_in: int, reserve_in: int, reserve_out: int, fee_bps: int = 25
) -> int:
    """Uniswap V2 getAmountOut."""
    if amount_in <= 0 or reserve_in <= 0 or reserve_out <= 0:
        return 0
    fee_num = 10000 - fee_bps
    num = amount_in * fee_num * reserve_out
    den = reserve_in * 10000 + amount_in * fee_num
    return num // den


def get_amount_in_v2(
    amount_out: int, reserve_in: int, reserve_out: int, fee_bps: int = 25
) -> int:
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
    gas_units: int = 350_000,
    gas_price_gwei: float = 1.5,
    bnb_price_usd: float = 600.0,
) -> float:
    return (gas_units * gas_price_gwei * 1e-9) * bnb_price_usd


def _net_at(
    amount: int,
    reserve_buy_in: int, reserve_buy_out: int, fee_buy_bps: int,
    reserve_sell_in: int, reserve_sell_out: int, fee_sell_bps: int,
    flash_fee_bps: int,
) -> int:
    """Return net profit (in wei) for a given loan amount. Can be negative."""
    q   = get_amount_out_v2(amount, reserve_buy_in,  reserve_buy_out,  fee_buy_bps)
    out = get_amount_out_v2(q,      reserve_sell_in, reserve_sell_out, fee_sell_bps)
    if q <= 0 or out <= 0:
        return -(10 ** 30)   # sentinel: impossible
    gross = out - amount
    flash = (amount * flash_fee_bps) // 10000
    return gross - flash


def find_optimal_trade_size(
    reserve_buy_in: int,
    reserve_buy_out: int,
    reserve_sell_in: int,
    reserve_sell_out: int,
    fee_buy_bps: int,
    fee_sell_bps: int,
    flash_fee_bps: int,
    max_price_impact_pct: float = 5.0,
    decimals_base: int = 18,
    gas_usd: float = 0.0,
    base_price_usd: float = 1.0,
) -> dict:
    """
    Find the loan size that maximises net profit using geometric sampling.

    Samples 40 points log-spaced between the minimum (0.001% of pool) and
    maximum (5% price impact), finds the best, then refines with 20 linear
    steps around that best point.
    """
    EMPTY = {
        'optimal_amount': 0, 'gross_profit': 0, 'net_profit': 0,
        'profitable': False, 'peak_net_usd': 0.0,
        'buy_price_impact': 0.0, 'sell_price_impact': 0.0,
        'reason': '',
    }

    if (reserve_buy_in <= 0 or reserve_buy_out <= 0
            or reserve_sell_in <= 0 or reserve_sell_out <= 0):
        return {**EMPTY, 'reason': 'zero reserves'}

    # Upper bound: 5% of the smaller pool
    max_amount = min(
        int(reserve_buy_in   * (max_price_impact_pct / 100)),
        int(reserve_sell_out * (max_price_impact_pct / 100)),
    )
    # Lower bound: 0.001% of pool (tiny but nonzero)
    min_amount = max(1, max_amount // 100_000)

    if max_amount <= min_amount:
        return {**EMPTY, 'reason': 'pool too small for meaningful trade'}

    # ── Step 1: Geometric sampling over the full range ────────────────────
    SAMPLES = 40
    ratio = (max_amount / min_amount) ** (1.0 / (SAMPLES - 1))
    amounts = [int(min_amount * (ratio ** i)) for i in range(SAMPLES)]
    amounts = sorted(set(amounts))   # deduplicate after int conversion

    best_net   = -(10 ** 30)
    best_idx   = 0
    nets       = []

    for i, amt in enumerate(amounts):
        n = _net_at(amt,
                    reserve_buy_in, reserve_buy_out, fee_buy_bps,
                    reserve_sell_in, reserve_sell_out, fee_sell_bps,
                    flash_fee_bps)
        nets.append(n)
        if n > best_net:
            best_net = n
            best_idx = i

    # ── Step 2: Refine around the best sample ─────────────────────────────
    lo = amounts[max(0, best_idx - 1)]
    hi = amounts[min(len(amounts) - 1, best_idx + 1)]
    REFINE = 20
    step = max(1, (hi - lo) // REFINE)

    best_amount = amounts[best_idx]
    best_final_net = best_net

    for amt in range(lo, hi + step, step):
        n = _net_at(amt,
                    reserve_buy_in, reserve_buy_out, fee_buy_bps,
                    reserve_sell_in, reserve_sell_out, fee_sell_bps,
                    flash_fee_bps)
        if n > best_final_net:
            best_final_net = n
            best_amount = amt

    # ── Step 3: Compute full result at optimal amount ─────────────────────
    q   = get_amount_out_v2(best_amount, reserve_buy_in,  reserve_buy_out,  fee_buy_bps)
    out = get_amount_out_v2(q,           reserve_sell_in, reserve_sell_out, fee_sell_bps)

    if q <= 0 or out <= 0:
        return {**EMPTY, 'reason': 'AMM returned zero at optimal amount'}

    gross = out - best_amount
    flash = (best_amount * flash_fee_bps) // 10000
    net   = gross - flash

    peak_net_tokens = net   / (10 ** decimals_base)
    peak_net_usd    = peak_net_tokens * base_price_usd

    result = {
        'optimal_amount':    best_amount,
        'quote_amount':      q,
        'gross_profit':      gross,
        'flash_fee':         flash,
        'net_profit':        net,
        'net_profit_pct':    (net / best_amount * 100) if best_amount > 0 else 0,
        'buy_price_impact':  calc_price_impact(best_amount, reserve_buy_in),
        'sell_price_impact': calc_price_impact(q, reserve_sell_in),
        'peak_net_usd':      round(peak_net_usd, 6),
        'profitable':        False,
        'reason':            '',
    }

    if peak_net_usd <= 0:
        result['reason'] = f'negative net even at optimal size ({peak_net_usd:.6f} USD)'
        return result

    if gas_usd > 0 and peak_net_usd <= gas_usd:
        result['reason'] = (
            f'peak net ${peak_net_usd:.4f} < gas ${gas_usd:.4f} '
            f'(need {gas_usd / peak_net_usd:.1f}x larger pool/spread)'
        )
        return result

    result['profitable'] = True
    return result


def spread_percentage(buy_price: float, sell_price: float) -> float:
    if buy_price <= 0:
        return 0
    return ((sell_price - buy_price) / buy_price) * 100
