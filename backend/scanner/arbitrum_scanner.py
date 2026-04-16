"""
Arbitrum DEX Scanner — DexScreener price-based
8 base tokens, 8 mainnet DEXes, 8 testnet DEXes
"""
import os, time, json, logging
from typing import Optional
from web3 import Web3
from .dexscreener_scanner import DexScreenerScanner

logger = logging.getLogger(__name__)

FLASH_ARB_ABI = json.loads('[{"inputs":[{"internalType":"address","name":"_flashLoanAsset","type":"address"},{"internalType":"uint256","name":"_flashLoanAmount","type":"uint256"},{"internalType":"address","name":"_buyDex","type":"address"},{"internalType":"address","name":"_sellDex","type":"address"},{"internalType":"address[]","name":"_buyPath","type":"address[]"},{"internalType":"address[]","name":"_sellPath","type":"address[]"},{"internalType":"uint256","name":"_minProfit","type":"uint256"},{"internalType":"uint256","name":"_deadline","type":"uint256"},{"internalType":"uint8","name":"_provider","type":"uint8"}],"name":"executeArbitrage","outputs":[],"stateMutability":"nonpayable","type":"function"}]')

ARB_MAINNET_RPC = ['https://arb1.arbitrum.io/rpc','https://rpc.ankr.com/arbitrum','https://arbitrum.llamarpc.com']
ARB_TESTNET_RPC = ['https://sepolia-rollup.arbitrum.io/rpc']

DEX_ROUTERS_MAINNET = {
    'Camelot V2':          '0xc873fEcbd354f5A56E00E710B90EF4201db2448d',
    'Uniswap V3 Arb':      '0xE592427A0AEce92De3Edee1F18E0157C05861564',
    'SushiSwap Arb':       '0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506',
    'Ramses':              '0xAAA87963EFeB6f7E0a2711F397663105Acb1805e',
    'Trader Joe Arb':      '0x5573405636F4b895E511C9CB54329B88BA862000',
    'Zyberswap':           '0xFa58b8024B49836772180f2Df902f231ba712F72',
    'PancakeSwap V3 Arb':  '0x1b81D678ffb9C0263b24A97847620C99d213eB14',
    'Balancer V2 Arb':     '0xBA12222222228d8Ba445958a75a0704d566BF2C8',
    'Chronos':             '0xE708aA9E887980750C040a6A2Cb901c37Aa34f3b',
    'WOOFi Arb':           '0x9aEd3A8896A85FE9a8CAc52C9B402D092B629a30',
}
DEX_ROUTERS_TESTNET = {
    'Uniswap V3 Arb Sepolia':  '0x101F443B4d1b059569D643917553c771E1b9663A',
    'Camelot V2 Testnet':      '0xdf39c8f7B09B9E3B1e3a9Ae78dE5e36E9Ac9EE72',
    'SushiSwap Arb Sepolia':   '0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506',
    'Ramses Sepolia':          '0xAAA87963EFeB6f7E0a2711F397663105Acb1805e',
    'Zyberswap Sepolia':       '0xFa58b8024B49836772180f2Df902f231ba712F72',
    'Trader Joe Arb Sep':      '0x5573405636F4b895E511C9CB54329B88BA862000',
    'PancakeSwap V3 Arb Sep':  '0x1b81D678ffb9C0263b24A97847620C99d213eB14',
    'Balancer V2 Arb Sep':     '0xBA12222222228d8Ba445958a75a0704d566BF2C8',
}


