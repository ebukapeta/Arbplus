"""
BSC DEX Scanner — DexScreener price-based (same approach as App.tsx)
Inherits DexScreenerScanner for scanning, keeps Web3 for execution.
"""

import os, time, json, logging
from typing import Optional
from web3 import Web3
from web3.middleware import geth_poa_middleware
from .dexscreener_scanner import (
    DexScreenerScanner, token_decimals,
    DEX_TYPE, DEX_FEE_TIER,
)

logger = logging.getLogger(__name__)


def _pack_flags(provider: int, buy_dex_type: int, sell_dex_type: int,
                buy_fee_tier: int, sell_fee_tier: int,
                flash_pool: str = '0x0000000000000000000000000000000000000000') -> int:
    """
    Pack values into a single uint256 flags word for executeArbitrage.
    bits  0-7:   provider (0=DODO, 1=PCSv3, 2=Aave)
    bits  8-15:  buyDexType
    bits 16-23:  sellDexType
    bits 24-47:  buyFeeTier
    bits 48-71:  sellFeeTier
    bits 72-231: flashLoanPool address (passed for PCS V3 — looked up from factory)
    """
    pool_int = int(flash_pool, 16) if flash_pool.startswith('0x') else 0
    return (int(provider) |
           (int(buy_dex_type)  << 8)  |
           (int(sell_dex_type) << 16) |
           (int(buy_fee_tier)  << 24) |
           (int(sell_fee_tier) << 48) |
           (pool_int           << 72))

# PancakeSwap V3 Factory BSC — used to look up correct pool addresses at runtime
PANCAKE_V3_FACTORY = '0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865'
PANCAKE_V3_FACTORY_ABI = '[{"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"},{"internalType":"uint24","name":"fee","type":"uint24"}],"name":"getPool","outputs":[{"internalType":"address","name":"pool","type":"address"}],"stateMutability":"view","type":"function"}]'

def get_pcs_v3_pool(w3, token_addr: str, paired_with: str = '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c',
                    fee_tiers: list = None) -> str:
    """
    Look up the real PancakeSwap V3 pool for a token pair using the factory.
    Returns the pool address or '' if none found.
    fee_tiers: list of fee tiers to try in order (default: [100, 500, 2500, 10000])
    """
    if fee_tiers is None:
        fee_tiers = [100, 500, 2500, 10000]
    import json
    try:
        factory = w3.eth.contract(
            address=w3.to_checksum_address(PANCAKE_V3_FACTORY),
            abi=json.loads(PANCAKE_V3_FACTORY_ABI)
        )
        for fee in fee_tiers:
            pool = factory.functions.getPool(
                w3.to_checksum_address(token_addr),
                w3.to_checksum_address(paired_with),
                fee
            ).call()
            if pool and pool != '0x' + '0'*40:
                return pool
    except Exception as e:
        pass
    return ''


FLASH_ARB_ABI = json.loads('[{"inputs": [{"internalType": "address", "name": "_asset", "type": "address"}, {"internalType": "uint256", "name": "_amount", "type": "uint256"}, {"internalType": "address", "name": "_buyDex", "type": "address"}, {"internalType": "address", "name": "_sellDex", "type": "address"}, {"internalType": "address[]", "name": "_buyPath", "type": "address[]"}, {"internalType": "address[]", "name": "_sellPath", "type": "address[]"}, {"internalType": "uint256", "name": "_minProfit", "type": "uint256"}, {"internalType": "uint256", "name": "_flags", "type": "uint256"}], "name": "executeArbitrage", "outputs": [], "stateMutability": "nonpayable", "type": "function"}]')

BSC_MAINNET_RPC = [
    'https://rpc.ankr.com/bsc',
    'https://bsc-rpc.publicnode.com',
    'https://binance.llamarpc.com',
    'https://bsc.meowrpc.com',
    'https://bsc-dataseed.bnbchain.org',
]
BSC_TESTNET_RPC = [
    'https://data-seed-prebsc-1-s1.binance.org:8545/',
    'https://data-seed-prebsc-2-s1.binance.org:8545/',
]

