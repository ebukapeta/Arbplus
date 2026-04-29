"""
BSC DEX Scanner — DexScreener price-based (same approach as App.tsx)
Inherits DexScreenerScanner for scanning, keeps Web3 for execution.
"""

import os, time, json, logging
from typing import Optional
from web3 import Web3
from web3.middleware import geth_poa_middleware
from .dexscreener_scanner import DexScreenerScanner

logger = logging.getLogger(__name__)

FLASH_ARB_ABI = json.loads('[{"inputs":[{"internalType":"address","name":"_flashLoanAsset","type":"address"},{"internalType":"uint256","name":"_flashLoanAmount","type":"uint256"},{"internalType":"address","name":"_buyDex","type":"address"},{"internalType":"address","name":"_sellDex","type":"address"},{"internalType":"address[]","name":"_buyPath","type":"address[]"},{"internalType":"address[]","name":"_sellPath","type":"address[]"},{"internalType":"uint256","name":"_minProfit","type":"uint256"},{"internalType":"uint256","name":"_deadline","type":"uint256"}],"name":"executeArbitrage","outputs":[],"stateMutability":"nonpayable","type":"function"}]')

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
    'MDEX':            '0x62c65B31E9b1D9b2580e089f4D2f4fFb8F0dAa5E',
    'BabySwap':        '0x325E343f1dE602396E256B67eFd1F61C3A6B38Bd',
    'Thena':           '0xd4ae6eCA985340Dd434D38F470aCCce4DC78d109',
    'KnightSwap':      '0x05E61E0cDcD2170a76F9568a110CEe3AFdD6c46f',
    'SushiSwap':       '0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506',
    'Nomiswap':        '0xD654953D746f0b114d1F85332Dc43446ac79413d',
    'Squadswap':       '0xA07c5b74C9B40447a954e1466938b865b6BBea36',  # Squadswap BSC router
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
        'XVS':  '0xcF6BB5389c92Bdda8a3747Ddb454cB7a64626C63',
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
        'BUSD':1.0,'ETH':3500.0,'DAI':1.0,'CAKE':3.0,'LINK':15.0,'XVS':8.0,
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
        {'name':'DODO Flash',           'fee_bps':0,  'pool':'0x9ad32e3054268B849b84a8dBcC7c8f7c52E4e69A', 'assets':['USDT','USDC','BUSD']},
        {'name':'PancakeSwap V3 Flash', 'fee_bps':1,  'pool':'0x46A15B0b27311cedF172AB29E4f4766fbE7F4364', 'assets':['WBNB','USDT','USDC','BTCB','CAKE']},
        {'name':'Aave V3 BSC',          'fee_bps':5,  'pool':'0x6807dc923806fE8Fd134338EABCA509979a7e0cB', 'assets':['WBNB','USDT','USDC','BTCB','ETH','DAI']},
    ]
    FLASH_PROVIDERS_TESTNET = [
        {'name':'PancakeSwap V2 Testnet Flash','fee_bps':25,'pool':'0xD99D1c33F9fC3444f8101754aBC46c52416550D1','assets':['WBNB','USDT','USDC','BUSD']},
    ]

    GAS_UNITS         = 350_000
    GAS_GWEI_MAINNET  = 1.5
    GAS_GWEI_TESTNET  = 10.0
    NATIVE_PRICE_USD  = 600.0

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
            flash_amt  = int(opportunity['flashLoanAmount'] * 1e18)
            min_profit = int(opportunity.get('netProfit', 0) * 0.9 * 1e18)
            deadline   = int(time.time()) + 1200  # 20 min — allow time for block inclusion

            # Get router addresses — try exact match first, then case-insensitive partial
            buy_router_raw  = self._resolve_router(opportunity['buyDex'])
            sell_router_raw = self._resolve_router(opportunity['sellDex'])
            if not buy_router_raw or not sell_router_raw:
                return {'status': 'error', 'error': f"Router not found for {opportunity['buyDex']} or {opportunity['sellDex']}. Add it to BSC DEX_ROUTERS_MAINNET."}

            tx = contract.functions.executeArbitrage(
                base_addr, flash_amt,
                Web3.to_checksum_address(buy_router_raw.lower()),
                Web3.to_checksum_address(sell_router_raw.lower()),
                [base_addr, quote_addr],
                [quote_addr, base_addr],
                min_profit, deadline,
            ).build_transaction({
                'from':     Web3.to_checksum_address(wallet_address.lower()),
                'gas':      600_000,
                'gasPrice': max(self.w3.eth.gas_price, 2_000_000_000),  # min 2 gwei
                'nonce':    self.w3.eth.get_transaction_count(
                    Web3.to_checksum_address(wallet_address.lower())
                ),
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
