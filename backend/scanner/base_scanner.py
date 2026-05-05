"""
Base Network DEX Scanner — DexScreener price-based
8 base tokens, 8 mainnet DEXes, 8 testnet DEXes
"""
import os, time, json, logging
from typing import Optional
from web3 import Web3
from .dexscreener_scanner import DexScreenerScanner

logger = logging.getLogger(__name__)


def _pack_flags(provider: int, buy_dex_type: int, sell_dex_type: int,
                buy_fee_tier: int, sell_fee_tier: int) -> int:
    """Pack 5 values into a single uint256 flags word for executeArbitrage."""
    return (int(provider) |
           (int(buy_dex_type)  << 8)  |
           (int(sell_dex_type) << 16) |
           (int(buy_fee_tier)  << 24) |
           (int(sell_fee_tier) << 48))

FLASH_ARB_ABI = json.loads('[{"inputs": [{"internalType": "address", "name": "_asset", "type": "address"}, {"internalType": "uint256", "name": "_amount", "type": "uint256"}, {"internalType": "address", "name": "_buyDex", "type": "address"}, {"internalType": "address", "name": "_sellDex", "type": "address"}, {"internalType": "address[]", "name": "_buyPath", "type": "address[]"}, {"internalType": "address[]", "name": "_sellPath", "type": "address[]"}, {"internalType": "uint256", "name": "_minProfit", "type": "uint256"}, {"internalType": "uint256", "name": "_flags", "type": "uint256"}], "name": "executeArbitrage", "outputs": [], "stateMutability": "nonpayable", "type": "function"}]')

BASE_MAINNET_RPC = ['https://mainnet.base.org','https://rpc.ankr.com/base','https://base.llamarpc.com']
BASE_TESTNET_RPC = ['https://sepolia.base.org','https://base-sepolia-rpc.publicnode.com']

DEX_ROUTERS_MAINNET = {
    'Aerodrome':           '0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43',
    'BaseSwap':            '0x327Df1E6de05895d2ab08513aaDD9313Fe505d86',
    'Uniswap V3 Base':     '0x2626664c2603336E57B271c5C0b26F421741e481',
    'SwapBased':           '0xaaa3b1F1bd7BCc97fD1917c18ADE665C5D31361f',
    'AlienBase':           '0x8c1A3cF8f83074169FE5D7aD50B978e1cD6b37c7',
    'RocketSwap':          '0x4cf76043B3f97ba06917cBd90F9e3A2AAC1B306e',
    'PancakeSwap V3 Base': '0x1b81D678ffb9C0263b24A97847620C99d213eB14',
    'SushiSwap Base':      '0x6BDED42c6DA8FBf0d2bA55B2fa120C5e0c8D7891',
    'Balancer V2 Base':    '0xBA12222222228d8Ba445958a75a0704d566BF2C8',
    'Extra Finance':       '0x8F9Fa34C4E3009337D28b0fEFB4ed2F78Ddc46D5',
}
DEX_ROUTERS_TESTNET = {
    'Uniswap V3 Base Sepolia': '0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4',
    'Aerodrome Base Sepolia':  '0x1912EC31C9D43DD84dc10e3bE3B77b2BccBbD4BC',
    'BaseSwap Sepolia':        '0x327Df1E6de05895d2ab08513aaDD9313Fe505d86',
    'SushiSwap Base Sepolia':  '0x6BDED42c6DA8FBf0d2bA55B2fa120C5e0c8D7891',
    'PancakeSwap V3 Base Sep': '0x1b81D678ffb9C0263b24A97847620C99d213eB14',
    'AlienBase Sepolia':       '0x8c1A3cF8f83074169FE5D7aD50B978e1cD6b37c7',
    'RocketSwap Sepolia':      '0x4cf76043B3f97ba06917cBd90F9e3A2AAC1B306e',
    'SwapBased Sepolia':       '0xaaa3b1F1bd7BCc97fD1917c18ADE665C5D31361f',
}