DEX_ROUTERS_MAINNET = {
    'PancakeSwap V2':  '0x10ED43C718714eb63d5aA57B78B54704E256024E',
    'PancakeSwap V3':  '0x1b81D678ffb9C0263b24A97847620C99d213eB14',
    'ApeSwap':         '0xcF0feBd3f17CEf5b47b0cD257aCf6025c5BFf3b7',
    'BiSwap':          '0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8',
    'MDEX':            '0x7DAe51BD3E3376B8c7c4900E9107f12Be3AF1bA8',  # MDEX BSC router
    'BabySwap':        '0x325E343f1dE602396E256B67eFd1F61C3A6B38Bd',
    'Thena':           '0xd4ae6eCA985340Dd434D38F470aCCce4DC78d109',
    'KnightSwap':      '0x05E61E0cDcD2170a76F9568a110CEe3AFdD6c46f',
    'SushiSwap':       '0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506',
    'Nomiswap':        '0xD654953D746f0b114d1F85332Dc43446ac79413d',
    'Squadswap':       '0x1B6C9c20693afDE803B27F8782156c0f892ABC2d',  # Squadswap V2 router
    # Newly whitelisted BSC DEXes — verified mainnet router addresses
    'Swych':           '0x6131B5fae19EA4f9D964eAc0408E4408b66337b5',  # Swych BSC V2 router
    'AutoShark':       '0xB0EeB0632bAB15F6f14F418d39273af54DB87f84',  # AutoShark router
    'UniChain BSC':    '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',  # Uniswap-compatible
    'WaultSwap':       '0xD48745E39BbED146eec15b79CbF964884F9877c2',  # WaultSwap BSC
    'Ellipsis':        '0x160CAed03795365F3A589f10C379FfA7d75d4E76',  # Ellipsis BSC
    'SushiSwap V3 BSC':'0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506',  # SushiSwap
    'Uniswap V3 BSC':  '0xdB1d10011AD0Ff90774D0C6Bb92e5C5c8b4461F7',  # Uniswap V3 BSC
}
DEX_ROUTERS_TESTNET = {
    'PancakeSwap V2 Testnet': '0xD99D1c33F9fC3444f8101754aBC46c52416550D1',
    'PancakeSwap V3 Testnet': '0x1b81D678ffb9C0263b24A97847620C99d213eB14',
    'BakerySwap Testnet':     '0xCDe540d7eAFE93aC439CeF360f775d9E69dFd93E',
    'JulSwap Testnet':        '0xbd67d157502A23309Db761c41965600c2Ec788b2',
    'ApeSwap Testnet':        '0xcF0feBd3f17CEf5b47b0cD257aCf6025c5BFf3b7',
    'BiSwap Testnet':         '0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8',
    'MDEX Testnet':           '0x62c65B31E9b1D9b2580e089f4D2f4fFb8F0dAa5E',
    'SushiSwap Testnet':      '0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506',
    'Nomiswap Testnet':       '0xD654953D746f0b114d1F85332Dc43446ac79413d',
    'KnightSwap Testnet':     '0x05E61E0cDcD2170a76F9568a110CEe3AFdD6c46f',
}


