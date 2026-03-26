"""
BSC DEX Scanner
Connects to BNB Chain, fetches reserves from multiple DEXes via multicall,
calculates arbitrage opportunities, and handles execution via smart contract.
"""

import os
import json
import time
import logging
import itertools
from typing import Optional
from web3 import Web3
from web3.middleware import geth_poa_middleware

from .token_pairs import TOKENS, DEX_CONFIGS, FLASH_LOAN_PROVIDERS, BASE_TOKEN_PAIRS
from .amm_math import (
    get_amount_out_v2, find_optimal_trade_size,
    calc_price_impact, spread_percentage, estimate_gas_cost_usd
)

logger = logging.getLogger(__name__)

# ─── ABIs ────────────────────────────────────────────────────────────────────
PAIR_ABI = json.loads('[{"constant":true,"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":true,"inputs":[],"name":"token0","outputs":[{"internalType":"address","name":"","type":"address"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":true,"inputs":[],"name":"token1","outputs":[{"internalType":"address","name":"","type":"address"}],"payable":false,"stateMutability":"view","type":"function"}]')

FACTORY_ABI = json.loads('[{"constant":true,"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"}],"name":"getPair","outputs":[{"internalType":"address","name":"pair","type":"address"}],"payable":false,"stateMutability":"view","type":"function"}]')

MULTICALL_ABI = json.loads('[{"inputs":[{"components":[{"internalType":"address","name":"target","type":"address"},{"internalType":"bytes","name":"callData","type":"bytes"}],"internalType":"struct Multicall2.Call[]","name":"calls","type":"tuple[]"}],"name":"tryAggregate","outputs":[{"components":[{"internalType":"bool","name":"success","type":"bool"},{"internalType":"bytes","name":"returnData","type":"bytes"}],"internalType":"struct Multicall2.Result[]","name":"returnData","type":"tuple[]"}],"stateMutability":"nonpayable","type":"function"}]')

FLASH_ARB_ABI = json.loads('[{"inputs":[{"internalType":"address","name":"_flashLoanAsset","type":"address"},{"internalType":"uint256","name":"_flashLoanAmount","type":"uint256"},{"internalType":"address","name":"_buyDex","type":"address"},{"internalType":"address","name":"_sellDex","type":"address"},{"internalType":"address[]","name":"_buyPath","type":"address[]"},{"internalType":"address[]","name":"_sellPath","type":"address[]"},{"internalType":"uint256","name":"_minProfit","type":"uint256"},{"internalType":"uint256","name":"_deadline","type":"uint256"}],"name":"executeArbitrage","outputs":[],"stateMutability":"nonpayable","type":"function"}]')

MULTICALL_ADDRESS = '0xcA11bde05977b3631167028862bE2a173976CA11'

# ─── Price Oracle (rough USD prices for display) ─────────────────────────────
PRICE_ORACLE = {
    'WBNB': 600.0, 'USDT': 1.0, 'USDC': 1.0, 'BTCB': 65000.0,
    'ETH': 3500.0, 'BUSD': 1.0, 'DAI': 1.0, 'CAKE': 2.5,
    'XRP': 0.5, 'ADA': 0.45, 'DOGE': 0.13, 'DOT': 7.5,
    'LINK': 14.0, 'MATIC': 0.7, 'SOL': 150.0, 'AVAX': 35.0,
    'ATOM': 10.0, 'UNI': 9.0, 'LTC': 80.0,
}

TOKEN_DECIMALS = {addr: 18 for addr in TOKENS.values()}
# Stablecoins typically use 18 decimals on BSC
TOKEN_DECIMALS[TOKENS['USDT']] = 18
TOKEN_DECIMALS[TOKENS['USDC']] = 18

NULL_ADDRESS = '0x0000000000000000000000000000000000000000'

BSC_RPC_FALLBACKS = [
    'https://rpc.ankr.com/bsc',
    'https://bsc-rpc.publicnode.com',
    'https://binance.llamarpc.com',
    'https://bsc.meowrpc.com',
    'https://bsc-dataseed.bnbchain.org',
]


