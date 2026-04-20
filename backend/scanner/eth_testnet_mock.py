"""
ArbPulse — Ethereum Sepolia Testnet Mock Scanner

DexScreener has no real Sepolia pair data, so this mock generates synthetic
arbitrage opportunities using:
  - Real Sepolia token addresses
  - Real Sepolia DEX router addresses (Uniswap V2 Sepolia, SushiSwap Sepolia)
  - Real Aave V3 Sepolia flash loan provider
  - Fabricated spreads and prices that change each scan cycle

Purpose: test the full UI → execute → smart contract flow on Sepolia
         without relying on DexScreener testnet data that does not exist.
"""

import time, math, logging
from web3 import Web3
import json

logger = logging.getLogger(__name__)

# ── Real Sepolia addresses ────────────────────────────────────────────────────

SEPOLIA_TOKENS = {
    'WETH': {'address': '0x7b79995e5f793A07Bc00c21d5351694B20Ca3f2d', 'decimals': 18, 'price_usd': 3500.0},
    'USDC': {'address': '0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238', 'decimals': 6,  'price_usd': 1.0},
    'DAI':  {'address': '0xFF34B3d4Aee8ddCd6F9AFFFB6Fe49bD371b8a357', 'decimals': 18, 'price_usd': 1.0},
    'LINK': {'address': '0x779877A7B0D9E8603169DdbD7836e478b4624789', 'decimals': 18, 'price_usd': 15.0},
    'UNI':  {'address': '0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984', 'decimals': 18, 'price_usd': 8.0},
    'USDT': {'address': '0xaA8E23Fb1079EA71e0a56F48a2aA51851D8433D0', 'decimals': 6,  'price_usd': 1.0},
}

SEPOLIA_ROUTERS = {
    'Uniswap V2 Sepolia': '0xeE567Fe1712Faf6149d80dA1E6934E354124CfE3',
    'SushiSwap Sepolia':  '0xeaBcE3E74EF19FB48d55747bf2Eb333B6f47A80a',
}

SEPOLIA_FLASH_PROVIDER = {
    'name': 'Aave V3 Sepolia',
    'pool': '0x6Ae43d3271ff6888e7Fc43Fd7321a503ff738951',
    'fee_bps': 5,  # 0.05%
}

ETH_TESTNET_RPC = [
    'https://rpc.sepolia.org',
    'https://ethereum-sepolia.publicnode.com',
]

FLASH_ARB_ABI = json.loads('[{"inputs":[{"internalType":"address","name":"flashLoanAsset","type":"address"},{"internalType":"uint256","name":"flashLoanAmount","type":"uint256"},{"internalType":"address","name":"buyDex","type":"address"},{"internalType":"address","name":"sellDex","type":"address"},{"internalType":"address[]","name":"buyPath","type":"address[]"},{"internalType":"address[]","name":"sellPath","type":"address[]"},{"internalType":"uint256","name":"minProfit","type":"uint256"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"uint8","name":"provider","type":"uint8"}],"name":"executeArbitrage","outputs":[],"stateMutability":"nonpayable","type":"function"}]')

# ── Synthetic pair templates ───────────────────────────────────────────────────
# Each entry defines a pair and a base spread.
# Prices shift slightly each scan cycle using a time-based oscillator,
# making results look live without being random noise.

_PAIR_TEMPLATES = [
    {
        'base':       'WETH',
        'quote':      'USDC',
        'buy_dex':    'Uniswap V2 Sepolia',
        'sell_dex':   'SushiSwap Sepolia',
        'buy_price':  3498.50,
        'spread_pct': 1.92,
        'liq_buy':    145_000,
        'liq_sell':   98_000,
    },
    {
        'base':       'WETH',
        'quote':      'DAI',
        'buy_dex':    'SushiSwap Sepolia',
        'sell_dex':   'Uniswap V2 Sepolia',
        'buy_price':  3491.00,
        'spread_pct': 1.77,
        'liq_buy':    112_000,
        'liq_sell':   87_000,
    },
    {
        'base':       'LINK',
        'quote':      'USDC',
        'buy_dex':    'Uniswap V2 Sepolia',
        'sell_dex':   'SushiSwap Sepolia',
        'buy_price':  14.82,
        'spread_pct': 2.16,
        'liq_buy':    62_000,
        'liq_sell':   41_000,
    },
    {
        'base':       'UNI',
        'quote':      'WETH',
        'buy_dex':    'SushiSwap Sepolia',
        'sell_dex':   'Uniswap V2 Sepolia',
        'buy_price':  0.002268,   # UNI price in WETH
        'spread_pct': 2.35,
        'liq_buy':    38_000,
        'liq_sell':   29_000,
    },
    {
        'base':       'WETH',
        'quote':      'USDT',
        'buy_dex':    'Uniswap V2 Sepolia',
        'sell_dex':   'SushiSwap Sepolia',
        'buy_price':  3505.00,
        'spread_pct': 1.55,
        'liq_buy':    95_000,
        'liq_sell':   73_000,
    },
]