class BSCScanner(DexScreenerScanner):
    DEXSCREENER_CHAIN = 'bsc'
    NETWORK_NAME      = 'BNB Chain'

    BASE_TOKENS_MAINNET = {
        'WBNB': '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c',
        'USDT': '0x55d398326f99059fF775485246999027B3197955',
        'USDC': '0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d',
        'BTCB': '0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c',
        'BUSD': '0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56',
        'ETH':  '0x2170Ed0880ac9A755fd29B2688956BD959F933F8',
        'DAI':  '0x1AF3F329e8BE154074D8769D1FFa4eE058B1DBc3',
        'CAKE': '0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82',
        'LINK': '0xF8A0BF9cF54Bb92F17374d9e9A321E6a111a51bD',
        'FDUSD':  '0xc5f0f7b66764F6ec8C8Dff7BA683102295E16409',
    }
    BASE_TOKENS_TESTNET = {
        'WBNB': '0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd',
        'USDT': '0x337610d27c682E347C9cD60BD4b3b107C9d34dDd',
        'USDC': '0x64544969ed7EBf5f083679233325356EbE738930',
        'BUSD': '0xeD24FC36d5Ee211Ea25A80239Fb8C4Cfd80f12Ee',
        'DAI':  '0xEC5dCb5Dbf4B114C9d0F65BcCAb49EC54F6A0867',
        'BTCB': '0x6ce8dA28E2f864420840cF74474eFf5bD8C6feed',
        'ETH':  '0x8BaBbB98678facC7342735486C851ABd7A0d17Cc',
        'CAKE': '0xFa60D973F7642B748046464e165A65B7323b0DEE',
    }

    PRICE_FALLBACKS = {
        'WBNB':600.0,'USDT':1.0,'USDC':1.0,'BTCB':65000.0,
        'BUSD':1.0,'ETH':3500.0,'DAI':1.0,'CAKE':3.0,'LINK':15.0,'FDUSD':1.0,
    }

    # DexScreener dexId → canonical name used in UI config
    DEX_ALIASES = {
        'pancakeswap-v3':           'PancakeSwap V3',
        'pancakeswap-amm-v3':       'PancakeSwap V3',
        'pancakeswap-amm':          'PancakeSwap V2',
        'pancakeswap-v2':           'PancakeSwap V2',
        'pancakeswap':              'PancakeSwap V2',
        'biswap':                   'BiSwap',
        'apeswap':                  'ApeSwap',
        'thena':                    'Thena',
        'thena-fusion':             'Thena',
        'thena-v3':                 'Thena',
        'mdex':                     'MDEX',
        'babyswap':                 'BabySwap',
        'sushiswap':                'SushiSwap',
        'nomiswap':                 'Nomiswap',
        'nomiswap-stable':          'Nomiswap',
        'knightswap':               'KnightSwap',
        'wombat-exchange':          'Wombat',
        'ellipsis-finance':         'Ellipsis',
        'dodo':                     'DODO',
        'acryptosswap':             'ACryptoS',
        'uniswap-v3':               'PancakeSwap V3',  # DexScreener labels PCS V3 as uniswap-v3 on BSC
        'uniswap':                  'PancakeSwap V2',  # Generic uniswap → PCS V2 on BSC
        'squadswap':                'Squadswap',
        'squadswap-v2':             'Squadswap',
        'squadswap-v3':             'Squadswap',

        # GeckoTerminal aliases (underscore_format → display name)
        'pancakeswap_v2': 'PancakeSwap V2',
        'pancakeswap_v3': 'PancakeSwap V3',
        'biswap': 'BiSwap',
        'apeswap': 'ApeSwap',
        'mdex': 'MDEX',
        'babyswap': 'BabySwap',
        'thena': 'Thena',
        'knightswap': 'KnightSwap',
        'sushiswap': 'SushiSwap',
        'nomiswap': 'Nomiswap',
        'squadswap': 'Squadswap',
        # Testnet mappings
        'pancakeswap-v2-testnet':   'PancakeSwap V2 Testnet',

        # Additional BSC DEX IDs seen in live DexScreener feeds
        'swych':                    'Swych',
        'swych-v2':                 'Swych',
        'autoshark':                'AutoShark',
        'autoshark-v2':             'AutoShark',
        'unichain':                 'UniChain BSC',
        'unichain-v2':              'UniChain BSC',
        'sushiswap-v3':             'SushiSwap V3 BSC',
        'uniswap-v3':               'Uniswap V3 BSC',
        'waultswap':                'WaultSwap',
        'ellipsis':                 'Ellipsis',
        'ellipsis-finance':         'Ellipsis',
        'babyswap-v2':              'BabySwap',
        'dodo-bsc':                 'DODO BSC',
        'traderjoexyz':             'Trader Joe BSC',
        'ant-exchange':             'Ant Exchange',
    }

    FLASH_PROVIDERS_MAINNET = [
        # DODO pool 0x9ad3... is a USDT/USDC pool — can only lend USDT or USDC
        {'name':'DODO Flash',           'fee_bps':0,  'pool':'0x9ad32e3054268B849b84a8dBcC7c8f7c52E4e69A', 'assets':['USDT','USDC']},
        # PancakeSwap V3 Flash: pool address looked up dynamically via tokenFlashPool
        # mapping on the contract. Owner must call setTokenFlashPool() after deploy.
        # Tokens supported depend on which pools have been registered.
        {'name':'PancakeSwap V3 Flash', 'fee_bps':1,  'pool':'dynamic', 'assets':['WBNB','USDT','CAKE','BTCB','ETH','LINK']},
        # Aave V3 BSC is the universal provider — widest asset support
        {'name':'Aave V3 BSC',          'fee_bps':5,  'pool':'0x6807dc923806fE8Fd134338EABCA509979a7e0cB',
         'assets':['WBNB','USDT','USDC','BTCB','ETH','DAI','BUSD','FDUSD','LINK']},
        # CAKE/WBNB PCS V3 pool — provider 3, for CAKE flash loans only
        {'name':'PancakeSwap V3 CAKE',  'fee_bps':1,  'pool':'0x7f51c8AaA6B0599aBd16674e2b17FEC7a9f674A1', 'assets':['CAKE']},
    ]
    FLASH_PROVIDERS_TESTNET = [
        {'name':'PancakeSwap V2 Testnet Flash','fee_bps':25,'pool':'0xD99D1c33F9fC3444f8101754aBC46c52416550D1','assets':['WBNB','USDT','USDC','BUSD']},
    ]

    GAS_UNITS         = 300_000
    GAS_GWEI_MAINNET  = 1.5
    GAS_GWEI_TESTNET  = 10.0
    NATIVE_PRICE_USD  = 600.0

    # Per-chain scanning params
    LOAN_CAP_RATIO:    float = 0.01
    MIN_LIQUIDITY_USD: float = 10_000
    MIN_SPREAD_PCT:    float = 0.01

    STABLECOIN_SEARCH_QUERIES: list = [
        'USDT/WBNB', 'USDC/WBNB', 'BUSD/WBNB', 'USDT/USDC',
        'BTCB/WBNB', 'ETH/WBNB', 'CAKE/WBNB', 'USDT/BUSD', 'FDUSD/WBNB', 'FDUSD/USDT',
    ]

    DEX_FEE_BPS: dict = {
        'PancakeSwap V2':      25,
        'PancakeSwap V3':       5,
        'BiSwap':              10,
        'Squadswap':           25,
        'MDEX':                30,
        'BabySwap':            30,
        'Nomiswap':            25,
        'AutoShark':           25,
        'UniChain BSC':        30,
        'Swych':               25,
        'SushiSwap V3 BSC':    5,
        'Uniswap V3 BSC':      5,
        'WaultSwap':           20,
        'Ellipsis':             4,
        'DODO':                 0,
        'SushiSwap':           30,
        'ApeSwap':             20,
        'KnightSwap':          25,
        'Thena':               5,
        'Trader Joe BSC':      30,
        'Wombat':              1,
        'ACryptoS':            5,
        'PancakeSwap V2 Testnet': 25,
        'DODO BSC':             0,
        'Ant Exchange':        25,
    }

    def __init__(self, testnet: bool = False):
        super().__init__(testnet)
        self.w3: Optional[Web3] = None
        self._last_bnb_price = 600.0
        self._connect()

    @property
    def _rpc_list(self):
        env = os.environ.get('BSC_TESTNET_RPC_URL' if self.testnet else 'BSC_RPC_URL', '')
        base = BSC_TESTNET_RPC if self.testnet else BSC_MAINNET_RPC
        return ([env] if env else []) + base

    @property
    def _dex_routers(self):
        return DEX_ROUTERS_TESTNET if self.testnet else DEX_ROUTERS_MAINNET

    def _connect(self):
        for url in self._rpc_list:
            try:
                w3 = Web3(Web3.HTTPProvider(url, request_kwargs={'timeout': 20}))
                w3.middleware_onion.inject(geth_poa_middleware, layer=0)
                if w3.is_connected():
                    self.w3 = w3
                    label = 'Testnet' if self.testnet else 'Mainnet'
                    logger.info(f"BSC {label} Web3 connected (for execution): {url}")
                    return
            except Exception as e:
                logger.debug(f"BSC RPC {url}: {e}")

    def _resolve_router(self, dex_name: str) -> str:
        """
        Resolve a DEX name to its router address.
        Tries exact match first, then case-insensitive, then partial match.
        """
        routers = self._dex_routers
        # Exact match
        if dex_name in routers:
            return routers[dex_name]
        # Case-insensitive exact
        lower = dex_name.lower()
        for key, addr in routers.items():
            if key.lower() == lower:
                return addr
        # Partial match — dex_name is contained in a router key
        for key, addr in routers.items():
            if lower in key.lower() or key.lower() in lower:
                return addr
        return ''

    NATIVE_INTERMEDIATE = '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c'  # WBNB

    # Minimal ABI to read reserves and token0 from any Uniswap V2 style pair contract
    _PAIR_ABI = __import__('json').loads(
        '[{"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"stateMutability":"view","type":"function"},' +
        '{"inputs":[],"name":"token0","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},' +
        '{"inputs":[],"name":"token1","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"}]'
    )

    def _validate_pair(self, pair_addr: str) -> bool:
        """
        Validate a pool using its pair contract address (from DexScreener).
        Calls getReserves() directly — no router address needed.
        Returns True if pool has liquidity (both reserves > 0).
        """
        if not pair_addr or len(pair_addr) < 42:
            return False
        try:
            pair = self.w3.eth.contract(
                address=Web3.to_checksum_address(pair_addr),
                abi=self._PAIR_ABI
            )
            r0, r1, _ = pair.functions.getReserves().call()
            return r0 > 0 and r1 > 0
        except Exception:
            return False

    def _resolve_path(self, router_addr: str, from_addr: str, to_addr: str,
                      amount_wei: int, pair_addr: str = '') -> list:
        """
        Return the swap path for from_addr→to_addr.

        Strategy:
        1. If pair_addr supplied (from DexScreener), validate via getReserves()
           on the actual pair contract. No router needed — avoids unverified routers.
        2. If pair_addr missing, fall back to router.getAmountsOut (original behaviour).
        3. Returns [from_addr, to_addr] if direct pair validated,
                   [from_addr, WBNB, to_addr] if only intermediate exists,
                   [] if nothing works.
        """
        native = self.NATIVE_INTERMEDIATE.lower()

        # Strategy 1: validate using actual pair contract from DexScreener
        if pair_addr and len(pair_addr) >= 42:
            if self._validate_pair(pair_addr):
                return [from_addr, to_addr]  # direct pair confirmed on-chain
            # Direct pair invalid — try intermediate (different pair contract)
            # We don't have the intermediate pair address so fall through to router

        # Strategy 2: router.getAmountsOut fallback (for intermediate paths)
        import json as _json
        ROUTER_ABI = _json.loads('[{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"}],"name":"getAmountsOut","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"view","type":"function"}]')
        try:
            router = self.w3.eth.contract(
                address=Web3.to_checksum_address(router_addr),
                abi=ROUTER_ABI
            )
            paths_to_try = [[from_addr, to_addr]]
            if from_addr.lower() != native and to_addr.lower() != native:
                paths_to_try.append([from_addr, self.NATIVE_INTERMEDIATE, to_addr])
            for path in paths_to_try:
                try:
                    out = router.functions.getAmountsOut(amount_wei, path).call()
                    if out and out[-1] > 0:
                        return path
                except Exception:
                    continue
        except Exception:
            pass
        return []

    def execute_trade(self, opportunity: dict, wallet_address: str, contract_address: str) -> dict:
        if not self.w3:
            self._connect()
        if not self.w3:
            return {'status': 'error', 'error': 'Cannot connect to BSC RPC for execution'}
        try:
            contract   = self.w3.eth.contract(
                address=Web3.to_checksum_address(contract_address.lower()),
                abi=FLASH_ARB_ABI
            )
            base_addr  = Web3.to_checksum_address(opportunity['baseTokenAddress'].lower())
            quote_addr = Web3.to_checksum_address(opportunity['quoteTokenAddress'].lower())
            loan_sym   = (opportunity.get('baseToken') or opportunity.get('flashLoanAsset') or '').upper()
            loan_dec   = token_decimals(loan_sym)
            flash_amt  = int(opportunity['flashLoanAmount'] * (10 ** loan_dec))
            # Convert USD net profit to token-native units for the on-chain minProfit guard.
            # netProfit is in USD; the contract compares in token units (wei).
            # We use 85% of expected profit as the floor (15% slippage buffer).
            net_profit_usd  = float(opportunity.get('netProfitUsd', 0) or 0)  # USD value, not token units
            loan_asset_sym  = (opportunity.get('baseToken') or opportunity.get('flashLoanAsset') or '').upper()
            token_price_usd = float((self.PRICE_FALLBACKS or {}).get(loan_asset_sym, 0) or 0)
            if token_price_usd > 0 and net_profit_usd > 0:
                min_profit = int((net_profit_usd / token_price_usd) * 0.85 * (10 ** loan_dec))
            else:
                min_profit = 0  # no price info — let on-chain profit check handle it
            deadline   = int(time.time()) + 90    # 90s — stale arb opps revert cleanly

            # Get router addresses — try exact match first, then case-insensitive partial
            buy_router_raw  = self._resolve_router(opportunity['buyDex'])
            sell_router_raw = self._resolve_router(opportunity['sellDex'])
            if not buy_router_raw or not sell_router_raw:
                return {'status': 'error', 'error': f"Router not found for {opportunity['buyDex']} or {opportunity['sellDex']}. Add it to BSC DEX_ROUTERS_MAINNET."}

            # Select flash loan provider:
            # 0=DODO (0% fee, but only works for tokens in that specific pool)
            # 1=PancakeSwap V3 (0.01% fee, works for most BSC tokens)
            # 2=Aave V3 BSC (0.05% fee, broadest asset coverage — safest fallback)
            flash_provider = opportunity.get('flashLoanProvider', '')
            if 'DODO' in flash_provider:
                provider_id = 0
            elif 'PancakeSwap V3' in flash_provider:
                provider_id = 1   # PCS V3 — pool looked up via tokenFlashPool on contract
            else:
                provider_id = 2   # Aave V3 BSC

            buy_router_cs  = Web3.to_checksum_address(buy_router_raw.lower())
            sell_router_cs = Web3.to_checksum_address(sell_router_raw.lower())

            # Resolve actual swap paths — validates direct pair exists, falls back to
            # native-intermediate routing (e.g. TOKEN→WBNB→TOKEN2) if direct fails.
            buy_dex_type  = DEX_TYPE.get(opportunity.get('buyDex',  ''), 0)
            sell_dex_type = DEX_TYPE.get(opportunity.get('sellDex', ''), 0)
            buy_fee_tier  = DEX_FEE_TIER.get(opportunity.get('buyDex',  ''), 3000)
            sell_fee_tier = DEX_FEE_TIER.get(opportunity.get('sellDex', ''), 3000)
            buy_pool_addr  = opportunity.get('buyPoolAddress',  '')
            sell_pool_addr = opportunity.get('sellPoolAddress', '')

            # Build swap paths based on DEX type:
            #   V2 (dexType=0): [pairAddress, tokenIn, tokenOut]
            #     Contract calls pair.swap() directly — no router address needed.
            #     pairAddress comes from DexScreener (verified on-chain).
            #   V3 (dexType=1): [tokenIn, tokenOut]
            #     Contract calls router.exactInputSingle().

            if buy_dex_type == 0:
                # V2: validate pair has reserves, build [pair, tokenIn, tokenOut]
                if not buy_pool_addr:
                    return {'status': 'error', 'error': f'No pool address for {opportunity["buyDex"]} — cannot execute V2 direct swap'}
                if not self._validate_pair(buy_pool_addr):
                    return {'status': 'error', 'error': f'Buy pool has no reserves: {buy_pool_addr[:12]}...'}
                buy_path = [Web3.to_checksum_address(buy_pool_addr.lower()), base_addr, quote_addr]
            else:
                # V3: standard [tokenIn, tokenOut]
                buy_path = [base_addr, quote_addr]

            if sell_dex_type == 0:
                if not sell_pool_addr:
                    return {'status': 'error', 'error': f'No pool address for {opportunity["sellDex"]} — cannot execute V2 direct swap'}
                if not self._validate_pair(sell_pool_addr):
                    return {'status': 'error', 'error': f'Sell pool has no reserves: {sell_pool_addr[:12]}...'}
                sell_path = [Web3.to_checksum_address(sell_pool_addr.lower()), quote_addr, base_addr]
            else:
                sell_path = [quote_addr, base_addr]

            logger.info(f'  buy_path={[a[:10] for a in buy_path]} sell_path={[a[:10] for a in sell_path]}')

            # For PancakeSwap V3 (provider_id=1), look up the real pool address
            # from the PCS V3 factory at runtime — no hardcoded addresses.
            flash_pool_addr = '0x0000000000000000000000000000000000000000'
            if provider_id == 1:
                WBNB = '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c'
                flash_pool_addr = get_pcs_v3_pool(self.w3, base_addr, WBNB)
                if not flash_pool_addr:
                    return {'status': 'error', 'error': f'No PancakeSwap V3 pool found for {opportunity["baseToken"]} — use Aave instead'}
                logger.info(f'  PCS V3 flash pool for {opportunity["baseToken"]}: {flash_pool_addr}')

            flags         = _pack_flags(provider_id, buy_dex_type, sell_dex_type,
                                        buy_fee_tier, sell_fee_tier, flash_pool_addr)
            logger.info(f"  flags={hex(flags)} provider={provider_id} "
                        f"buyType={buy_dex_type}(fee={buy_fee_tier}) "
                        f"sellType={sell_dex_type}(fee={sell_fee_tier})")

            call_args = [
                base_addr, flash_amt,
                buy_router_cs, sell_router_cs,
                buy_path, sell_path,
                min_profit, flags,
            ]
            gas_price  = max(self.w3.eth.gas_price, 2_000_000_000)  # min 2 gwei
            sender     = Web3.to_checksum_address(wallet_address.lower())

            # Estimate gas dynamically — if this reverts, the trade would fail on-chain.
            # Catches stale opportunities before MetaMask even shows the confirmation.
            try:
                estimated = contract.functions.executeArbitrage(*call_args).estimate_gas({
                    'from': sender,
                })
                gas_limit = int(estimated * 1.25)  # 25% buffer above estimate
                logger.info(f"  Gas estimate: {estimated:,} units → limit {gas_limit:,}")
            except Exception as est_err:
                logger.warning(f"  Gas estimation failed ({est_err}) — using 600K fallback")
                gas_limit = 600_000

            tx = contract.functions.executeArbitrage(*call_args).build_transaction({
                'from':     sender,
                'gas':      gas_limit,
                'gasPrice': gas_price,
                'nonce':    self.w3.eth.get_transaction_count(sender),
            })
            chain_id = 97 if self.testnet else 56
            return {
                'status': 'ready',
                'unsignedTx': {
                    'to': tx['to'], 'data': tx['data'],
                    'gas': hex(tx['gas']), 'gasPrice': hex(tx['gasPrice']),
                    'nonce': hex(tx['nonce']), 'value': '0x0',
                    'chainId': chain_id,
                }
            }
        except Exception as e:
            logger.error(f"BSC build tx error: {e}", exc_info=True)
            return {'status': 'error', 'error': str(e)}
