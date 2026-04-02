"""
AMM Mathematics — Gas-floor aware optimizer.
Key fix: compute minimum viable loan (min that could cover gas) before sampling.
Only samples loan sizes that are large enough to potentially profit after gas.
"""


def get_amount_out_v2(
    amount_in: int, reserve_in: int, reserve_out: int, fee_bps: int = 25
) -> int:
    if amount_in <= 0 or reserve_in <= 0 or reserve_out <= 0:
        return 0
    fee_num = 10000 - fee_bps
    num = amount_in * fee_num * reserve_out
    den = reserve_in * 10000 + amount_in * fee_num
    return num // den


def get_amount_in_v2(
    amount_out: int, reserve_in: int, reserve_out: int, fee_bps: int = 25
) -> int:
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
    Find the loan size that maximises net profit.

    Step 0: Check if a profitable loan can even exist.
      net_spread = spot_spread - total_fee_pct
      If net_spread <= 0, no loan size can profit — return immediately.
      If net_spread > 0, minimum gas-covering loan = gas_usd / net_spread.

    Step 1: Sample 40 points log-spaced from min_loan to max_loan (5% impact).

    Step 2: Refine around the best sample with 30 linear steps.
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

    # ── Step 0: Quick spread check — is a profitable loan mathematically possible? ──
    buy_spot  = reserve_buy_out  / reserve_buy_in   # quote per base on buy DEX
    sell_spot = reserve_sell_in  / reserve_sell_out  # quote per base on sell DEX (= r_quote/r_base)

    if buy_spot <= 0 or sell_spot <= 0:
        return {**EMPTY, 'reason': 'invalid spot prices'}

    gross_spread_pct = ((buy_spot - sell_spot) / sell_spot) * 100
    total_fee_pct    = (flash_fee_bps + fee_buy_bps + fee_sell_bps) / 100
    net_spread_pct   = gross_spread_pct - total_fee_pct

    if gross_spread_pct <= 0:
        return {**EMPTY, 'reason': f'no spread (buy_spot={buy_spot:.6f} <= sell_spot={sell_spot:.6f})'}

    # ── Step 0b: Compute min loan needed to cover gas ──────────────────────
    # At small sizes (ignoring price impact): net_profit_usd ≈ loan_usd × net_spread_pct/100
    # For this to cover gas: loan_usd ≥ gas_usd / (net_spread_pct / 100)
    if net_spread_pct > 0 and gas_usd > 0 and base_price_usd > 0:
        min_loan_usd    = gas_usd / (net_spread_pct / 100)
        min_loan_tokens = int((min_loan_usd / base_price_usd) * (10 ** decimals_base))
    else:
        # net_spread <= 0: can never cover fees, but we still compute for display
        min_loan_tokens = int(reserve_buy_in * 0.001)  # 0.1% as display floor

    # ── Step 0c: Upper bound — 5% price impact ─────────────────────────────
    max_amount = min(
        int(reserve_buy_in   * (max_price_impact_pct / 100)),
        int(reserve_sell_out * (max_price_impact_pct / 100)),
    )
    if max_amount <= 0:
        return {**EMPTY, 'reason': 'pools too small for 5% impact trade'}

    # If min_loan > max_amount: the required loan would exceed pool capacity
    if min_loan_tokens > max_amount:
        required_usd    = min_loan_tokens / (10 ** decimals_base) * base_price_usd
        available_usd   = max_amount      / (10 ** decimals_base) * base_price_usd
        return {
            **EMPTY,
            'optimal_amount': max_amount,  # show max possible for display
            'reason': (
                f'need ${required_usd:.0f} loan to cover gas but pool only supports '
                f'${available_usd:.0f} at 5% impact'
            ),
        }

    # Clamp min_loan to at least 0.01% of pool
    lo = max(min_loan_tokens, max(1, max_amount // 10_000))
    hi = max_amount

    if lo >= hi:
        lo = max(1, hi // 100)

    # ── Step 1: Geometric sampling ─────────────────────────────────────────
    SAMPLES = 40
    if hi <= lo:
        amounts = [lo]
    else:
        ratio   = (hi / lo) ** (1.0 / (SAMPLES - 1))
        amounts = sorted(set(int(lo * (ratio ** i)) for i in range(SAMPLES)))

    best_net = -(10 ** 30)
    best_idx = 0

    def net_at(amt):
        q   = get_amount_out_v2(amt, reserve_buy_in,  reserve_buy_out,  fee_buy_bps)
        out = get_amount_out_v2(q,   reserve_sell_in, reserve_sell_out, fee_sell_bps)
        if q <= 0 or out <= 0:
            return -(10 ** 30)
        return (out - amt) - (amt * flash_fee_bps) // 10000

    nets = [net_at(a) for a in amounts]
    for i, n in enumerate(nets):
        if n > best_net:
            best_net = n
            best_idx = i

    # ── Step 2: Refine around best ─────────────────────────────────────────
    refine_lo = amounts[max(0, best_idx - 1)]
    refine_hi = amounts[min(len(amounts) - 1, best_idx + 1)]
    STEPS     = 30
    step      = max(1, (refine_hi - refine_lo) // STEPS)

    best_amount  = amounts[best_idx]
    best_net_ref = best_net

    for amt in range(refine_lo, refine_hi + step, step):
        n = net_at(amt)
        if n > best_net_ref:
            best_net_ref = n
            best_amount  = amt

    # ── Step 3: Full result at optimal amount ──────────────────────────────
    q   = get_amount_out_v2(best_amount, reserve_buy_in,  reserve_buy_out,  fee_buy_bps)
    out = get_amount_out_v2(q,           reserve_sell_in, reserve_sell_out, fee_sell_bps)

    if q <= 0 or out <= 0:
        return {**EMPTY, 'optimal_amount': best_amount, 'reason': 'AMM returned zero at optimal amount'}

    gross = out - best_amount
    flash = (best_amount * flash_fee_bps) // 10000
    net   = gross - flash

    peak_net_tokens = net  / (10 ** decimals_base)
    peak_net_usd    = peak_net_tokens * base_price_usd

    result = {
        'optimal_amount':    best_amount,
        'quote_amount':      q,
        'gross_profit':      max(0, gross),
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
        result['reason'] = (
            f'spread={gross_spread_pct:.3f}% fee={total_fee_pct:.3f}% '
            f'net_spread={net_spread_pct:.3f}% — fees exceed spread'
        )
        return result

    if gas_usd > 0 and peak_net_usd <= gas_usd:
        result['reason'] = (
            f'peak net ${peak_net_usd:.4f} < gas ${gas_usd:.4f} '
            f'(loan=${best_amount/(10**decimals_base)*base_price_usd:.0f}, '
            f'need {gas_usd/peak_net_usd:.1f}x larger spread/pool)'
        )
        return result

    result['profitable'] = True
    return result


def spread_percentage(buy_price: float, sell_price: float) -> float:
    if buy_price <= 0:
        return 0
    return ((sell_price - buy_price) / buy_price) * 100
