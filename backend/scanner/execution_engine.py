"""
ArbPulse — Execution Engine
Separates candidate opportunities from verified ones.
Builds the final smart contract execution payload.
"""

import time, logging
from typing import Optional
from web3 import Web3

logger = logging.getLogger(__name__)

# ── Opportunity statuses ──────────────────────────────────────────────────────
STATUS_CANDIDATE      = 'candidate'      # DexScreener says profitable, not yet verified
STATUS_VERIFIED       = 'verified'       # Reserves + router confirmed
STATUS_EXECUTION_READY= 'profitable'     # Flash loan size verified, ready to execute
STATUS_REJECTED       = 'rejected'       # Failed validation — do not show
STATUS_MARGINAL       = 'marginal'       # Profitable but below min threshold


def mark_candidate(opp: dict) -> dict:
    """Mark as candidate — DexScreener profitable but not yet on-chain verified."""
    opp['executionStatus'] = STATUS_CANDIDATE
    opp['status']          = STATUS_CANDIDATE
    return opp


def mark_verified(opp: dict, confirmed_spread: float = 0.0) -> dict:
    """Mark as verified — reserves and router both confirmed."""
    opp['executionStatus']   = STATUS_VERIFIED
    opp['confirmedSpread']   = confirmed_spread
    return opp


def mark_execution_ready(opp: dict) -> dict:
    """Mark as execution ready — all checks passed."""
    opp['executionStatus'] = STATUS_EXECUTION_READY
    opp['status']          = STATUS_EXECUTION_READY
    return opp


def mark_rejected(opp: dict, reason: str) -> dict:
    """Mark as rejected with a reason."""
    opp['executionStatus']    = STATUS_REJECTED
    opp['status']             = STATUS_REJECTED
    opp['rejectionReason']    = reason
    return opp


def verify_flashloan_size_limits(
    opp: dict,
    flash_providers: list,
) -> tuple:
    """
    Check the loan amount does not exceed what the flash loan provider can supply.
    Returns (ok: bool, reason: str).
    Most providers have soft limits — we use a conservative cap.
    """
    loan_usd = opp.get('flashLoanAmountUsd', 0)
    provider_name = opp.get('flashLoanProvider', '')

    # Conservative per-provider caps (USD)
    caps = {
        'DODO Flash':            500_000,
        'PancakeSwap V3 Flash':  2_000_000,
        'Aave V3 BSC':           50_000_000,
        'Balancer V2 Flash':     100_000_000,
        'Uniswap V3 Flash':      10_000_000,
        'Aave V3 ETH':           50_000_000,
        'Aave V3 Arb':           50_000_000,
        'Balancer V2 Arb':       100_000_000,
        'Uniswap V3 Arb Flash':  10_000_000,
        'Balancer V2 Base':      100_000_000,
        'Aave V3 Base':          50_000_000,
        'Uniswap V3 Base Flash': 10_000_000,
        'MarginFi':              5_000_000,
        'Kamino':                5_000_000,
        'Solend':                2_000_000,
    }

    cap = caps.get(provider_name, 1_000_000)
    if loan_usd > cap:
        return False, f'loan ${loan_usd:,.0f} exceeds {provider_name} cap of ${cap:,.0f}'

    # Minimum loan size check
    if loan_usd < 100:
        return False, f'loan ${loan_usd:.2f} is below $100 minimum'

    return True, 'flash loan size ok'


def calculate_exact_flash_repayment(
    loan_amount_raw: int,   # in token's smallest unit
    fee_bps: int,           # provider fee in basis points
) -> int:
    """
    Calculate the exact repayment amount: principal + fee.
    fee_bps: 0 = DODO/Balancer, 5 = Aave, 9 = Kamino, 30 = Solend
    """
    fee = (loan_amount_raw * fee_bps) // 10_000
    return loan_amount_raw + fee


def verify_flashloan_provider_support(
    opp: dict,
    flash_providers: list,
) -> tuple:
    """
    Confirm the selected provider actually supports the flash loan asset.
    Returns (ok: bool, provider: dict, reason: str).
    """
    base_token = opp.get('baseToken', '').upper()

    for provider in flash_providers:
        supported = provider.get('assets', [])
        if not supported or base_token in supported:
            return True, provider, f"{provider['name']} supports {base_token}"

    return False, {}, f"no flash provider supports {base_token} on this chain"


def prepare_execution_payload(
    opp: dict,
    buy_router_address:  str,
    sell_router_address: str,
    provider_type:       int,    # 0/1/2 per chain contract
    wallet_address:      str,
    deadline_seconds:    int = 1200,
) -> Optional[dict]:
    """
    Build the final payload dict that maps to the smart contract's
    executeArbitrage() parameters.
    """
    base_addr  = opp.get('baseTokenAddress', '')
    quote_addr = opp.get('quoteTokenAddress', '')
    loan_amt   = opp.get('flashLoanAmount', 0)

    if not base_addr or not quote_addr or loan_amt <= 0:
        logger.warning("prepare_execution_payload: missing addresses or loan amount")
        return None

    loan_raw   = int(loan_amt * 1e18)
    min_profit = int(opp.get('netProfit', 0) * 0.85 * 1e18)  # 15% slippage buffer
    deadline   = int(time.time()) + deadline_seconds

    return {
        'flashLoanAsset':   base_addr,
        'flashLoanAmount':  loan_raw,
        'buyDex':           buy_router_address,
        'sellDex':          sell_router_address,
        'buyPath':          [base_addr, quote_addr],
        'sellPath':         [quote_addr, base_addr],
        'minProfit':        min_profit,
        'deadline':         deadline,
        'provider':         provider_type,
        'walletAddress':    wallet_address,
    }


def build_contract_call_data(
    w3: Web3,
    contract_address: str,
    contract_abi: list,
    payload: dict,
    gas_limit: int = 500_000,
) -> Optional[dict]:
    """
    Build the raw unsigned transaction for the smart contract call.
    Returns the unsigned tx dict ready for MetaMask signing.
    """
    try:
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=contract_abi,
        )
        wallet = Web3.to_checksum_address(payload['walletAddress'])

        tx = contract.functions.executeArbitrage(
            Web3.to_checksum_address(payload['flashLoanAsset']),
            payload['flashLoanAmount'],
            Web3.to_checksum_address(payload['buyDex']),
            Web3.to_checksum_address(payload['sellDex']),
            [Web3.to_checksum_address(a) for a in payload['buyPath']],
            [Web3.to_checksum_address(a) for a in payload['sellPath']],
            payload['minProfit'],
            payload['deadline'],
            payload['provider'],
        ).build_transaction({
            'from':     wallet,
            'gas':      gas_limit,
            'gasPrice': max(w3.eth.gas_price, 3_000_000_000),  # min 3 gwei
            'nonce':    w3.eth.get_transaction_count(wallet),
        })

        return {
            'to':       tx['to'],
            'data':     tx['data'],
            'gas':      hex(tx['gas']),
            'gasPrice': hex(tx['gasPrice']),
            'nonce':    hex(tx['nonce']),
            'value':    '0x0',
        }
    except Exception as e:
        logger.error(f"build_contract_call_data error: {e}")
        return None