class ArbitrumScanner(DexScreenerScanner):
    DEXSCREENER_CHAIN = 'arbitrum'
    NETWORK_NAME      = 'Arbitrum'

    BASE_TOKENS_MAINNET = {
        'WETH':  '0x82aF49447D8a07e3bd95BD0d56f35241523fBab1',
        'USDT':  '0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9',
        'USDC':  '0xaf88d065e77c8cC2239327C5EDb3A432268e5831',
        'DAI':   '0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1',
        'WBTC':  '0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f',
        'ARB':   '0x912CE59144191C1204E64559FE8253a0e49E6548',
        'FRAX':  '0x17FC002b466eEc40DaE837Fc4bE5c67993ddBd6F',
        'GMX':   '0xfc5A1A6EB076a2C7aD06eD22C90d7E710E35ad0a',
        'LINK':  '0xf97f4df75117a78c1A5a0DBb814Af92458539FB3',
        'USDCe': '0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8',
    }
    BASE_TOKENS_TESTNET = {
        'WETH':  '0x980B62Da83eFf3D4576C647993b0c1D7faf17c73',
        'USDC':  '0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d',
        'ARB':   '0x912CE59144191C1204E64559FE8253a0e49E6548',
        'DAI':   '0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1',
        'USDT':  '0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9',
        'WBTC':  '0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f',
        'FRAX':  '0x17FC002b466eEc40DaE837Fc4bE5c67993ddBd6F',
        'GMX':   '0xfc5A1A6EB076a2C7aD06eD22C90d7E710E35ad0a',
    }

    PRICE_FALLBACKS = {
        'WETH':3500.0,'USDT':1.0,'USDC':1.0,'DAI':1.0,'WBTC':65000.0,
        'ARB':1.2,'FRAX':1.0,'GMX':25.0,'LINK':15.0,'USDCe':1.0,
    }

    DEX_ALIASES = {
        'camelot':              'Camelot V2',
        'camelot-v3':           'Camelot V2',
        'camelot-v2':           'Camelot V2',
        'uniswap-v3':           'Uniswap V3 Arb',
        'sushiswap':            'SushiSwap Arb',
        'ramses-cl':            'Ramses',
        'ramses':               'Ramses',
        'traderjoe-v21':        'Trader Joe Arb',
        'traderjoe-v20':        'Trader Joe Arb',
        'traderjoe':            'Trader Joe Arb',
        'pancakeswap-v3':       'PancakeSwap V3 Arb',
        'zyberswap':            'Zyberswap',
        'zyberswap-v2':         'Zyberswap',
        'balancer-v2':          'Balancer V2 Arb',
        'woofi':                'WOOFi Arb',
        'chronos':              'Chronos',
        'chronos-v2':           'Chronos',
        'woofi-v2':             'WOOFi Arb',
        'odos':                 'Odos',
        'gmx':                  'GMX',
        'gmx-v2':               'GMX',
        'dodo':                 'DODO Arb',
        'kyberswap-elastic':    'Kyberswap Arb',
        'curve':                'Curve Arb',
        'aave-v3':              'Aave V3 Arb',
        'radiant':              'Radiant',
    }

    FLASH_PROVIDERS_MAINNET = [
        {'name':'Aave V3 Arb',        'fee_bps':5,  'pool':'0x794a61358D6845594F94dc1DB02A252b5b4814aD', 'assets':['WETH','WBTC','USDC','USDT','DAI','FRAX','ARB']},
        {'name':'Balancer V2 Arb',    'fee_bps':0,  'pool':'0xBA12222222228d8Ba445958a75a0704d566BF2C8', 'assets':['WETH','WBTC','USDC','USDT','DAI','ARB']},
        {'name':'Uniswap V3 Arb Flash','fee_bps':5, 'pool':'0xC31E54c7a869B9FcBEcc14363CF510d1c41fa443', 'assets':['WETH','USDC','USDT']},
    ]
    FLASH_PROVIDERS_TESTNET = [
        {'name':'Aave V3 Arb Sep',    'fee_bps':5, 'pool':'0xBfC91D59fdAA134A4ED45f7B584cAf96D7792Eff', 'assets':['WETH','USDC','ARB']},
        {'name':'Balancer V2 Arb Sep','fee_bps':0, 'pool':'0xBA12222222228d8Ba445958a75a0704d566BF2C8', 'assets':['WETH','USDC']},
    ]

    GAS_UNITS        = 350_000
    GAS_GWEI_MAINNET = 0.1
    GAS_GWEI_TESTNET = 0.05
    NATIVE_PRICE_USD = 3500.0

    def __init__(self, testnet: bool = False):
        super().__init__(testnet)
        self.w3: Optional[Web3] = None
        self._connect()

    @property
    def _rpc_list(self):
        env = os.environ.get('ARB_TESTNET_RPC_URL' if self.testnet else 'ARB_RPC_URL', '')
        base = ARB_TESTNET_RPC if self.testnet else ARB_MAINNET_RPC
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
                    logger.info(f"Arbitrum {'Testnet' if self.testnet else 'Mainnet'} Web3 connected: {url}")
                    return
            except Exception as e:
                logger.debug(f"ARB RPC {url}: {e}")

    def execute_trade(self, opportunity: dict, wallet_address: str, contract_address: str) -> dict:
        if not self.w3:
            self._connect()
        if not self.w3:
            return {'status': 'error', 'error': 'Cannot connect to Arbitrum RPC'}
        try:
            contract   = self.w3.eth.contract(address=Web3.to_checksum_address(contract_address.lower()), abi=FLASH_ARB_ABI)
            base_addr  = Web3.to_checksum_address(opportunity['baseTokenAddress'].lower())
            quote_addr = Web3.to_checksum_address(opportunity['quoteTokenAddress'].lower())
            flash_amt  = int(opportunity['flashLoanAmount'] * 1e18)
            min_profit = int(opportunity.get('netProfit', 0) * 0.9 * 1e18)
            deadline   = int(time.time()) + 180
            provider_id= 1 if 'Balancer' in opportunity.get('flashLoanProvider', '') else 0
            buy_router  = self._dex_routers.get(opportunity['buyDex'],  '')
            sell_router = self._dex_routers.get(opportunity['sellDex'], '')
            if not buy_router or not sell_router:
                return {'status':'error','error':f"Router not found for {opportunity['buyDex']} or {opportunity['sellDex']}"}
            tx = contract.functions.executeArbitrage(
                base_addr, flash_amt,
                Web3.to_checksum_address(buy_router.lower()),
                Web3.to_checksum_address(sell_router.lower()),
                [base_addr, quote_addr], [quote_addr, base_addr],
                min_profit, deadline, provider_id,
            ).build_transaction({
                'from': Web3.to_checksum_address(wallet_address.lower()),
                'gas': 500_000, 'gasPrice': self.w3.eth.gas_price,
                'nonce': self.w3.eth.get_transaction_count(Web3.to_checksum_address(wallet_address.lower())),
            })
            return {'status':'ready','unsignedTx':{'to':tx['to'],'data':tx['data'],'gas':hex(tx['gas']),'gasPrice':hex(tx['gasPrice']),'nonce':hex(tx['nonce']),'value':'0x0','chainId':421614 if self.testnet else 42161}}
        except Exception as e:
            return {'status':'error','error':str(e)}