def _oscillate(base: float, amplitude_pct: float, phase: float) -> float:
    """Vary a value sinusoidally so results look live each scan."""
    return base * (1.0 + (amplitude_pct / 100.0) * math.sin(phase))


class ETHTestnetMockScanner:
    """
    Returns synthetic arbitrage opportunities for Ethereum Sepolia.
    All addresses are real Sepolia deployments.
    Opportunities are fabricated for UI and smart-contract testing only.
    """

    def __init__(self):
        self.testnet = True
        self.w3 = None
        self._connect()
        logger.info("ETH Sepolia Mock Scanner initialised (simulation mode)")

    def _connect(self):
        for url in ETH_TESTNET_RPC:
            try:
                w3 = Web3(Web3.HTTPProvider(url, request_kwargs={'timeout': 15}))
                if w3.is_connected():
                    self.w3 = w3
                    logger.info(f"ETH Sepolia RPC connected: {url}")
                    return
            except Exception as e:
                logger.debug(f"RPC {url}: {e}")

    def scan(self, config: dict) -> dict:
        logger.info("[ETH Sepolia Mock] Generating synthetic opportunities…")

        # Time-based phase — changes every ~30 s so each scan looks slightly different
        phase = (time.time() % 300) / 300 * 2 * math.pi

        gas_usd  = 400_000 * 1.2e-9 * 3500.0   # ~$1.68 on Sepolia

        opportunities = []

        min_liq  = float(config.get('minLiquidityUsd', 2_000))
        min_pct  = float(config.get('minNetProfitPct', 0.10))

        active_dexes  = config.get('dexes',       list(SEPOLIA_ROUTERS.keys()))
        active_tokens = config.get('baseTokens',  list(SEPOLIA_TOKENS.keys()))

        for i, tmpl in enumerate(_PAIR_TEMPLATES):
            if tmpl['base']    not in active_tokens: continue
            if tmpl['buy_dex'] not in active_dexes:  continue
            if tmpl['sell_dex'] not in active_dexes: continue

            # Oscillate price and spread slightly each cycle
            buy_price  = _oscillate(tmpl['buy_price'],  0.4, phase + i)
            spread_pct = _oscillate(tmpl['spread_pct'], 8.0, phase + i * 1.3)
            sell_price = buy_price * (1.0 + spread_pct / 100.0)

            liq_buy  = _oscillate(tmpl['liq_buy'],  3.0, phase + i * 0.7)
            liq_sell = _oscillate(tmpl['liq_sell'], 3.0, phase + i * 1.1)

            if min(liq_buy, liq_sell) < min_liq:
                continue

            pair_liq     = min(liq_buy, liq_sell)
            loan_usd     = max(200.0, pair_liq * 0.0025)
            base_info    = SEPOLIA_TOKENS[tmpl['base']]
            base_usd     = base_info['price_usd']
            loan_amt     = loan_usd / base_usd

            flash_fee_pct = SEPOLIA_FLASH_PROVIDER['fee_bps'] / 100.0
            dex_fee_pct   = 0.60   # 0.3% buy + 0.3% sell
            impact_pct    = (loan_usd / pair_liq) * 100 * 1.5

            gross_profit_usd = loan_usd * (spread_pct / 100.0)
            total_fee_usd    = loan_usd * ((flash_fee_pct + dex_fee_pct + impact_pct) / 100.0)
            net_profit_usd   = gross_profit_usd - total_fee_usd - gas_usd
            net_pct          = (net_profit_usd / loan_usd * 100) if loan_usd > 0 else 0

            if net_profit_usd <= 0 or net_pct < min_pct:
                continue

            quote_info = SEPOLIA_TOKENS.get(tmpl['quote'], SEPOLIA_TOKENS['USDC'])

            opp = {
                'id':                  f"mock_{tmpl['base']}_{tmpl['quote']}_{tmpl['buy_dex']}_{int(time.time())}",
                'pair':                f"{tmpl['base']}/{tmpl['quote']}",
                'baseToken':           tmpl['base'],
                'quoteToken':          tmpl['quote'],
                'baseTokenAddress':    base_info['address'],
                'quoteTokenAddress':   quote_info['address'],
                'buyDex':              tmpl['buy_dex'],
                'sellDex':             tmpl['sell_dex'],
                'buyPrice':            round(buy_price,  8),
                'sellPrice':           round(sell_price, 8),
                'spread':              round(spread_pct, 4),
                'flashLoanAsset':      tmpl['base'],
                'flashLoanAmount':     round(loan_amt,   6),
                'flashLoanAmountUsd':  round(loan_usd,   2),
                'flashLoanProvider':   SEPOLIA_FLASH_PROVIDER['name'],
                'flashLoanPool':       SEPOLIA_FLASH_PROVIDER['pool'],
                'grossProfit':         round(gross_profit_usd / max(base_usd, 1e-9), 6),
                'grossProfitUsd':      round(gross_profit_usd, 2),
                'netProfit':           round(net_profit_usd   / max(base_usd, 1e-9), 6),
                'netProfitUsd':        round(net_profit_usd,  2),
                'gasFee':              round(gas_usd, 2),
                'dexFees':             round(loan_usd * (dex_fee_pct / 100.0), 2),
                'flashFee':            round(loan_usd * (flash_fee_pct / 100.0), 2),
                'netProfitPct':        round(net_pct, 4),
                'buyPoolLiquidity':    round(liq_buy,  0),
                'sellPoolLiquidity':   round(liq_sell, 0),
                'buyPriceImpact':      round(impact_pct / 2, 4),
                'sellPriceImpact':     round(impact_pct / 2, 4),
                'status':              'profitable' if net_profit_usd >= 0.20 else 'marginal',
                'poolAddress':         '',
                'timestamp':           int(time.time()),
                'mock':                True,   # flag so frontend can show simulation label
                'testnet':             True,
            }
            opportunities.append(opp)

        opportunities.sort(key=lambda x: x['netProfitUsd'], reverse=True)
        profitable = [o for o in opportunities if o['netProfitUsd'] > 0 and o['netProfitPct'] >= min_pct]

        logger.info(f"[ETH Sepolia Mock] Generated {len(opportunities)} synthetic opportunities, {len(profitable)} profitable")

        return {
            'opportunities':    opportunities[:20],
            'total':            len(opportunities),
            'profitable':       len(profitable),
            'best_profit_usd':  opportunities[0]['netProfitUsd'] if opportunities else 0,
            'avg_spread':       round(sum(o['spread'] for o in opportunities) / len(opportunities), 4) if opportunities else 0,
            'mock':             True,
            'testnet':          True,
            'scan_timestamp':   int(time.time()),
        }

    def execute_trade(self, opportunity: dict, wallet_address: str, contract_address: str) -> dict:
        """
        Build a real unsigned transaction for Sepolia using the opportunity's
        real Sepolia token addresses and real Sepolia DEX routers.
        """
        if not self.w3:
            self._connect()
        if not self.w3:
            return {'status': 'error', 'error': 'Cannot connect to Sepolia RPC'}

        try:
            buy_router  = SEPOLIA_ROUTERS.get(opportunity['buyDex'],  '')
            sell_router = SEPOLIA_ROUTERS.get(opportunity['sellDex'], '')
            if not buy_router or not sell_router:
                return {'status': 'error', 'error': f"No Sepolia router for {opportunity['buyDex']} or {opportunity['sellDex']}"}

            base_addr  = Web3.to_checksum_address(opportunity['baseTokenAddress'].lower())
            quote_addr = Web3.to_checksum_address(opportunity['quoteTokenAddress'].lower())
            flash_amt  = int(opportunity['flashLoanAmount'] * 1e18)
            min_profit = int(opportunity.get('netProfit', 0) * 0.9 * 1e18)
            deadline   = int(time.time()) + 180

            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(contract_address.lower()),
                abi=FLASH_ARB_ABI
            )

            tx = contract.functions.executeArbitrage(
                base_addr, flash_amt,
                Web3.to_checksum_address(buy_router.lower()),
                Web3.to_checksum_address(sell_router.lower()),
                [base_addr, quote_addr],
                [quote_addr, base_addr],
                min_profit, deadline,
                0,  # provider 0 = Aave V3
            ).build_transaction({
                'from':     Web3.to_checksum_address(wallet_address.lower()),
                'gas':      500_000,
                'gasPrice': self.w3.eth.gas_price,
                'nonce':    self.w3.eth.get_transaction_count(Web3.to_checksum_address(wallet_address.lower())),
            })

            return {
                'status': 'ready',
                'unsignedTx': {
                    'to':       tx['to'],
                    'data':     tx['data'],
                    'gas':      hex(tx['gas']),
                    'gasPrice': hex(tx['gasPrice']),
                    'nonce':    hex(tx['nonce']),
                    'value':    '0x0',
                    'chainId':  11155111,  # Sepolia
                },
                'mock': True,
            }

        except Exception as e:
            return {'status': 'error', 'error': str(e)}