class BaseScanner(DexScreenerScanner):
    DEXSCREENER_CHAIN = 'base'
    GECKO_CHAIN       = 'base'       # GeckoTerminal slug for Base
    NETWORK_NAME      = 'Base'

    BASE_TOKENS_MAINNET = {
        'WETH':  '0x4200000000000000000000000000000000000006',
        'USDC':  '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',
        'DAI':   '0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb',
        'cbETH': '0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22',
        'AERO':  '0x940181a94A35A4569E4529A3CDfB74e38FD98631',
        'USDbC': '0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA',
        'DEGEN': '0x4ed4E862860beD51a9570b96d89aF5E1B0Efefed',
        'BRETT': '0x532f27101965dd16442E59d40670FaF5eBB142E4',
        'cbBTC': '0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf',
        'rETH':  '0xB6fe221Fe9EeF5aBa221c348bA20A1Bf5e73624',
    }
    BASE_TOKENS_TESTNET = {
        'WETH':  '0x4200000000000000000000000000000000000006',
        'USDC':  '0x036CbD53842c5426634e7929541eC2318f3dCF7e',
        'DAI':   '0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb',
        'cbETH': '0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22',
        'AERO':  '0x940181a94A35A4569E4529A3CDfB74e38FD98631',
        'USDbC': '0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA',
        'DEGEN': '0x4ed4E862860beD51a9570b96d89aF5E1B0Efefed',
        'BRETT': '0x532f27101965dd16442E59d40670FaF5eBB142E4',
    }

    PRICE_FALLBACKS = {
        'WETH':3500.0,'USDC':1.0,'DAI':1.0,'cbETH':3600.0,
        'AERO':1.5,'USDbC':1.0,'DEGEN':0.02,'BRETT':0.15,'cbBTC':65000.0,'rETH':3600.0,
    }

    DEX_ALIASES = {
        'aerodrome-slipstream': 'Aerodrome',
        'aerodrome':            'Aerodrome',
        'aerodrome-v2':         'Aerodrome',
        'uniswap-v3':           'Uniswap V3 Base',
        'uniswap-v2':           'Uniswap V3 Base',
        'sushiswap':            'SushiSwap Base',
        'baseswap':             'BaseSwap',
        'baseswap-v2':          'BaseSwap',
        'pancakeswap-v3':       'PancakeSwap V3 Base',
        'alienbase':            'AlienBase',
        'alien-base':           'AlienBase',
        'swapbased':            'SwapBased',
        'rocketswap':           'RocketSwap',
        'dackieswap':           'DackieSwap',
        'dackieswap-v2':        'DackieSwap',
        'balancer-v2':          'Balancer V2 Base',
        'curve':                'Curve Base',
        'extra-finance':        'Extra Finance',
        'bswap':                'BaseSwap',
        # Additional IDs from live DexScreener Base feeds
        'maverick-v2':          'Maverick V2',
        'synapse':              'Synapse Base',
        'sushiswap-v3':         'SushiSwap V3 Base',
        'pancakeswap-v2':       'PancakeSwap V2 Base',
        'velodrome-slipstream': 'Velodrome Slipstream',
        'velodrome-v2':         'Velodrome V2',
        'horizon-dex':          'Horizon DEX',
        'thick':                'Thick',
        'kim-exchange':         'Kim Exchange',
        'synthswap':            'SynthSwap',
    }

    FLASH_PROVIDERS_MAINNET = [
        {'name':'Balancer V2 Base',    'fee_bps':0,  'pool':'0xBA12222222228d8Ba445958a75a0704d566BF2C8', 'assets':['WETH','USDC','DAI','cbETH','AERO','USDbC']},
        {'name':'Aave V3 Base',        'fee_bps':5,  'pool':'0xA238Dd80C259a72e81d7e4664a9801593F98d1c5', 'assets':['WETH','USDC','DAI','cbETH','USDbC']},
        {'name':'Uniswap V3 Base Flash','fee_bps':5, 'pool':'0xd0b53D9277642d899DF5C87A3966A349A798F224', 'assets':['WETH','USDC','DAI']},
    ]
    FLASH_PROVIDERS_TESTNET = [
        {'name':'Aave V3 Base Sepolia','fee_bps':5, 'pool':'0x6Ae43d3271ff6888e7Fc43Fd7321a503ff738951', 'assets':['WETH','USDC','DAI']},
        {'name':'Uniswap V3 Base Sep', 'fee_bps':5, 'pool':'0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24', 'assets':['WETH','USDC']},
    ]

    GAS_UNITS        = 600_000
    GAS_GWEI_MAINNET = 0.005
    GAS_GWEI_TESTNET = 0.001
    NATIVE_PRICE_USD = 3500.0

    # Per-chain scanning params — Base gas ~$0.005, extremely cheap
    LOAN_CAP_RATIO:    float = 0.01
    MIN_LIQUIDITY_USD: float = 10_000
    MIN_SPREAD_PCT:    float = 0.01
    STABLECOIN_SEARCH_QUERIES: list = [
        'USDC/WETH', 'USDbC/WETH', 'USDT/WETH', 'USDC/USDbC',
        'cbETH/WETH', 'AERO/WETH', 'WBTC/WETH', 'DAI/USDC',
        'BALD/WETH', 'BRETT/WETH',
    ]

    DEX_FEE_BPS: dict = {
        'Uniswap V3 Base':     5,
        'Aerodrome':            5,
        'Aerodrome V2':        30,
        'SushiSwap Base':      5,
        'Aerodrome Slipstream': 5,
        'Extra Finance':       5,
        'RocketSwap':          30,
        'BaseSwap':            30,
        'BaseSwap V2':         30,
        'SushiSwap V3 Base':   5,
        'PancakeSwap V3 Base': 5,
        'PancakeSwap V2 Base': 25,
        'AlienBase':           30,
        'SwapBased':           30,
        'Curve Base':           4,
        'Balancer V2 Base':    30,
        'Maverick V2':         30,
        'Velodrome Slipstream': 5,
        'Velodrome V2':        30,
        'DackieSwap':          30,
        'Kim Exchange':         5,
        'Thick':                5,
        'Synapse Base':         4,
        'SynthSwap':           30,
        'Horizon DEX':         30,
    }

    def __init__(self, testnet: bool = False):
        super().__init__(testnet)
        self.w3: Optional[Web3] = None
        self._connect()

    @property
    def _rpc_list(self):
        env = os.environ.get('BASE_TESTNET_RPC_URL' if self.testnet else 'BASE_RPC_URL', '')
        base = BASE_TESTNET_RPC if self.testnet else BASE_MAINNET_RPC
        return ([env] if env else []) + base

    @property
    def _dex_routers(self):
        return DEX_ROUTERS_TESTNET if self.testnet else DEX_ROUTERS_MAINNET

    def _connect(self):
        for url in self._rpc_list:
            try:
                w3 = Web3(Web3.HTTPProvider(url, request_kwargs={'timeout': 20}))
                if w3.is_connected():
                    self.w3 = w3
                    logger.info(f"Base {'Testnet' if self.testnet else 'Mainnet'} Web3 connected: {url}")
                    return
            except Exception as e:
                logger.debug(f"Base RPC {url}: {e}")

    def _resolve_router(self, dex_name: str) -> str:
        routers = self._dex_routers
        if dex_name in routers:
            return routers[dex_name]
        lower = dex_name.lower()
        for key, addr in routers.items():
            if key.lower() == lower:
                return addr
        for key, addr in routers.items():
            if lower in key.lower() or key.lower() in lower:
                return addr
        return ''

    def execute_trade(self, opportunity: dict, wallet_address: str, contract_address: str) -> dict:
        if not self.w3:
            self._connect()
        if not self.w3:
            return {'status': 'error', 'error': 'Cannot connect to Base RPC'}
        try:
            contract   = self.w3.eth.contract(address=Web3.to_checksum_address(contract_address.lower()), abi=FLASH_ARB_ABI)
            base_addr  = Web3.to_checksum_address(opportunity['baseTokenAddress'].lower())
            quote_addr = Web3.to_checksum_address(opportunity['quoteTokenAddress'].lower())
            loan_sym   = (opportunity.get('baseToken') or opportunity.get('flashLoanAsset') or '').upper()
            loan_dec   = token_decimals(loan_sym)
            flash_amt  = int(opportunity['flashLoanAmount'] * (10 ** loan_dec))
            # Convert USD net profit to token-native units for the on-chain minProfit guard.
            # netProfit is in USD; the contract compares in token units (wei).
            # We use 85% of expected profit as the floor (15% slippage buffer).
            net_profit_usd  = float(opportunity.get('netProfit', 0) or 0)
            loan_asset_sym  = (opportunity.get('baseToken') or opportunity.get('flashLoanAsset') or '').upper()
            token_price_usd = float((self.PRICE_FALLBACKS or {}).get(loan_asset_sym, 0) or 0)
            if token_price_usd > 0 and net_profit_usd > 0:
                min_profit = int((net_profit_usd / token_price_usd) * 0.85 * (10 ** loan_dec))
            else:
                min_profit = 0  # no price info — let on-chain profit check handle it
            deadline   = int(time.time()) + 90    # 90s — stale arb opps revert cleanly
            provider_id= 1 if 'Balancer' in opportunity.get('flashLoanProvider', '') else 0
            buy_router  = self._resolve_router(opportunity['buyDex'])
            sell_router = self._resolve_router(opportunity['sellDex'])
            if not buy_router or not sell_router:
                return {'status':'error','error':f"Router not found for {opportunity['buyDex']} or {opportunity['sellDex']}"}
            buy_router_cs  = Web3.to_checksum_address(buy_router.lower())
            sell_router_cs = Web3.to_checksum_address(sell_router.lower())
            buy_dex_type   = DEX_TYPE.get(opportunity.get('buyDex',  ''), 0)
            sell_dex_type  = DEX_TYPE.get(opportunity.get('sellDex', ''), 0)
            buy_fee_tier   = DEX_FEE_TIER.get(opportunity.get('buyDex',  ''), 3000)
            sell_fee_tier  = DEX_FEE_TIER.get(opportunity.get('sellDex', ''), 3000)
            sender         = Web3.to_checksum_address(wallet_address.lower())
            gas_price      = max(self.w3.eth.gas_price, 2_000_000_000)
            flags     = _pack_flags(provider_id, buy_dex_type, sell_dex_type,
                                    buy_fee_tier, sell_fee_tier)
            call_args = [
                base_addr, flash_amt,
                buy_router_cs, sell_router_cs,
                [base_addr, quote_addr], [quote_addr, base_addr],
                min_profit, flags,
            ]
            try:
                estimated = contract.functions.executeArbitrage(*call_args).estimate_gas({'from': sender})
                gas_limit = int(estimated * 1.25)
            except Exception as est_err:
                logger.warning(f'Gas estimate failed: {est_err} — using 600K fallback')
                gas_limit = 600_000
            tx = contract.functions.executeArbitrage(*call_args).build_transaction({
                'from': sender, 'gas': gas_limit, 'gasPrice': gas_price,
                'nonce': self.w3.eth.get_transaction_count(sender),
            })
            chain_id = 84532 if self.testnet else 8453
            return {'status':'ready','unsignedTx':{'to':tx['to'],'data':tx['data'],'gas':hex(tx['gas']),'gasPrice':hex(tx['gasPrice']),'nonce':hex(tx['nonce']),'value':'0x0','chainId':chain_id}}
        except Exception as e:
            return {'status':'error','error':str(e)}