class BSCScanner:
    def __init__(self):
        self.w3: Optional[Web3] = None
        self._pair_cache: dict = {}
        self._last_price_update: float = 0
        self._price_cache: dict = {}
        self._connect()

    def _connect(self):
        rpc_url = os.environ.get('BSC_RPC_URL', '')
        candidates = [rpc_url] + BSC_RPC_FALLBACKS if rpc_url else BSC_RPC_FALLBACKS
        for url in candidates:
            try:
                w3 = Web3(Web3.HTTPProvider(url, request_kwargs={'timeout': 10}))
                w3.middleware_onion.inject(geth_poa_middleware, layer=0)
                if w3.is_connected():
                    self.w3 = w3
                    logger.info(f"BSC connected via {url}")
                    return
            except Exception as e:
                logger.warning(f"BSC RPC {url} failed: {e}")
        logger.error("All BSC RPC endpoints failed")

    def _ensure_connected(self):
        if not self.w3 or not self.w3.is_connected():
            self._connect()
        return self.w3 is not None

    def _get_pair_address(self, factory_addr: str, token_a: str, token_b: str) -> str:
        cache_key = f"{factory_addr}:{min(token_a,token_b)}:{max(token_a,token_b)}"
        if cache_key in self._pair_cache:
            return self._pair_cache[cache_key]
        try:
            factory = self.w3.eth.contract(
                address=Web3.to_checksum_address(factory_addr),
                abi=FACTORY_ABI
            )
            pair = factory.functions.getPair(
                Web3.to_checksum_address(token_a),
                Web3.to_checksum_address(token_b)
            ).call()
            self._pair_cache[cache_key] = pair
            return pair
        except Exception as e:
            logger.debug(f"getPair failed {factory_addr}: {e}")
            return NULL_ADDRESS

    def _get_reserves(self, pair_addr: str, token_a: str, token_b: str) -> tuple:
        """Returns (reserveA, reserveB) ordered to match tokenA, tokenB."""
        try:
            pair_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(pair_addr),
                abi=PAIR_ABI
            )
            r0, r1, _ = pair_contract.functions.getReserves().call()
            t0 = pair_contract.functions.token0().call()
            if t0.lower() == token_a.lower():
                return r0, r1
            else:
                return r1, r0
        except Exception as e:
            logger.debug(f"getReserves failed {pair_addr}: {e}")
            return 0, 0

    def _get_bnb_price(self) -> float:
        """Get current BNB price via WBNB/USDT pair on PancakeSwap V2."""
        try:
            factory_addr = DEX_CONFIGS['PancakeSwap V2']['factory']
            pair = self._get_pair_address(factory_addr, TOKENS['WBNB'], TOKENS['USDT'])
            if pair == NULL_ADDRESS:
                return 600.0
            r_bnb, r_usdt = self._get_reserves(pair, TOKENS['WBNB'], TOKENS['USDT'])
            if r_bnb and r_usdt:
                return r_usdt / r_bnb
        except Exception:
            pass
        return 600.0

    def scan(self, config: dict) -> dict:
        """Main scan entry point. Returns all arbitrage opportunities."""
        if not self._ensure_connected():
            return {
                'opportunities': [],
                'total': 0,
                'profitable': 0,
                'best_profit_usd': 0,
                'avg_spread': 0,
                'error': 'Cannot connect to BSC RPC'
            }

        min_net_profit_pct = float(config.get('minNetProfitPct', 0.30))
        min_liquidity_usd = float(config.get('minLiquidityUsd', 25000))
        slippage_tolerance = float(config.get('slippageTolerance', 0.5))
        flash_provider = config.get('flashLoanProvider', 'Aave V3')
        base_tokens = config.get('baseTokens', ['USDT', 'WBNB', 'BTCB', 'USDC'])
        selected_dexes = config.get('dexes', list(DEX_CONFIGS.keys()))

        flash_fee_bps = FLASH_LOAN_PROVIDERS.get(flash_provider, {}).get('fee_bps', 5)
        bnb_price = self._get_bnb_price()
        gas_usd = estimate_gas_cost_usd(bnb_price_usd=bnb_price)

        opportunities = []
        active_dexes = {k: v for k, v in DEX_CONFIGS.items() if k in selected_dexes}

        for base_token in base_tokens:
            if base_token not in TOKENS:
                continue
            base_addr = TOKENS[base_token]
            base_price_usd = PRICE_ORACLE.get(base_token, 1.0)
            base_decimals = TOKEN_DECIMALS.get(base_addr, 18)
            quote_tokens = BASE_TOKEN_PAIRS.get(base_token, [])

            for quote_token in quote_tokens:
                if quote_token not in TOKENS:
                    continue
                quote_addr = TOKENS[quote_token]

                dex_data = {}
                for dex_name, dex_cfg in active_dexes.items():
                    if dex_cfg.get('type') not in ('v2', 'v2_stable'):
                        continue  # V3 requires quoter calls — separate logic
                    pair_addr = self._get_pair_address(dex_cfg['factory'], base_addr, quote_addr)
                    if not pair_addr or pair_addr == NULL_ADDRESS:
                        continue
                    r_base, r_quote = self._get_reserves(pair_addr, base_addr, quote_addr)
                    if r_base == 0 or r_quote == 0:
                        continue
                    liq_usd = (r_base / 10**base_decimals) * base_price_usd * 2
                    if liq_usd < min_liquidity_usd:
                        continue
                    dex_data[dex_name] = {
                        'r_base': r_base,
                        'r_quote': r_quote,
                        'liq_usd': liq_usd,
                        'fee_bps': dex_cfg['fee_bps'],
                        'pair_addr': pair_addr,
                        'router': dex_cfg.get('router', ''),
                    }

                if len(dex_data) < 2:
                    continue

                # Compare all DEX pairs
                dex_names = list(dex_data.keys())
                for buy_dex, sell_dex in itertools.permutations(dex_names, 2):
                    bd = dex_data[buy_dex]
                    sd = dex_data[sell_dex]

                    # Quick spread check before expensive optimal calc
                    buy_spot = bd['r_quote'] / bd['r_base'] if bd['r_base'] > 0 else 0
                    sell_spot = sd['r_quote'] / sd['r_base'] if sd['r_base'] > 0 else 0
                    if buy_spot <= 0 or sell_spot <= 0:
                        continue
                    spread = ((sell_spot - buy_spot) / buy_spot) * 100
                    if spread < min_net_profit_pct * 0.5:  # pre-filter
                        continue

                    result = find_optimal_trade_size(
                        reserve_buy_in=bd['r_base'],
                        reserve_buy_out=bd['r_quote'],
                        reserve_sell_in=sd['r_quote'],
                        reserve_sell_out=sd['r_base'],
                        fee_buy_bps=bd['fee_bps'],
                        fee_sell_bps=sd['fee_bps'],
                        flash_fee_bps=flash_fee_bps,
                        max_price_impact_pct=slippage_tolerance,
                        decimals_base=base_decimals,
                    )

                    if not result['profitable'] or result['optimal_amount'] <= 0:
                        continue

                    gross_profit_tokens = result['gross_profit'] / 10**base_decimals
                    net_profit_tokens = result['net_profit'] / 10**base_decimals
                    loan_tokens = result['optimal_amount'] / 10**base_decimals
                    gross_profit_usd = gross_profit_tokens * base_price_usd
                    net_profit_usd = net_profit_tokens * base_price_usd
                    loan_usd = loan_tokens * base_price_usd

                    # DEX fees (buy + sell)
                    dex_fee_buy_usd = loan_usd * (bd['fee_bps'] / 10000)
                    dex_fee_sell_usd = gross_profit_usd * (sd['fee_bps'] / 10000)
                    total_dex_fees_usd = dex_fee_buy_usd + dex_fee_sell_usd

                    final_net_usd = net_profit_usd - gas_usd
                    if final_net_usd <= 0:
                        continue
                    net_pct = (net_profit_tokens / loan_tokens * 100) if loan_tokens > 0 else 0
                    if net_pct < min_net_profit_pct:
                        continue

                    buy_price = bd['r_base'] / bd['r_quote'] if bd['r_quote'] > 0 else 0
                    sell_price = sd['r_base'] / sd['r_quote'] if sd['r_quote'] > 0 else 0

                    opportunities.append({
                        'id': f"{base_token}_{quote_token}_{buy_dex}_{sell_dex}_{int(time.time())}",
                        'pair': f"{quote_token}/{base_token}",
                        'baseToken': base_token,
                        'quoteToken': quote_token,
                        'baseTokenAddress': base_addr,
                        'quoteTokenAddress': quote_addr,
                        'buyDex': buy_dex,
                        'sellDex': sell_dex,
                        'buyDexRouter': bd['router'],
                        'sellDexRouter': sd['router'],
                        'buyPrice': round(buy_price, 10),
                        'sellPrice': round(sell_price, 10),
                        'spread': round(spread, 4),
                        'flashLoanAsset': base_token,
                        'flashLoanAmount': round(loan_tokens, 6),
                        'flashLoanAmountUsd': round(loan_usd, 2),
                        'flashLoanProvider': flash_provider,
                        'grossProfit': round(gross_profit_tokens, 6),
                        'grossProfitUsd': round(gross_profit_usd, 2),
                        'netProfit': round(net_profit_tokens, 6),
                        'netProfitUsd': round(final_net_usd, 2),
                        'gasFee': round(gas_usd, 2),
                        'dexFees': round(total_dex_fees_usd, 2),
                        'flashFee': round((result['flash_fee'] / 10**base_decimals) * base_price_usd, 2),
                        'netProfitPct': round(net_pct, 4),
                        'buyPoolLiquidity': round(bd['liq_usd'], 0),
                        'sellPoolLiquidity': round(sd['liq_usd'], 0),
                        'buyPriceImpact': round(result.get('buy_price_impact', 0), 4),
                        'sellPriceImpact': round(result.get('sell_price_impact', 0), 4),
                        'status': 'profitable' if final_net_usd > 0 else 'marginal',
                        'timestamp': int(time.time()),
                    })

        # Sort by net profit descending
        opportunities.sort(key=lambda x: x['netProfitUsd'], reverse=True)
        profitable = [o for o in opportunities if o['netProfitUsd'] > 0]
        avg_spread = sum(o['spread'] for o in opportunities) / len(opportunities) if opportunities else 0

        return {
            'opportunities': opportunities,
            'total': len(opportunities),
            'profitable': len(profitable),
            'best_profit_usd': opportunities[0]['netProfitUsd'] if opportunities else 0,
            'avg_spread': round(avg_spread, 4),
            'bnb_price': bnb_price,
            'gas_estimate_usd': round(gas_usd, 2),
            'scan_timestamp': int(time.time()),
        }

    def execute_trade(self, opportunity: dict, wallet_address: str, contract_address: str) -> dict:
        """
        Execute flash loan arbitrage via deployed smart contract.
        Builds and sends the transaction — the wallet must sign via frontend (MetaMask).
        Returns the unsigned transaction for the frontend to sign.
        """
        try:
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(contract_address),
                abi=FLASH_ARB_ABI
            )
            base_addr = Web3.to_checksum_address(opportunity['baseTokenAddress'])
            quote_addr = Web3.to_checksum_address(opportunity['quoteTokenAddress'])
            base_dec = TOKEN_DECIMALS.get(TOKENS.get(opportunity['baseToken'], ''), 18)

            flash_amount = int(opportunity['flashLoanAmount'] * (10 ** base_dec))
            min_profit = int(opportunity['netProfit'] * 0.9 * (10 ** base_dec))  # 10% slippage buffer
            deadline = int(time.time()) + 180  # 3 minutes

            tx = contract.functions.executeArbitrage(
                base_addr,
                flash_amount,
                Web3.to_checksum_address(opportunity['buyDexRouter']),
                Web3.to_checksum_address(opportunity['sellDexRouter']),
                [base_addr, quote_addr],
                [quote_addr, base_addr],
                min_profit,
                deadline,
            ).build_transaction({
                'from': Web3.to_checksum_address(wallet_address),
                'gas': 600000,
                'gasPrice': self.w3.eth.gas_price,
                'nonce': self.w3.eth.get_transaction_count(Web3.to_checksum_address(wallet_address)),
            })

            return {
                'status': 'ready',
                'unsignedTx': {
                    'to': tx['to'],
                    'data': tx['data'],
                    'gas': hex(tx['gas']),
                    'gasPrice': hex(tx['gasPrice']),
                    'nonce': hex(tx['nonce']),
                    'value': '0x0',
                    'chainId': 56,
                }
            }
        except Exception as e:
            logger.error(f"Build tx error: {e}", exc_info=True)
            return {'status': 'error', 'error': str(e)}
