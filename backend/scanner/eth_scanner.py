"""
Ethereum DEX Scanner — DexScreener price-based
10 base tokens, 10 mainnet DEXes, 10 testnet DEXes
"""
import os, time, json, logging
from typing import Optional
from web3 import Web3
from .dexscreener_scanner import (
    DexScreenerScanner, token_decimals,
    DEX_TYPE, DEX_FEE_TIER,
)

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

ETH_MAINNET_RPC = ['https://eth.llamarpc.com','https://rpc.ankr.com/eth','https://ethereum.publicnode.com']
ETH_TESTNET_RPC = ['https://rpc.sepolia.org','https://ethereum-sepolia.publicnode.com']

DEX_ROUTERS_MAINNET = {
    'Uniswap V2':         '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',
    'Uniswap V3':         '0xE592427A0AEce92De3Edee1F18E0157C05861564',
    'SushiSwap ETH':      '0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F',
    'Shibaswap':          '0x03f7724180AA6b939894B5Ca4314783B0b36b329',
    'Fraxswap':           '0xC14d550632db8592D1243Edc8B95b0Ad06703867',
    'PancakeSwap V3 ETH': '0x13f4EA83D0bd40E75C8222255bc855a974568Dd4',
    'Balancer V2':        '0xBA12222222228d8Ba445958a75a0704d566BF2C8',
    'Curve ETH':          '0x99a58482BD75cbab83b27EC03CA68fF489b5788f',
    'DODO ETH':           '0xa356867fDaea8ed601Bb94d8B53E2a6F04Da7b6e',
    'Kyberswap ETH':      '0x6131B5fae19EA4f9D964eAc0408E4408b66337b5',
}
DEX_ROUTERS_TESTNET = {
    # ETH testnet uses only these two verified Sepolia DEXes
    'Uniswap V2 Sepolia':  '0xeE567Fe1712Faf6149d80dA1E6934E354124CfE3',
    'SushiSwap Sepolia':   '0xeaBcE3E74EF19FB48d55747bf2Eb333B6f47A80a',
}


class ETHScanner(DexScreenerScanner):
    DEXSCREENER_CHAIN = 'ethereum'
    GECKO_CHAIN       = 'eth'        # GeckoTerminal uses 'eth' not 'ethereum'
    NETWORK_NAME      = 'Ethereum'

    BASE_TOKENS_MAINNET = {
        'WETH':  '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',
        'USDT':  '0xdAC17F958D2ee523a2206206994597C13D831ec7',
        'USDC':  '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48',
        'DAI':   '0x6B175474E89094C44Da98b954EedeAC495271d0F',
        'WBTC':  '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599',
        'FRAX':  '0x853d955aCEf822Db058eb8505911ED77F175b99e',
        'LUSD':  '0x5f98805A4E8be255a32880FDeC7F6728C6568bA0',
        'LINK':  '0x514910771AF9Ca656af840dff83E8264EcF986CA',
        'UNI':   '0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984',
        'AAVE':  '0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9',
    }
    BASE_TOKENS_TESTNET = {
        'WETH':  '0x7b79995e5f793A07Bc00c21d5351694B20Ca3f2d',
        'USDC':  '0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238',
        'DAI':   '0xFF34B3d4Aee8ddCd6F9AFFFB6Fe49bD371b8a357',
        'LINK':  '0x779877A7B0D9E8603169DdbD7836e478b4624789',
        'UNI':   '0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984',
        'USDT':  '0xaA8E23Fb1079EA71e0a56F48a2aA51851D8433D0',
        'WBTC':  '0x92f3B59a79bFf5dc60c0d59eA13a44D082B2bdFC',
        'AAVE':  '0x88541670E55cC00bEEFD87eB59EDd1b7C511AC9a',
        'FRAX':  '0x853d955aCEf822Db058eb8505911ED77F175b99e',
        'LUSD':  '0x5f98805A4E8be255a32880FDeC7F6728C6568bA0',
    }

    PRICE_FALLBACKS = {
        'WETH':3500.0,'USDT':1.0,'USDC':1.0,'DAI':1.0,'WBTC':65000.0,
        'FRAX':1.0,'LUSD':1.0,'LINK':15.0,'UNI':8.0,'AAVE':100.0,
    }

    DEX_ALIASES = {
        'uniswap-v3':         'Uniswap V3',
        'uniswap-v2':         'Uniswap V2',
        'sushiswap':          'SushiSwap ETH',
        'shibaswap':          'Shibaswap',
        'fraxswap':           'Fraxswap',
        'pancakeswap-v3':     'PancakeSwap V3 ETH',
        'balancer-v2':        'Balancer V2',
        'curve':              'Curve ETH',
        'curve-dex':          'Curve ETH',
        'dodo':               'DODO ETH',
        'kyberswap-classic':  'Kyberswap ETH',
        'maverick':           'Maverick',
        'maverick-v2':        'Maverick',
        'dodo-v2':            'DODO ETH',
        # Additional IDs from live DexScreener ETH feeds
        'sushiswap-v3':       'SushiSwap V3',
        'pancakeswap-v2':     'PancakeSwap V2',
        'verse-dex':          'Verse DEX',
        'elk-finance':        'Elk Finance',
        'defiswap':           'DeFi Swap',
    }

    FLASH_PROVIDERS_MAINNET = [
        {'name':'Balancer V2 Flash', 'fee_bps':0,  'pool':'0xBA12222222228d8Ba445958a75a0704d566BF2C8', 'assets':['WETH','WBTC','USDC','USDT','DAI','FRAX','LINK','UNI','AAVE']},
        {'name':'Uniswap V3 Flash',  'fee_bps':5,  'pool':'0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640', 'assets':['WETH','USDC','USDT','DAI','WBTC']},
        {'name':'Aave V3 ETH',       'fee_bps':5,  'pool':'0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2', 'assets':['WETH','WBTC','USDC','USDT','DAI','FRAX','LINK','UNI','AAVE','LUSD']},
    ]
    FLASH_PROVIDERS_TESTNET = [
        {'name':'Aave V3 Sepolia',       'fee_bps':5, 'pool':'0x6Ae43d3271ff6888e7Fc43Fd7321a503ff738951', 'assets':['WETH','USDC','DAI','LINK']},
        {'name':'Uniswap V3 Sep Flash',  'fee_bps':5, 'pool':'0x3bFA4769FB09eefC5a80d6E87c3B9C650f7Ae48E', 'assets':['WETH','USDC']},
    ]

    GAS_UNITS        = 400_000
    GAS_GWEI_MAINNET = 20.0
    GAS_GWEI_TESTNET = 1.2
    NATIVE_PRICE_USD = 3500.0

    # Per-chain scanning params — ETH gas ~$28 so needs bigger loans & pools
    LOAN_CAP_RATIO:    float = 0.01     # ETH gas ~$28 needs larger loans
    MIN_LIQUIDITY_USD: float = 10_000
    MIN_SPREAD_PCT:    float = 0.01
    STABLECOIN_SEARCH_QUERIES: list = [
        'USDC/WETH', 'USDT/WETH', 'USDC/USDT', 'DAI/USDC',
        'WBTC/WETH', 'WBTC/USDC', 'FRAX/USDC', 'LUSD/USDC',
        'stETH/WETH', 'rETH/WETH',
    ]

    DEX_FEE_BPS: dict = {
        'Uniswap V3':          5,
        'Uniswap V2':          30,
        'SushiSwap ETH':       30,
        'SushiSwap':           30,
        'SushiSwap V3':        5,
        'PancakeSwap V3 ETH':   5,
        'PancakeSwap V3':      5,
        'PancakeSwap V2':      25,
        'Curve ETH':            4,
        'Curve':                4,
        'Balancer V2':         30,
        'Maverick':            30,
        'Kyberswap ETH':       30,
        'Kyberswap Classic':   30,
        'Kyberswap Elastic':    5,
        'DODO ETH':             0,
        'DODO':                 0,
        'Fraxswap':            30,
        'DeFi Swap':           30,
        'Elk Finance':         30,
        'Verse DEX':           30,
        'Shibaswap':           30,
        'ShibaSwap':           30,
    }

    def __init__(self, testnet: bool = False):
        super().__init__(testnet)
        self.w3: Optional[Web3] = None
        self._connect()

    @property
    def _rpc_list(self):
        env = os.environ.get('ETH_TESTNET_RPC_URL' if self.testnet else 'ETH_RPC_URL', '')
        base = ETH_TESTNET_RPC if self.testnet else ETH_MAINNET_RPC
        return ([env] if env else []) + base

    @property
    def _dex_routers(self):
        return DEX_ROUTERS_TESTNET if self.testnet else DEX_ROUTERS_MAINNET

    def _connect(self):
        for url in self._rpc_list:
            try:
                w3 = Web3(Web3.HTTPProvider(url, request_kwargs={'timeout': 25}))
                if w3.is_connected():
                    self.w3 = w3
                    logger.info(f"ETH {'Testnet' if self.testnet else 'Mainnet'} Web3 connected: {url}")
                    return
            except Exception as e:
                logger.debug(f"ETH RPC {url}: {e}")

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


    NATIVE_INTERMEDIATE = '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'  # WETH

    def _resolve_path(self, router_addr: str, from_addr: str, to_addr: str, amount_wei: int) -> list:
        """Validate swap path on-chain. Returns direct or intermediate path, [] if none work."""
        import json as _json
        ROUTER_ABI = '[{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"}],"name":"getAmountsOut","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"view","type":"function"}]'
        try:
            router = self.w3.eth.contract(
                address=Web3.to_checksum_address(router_addr),
                abi=_json.loads(ROUTER_ABI)
            )
        except Exception:
            return [from_addr, to_addr]
        native = self.NATIVE_INTERMEDIATE.lower()
        paths = [[from_addr, to_addr]]
        if from_addr.lower() != native and to_addr.lower() != native:
            paths.append([from_addr, self.NATIVE_INTERMEDIATE, to_addr])
        for path in paths:
            try:
                out = router.functions.getAmountsOut(amount_wei, path).call()
                if out and out[-1] > 0:
                    return path
            except Exception:
                continue
        return []

    def execute_trade(self, opportunity: dict, wallet_address: str, contract_address: str) -> dict:
        if not self.w3:
            self._connect()
        if not self.w3:
            return {'status': 'error', 'error': 'Cannot connect to ETH RPC'}
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
            net_profit_usd  = float(opportunity.get('netProfitUsd', 0) or 0)  # USD value, not token units
            loan_asset_sym  = (opportunity.get('baseToken') or opportunity.get('flashLoanAsset') or '').upper()
            token_price_usd = float((self.PRICE_FALLBACKS or {}).get(loan_asset_sym, 0) or 0)
            if token_price_usd > 0 and net_profit_usd > 0:
                min_profit = int((net_profit_usd / token_price_usd) * 0.85 * (10 ** loan_dec))
            else:
                min_profit = 0  # no price info — let on-chain profit check handle it
            deadline   = int(time.time()) + 90    # 90s — stale arb opps revert cleanly
            provider_id= 0 if 'Balancer' in opportunity.get('flashLoanProvider', '') else 1  # 0=Balancer, 1=Aave
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

            buy_path  = self._resolve_path(buy_router_cs, base_addr, quote_addr, flash_amt)
            sell_path = self._resolve_path(sell_router_cs, quote_addr, base_addr, flash_amt)
            if not buy_path:
                return {'status':'error','error':f'No valid buy path {opportunity["baseToken"]}→{opportunity["quoteToken"]} on {opportunity["buyDex"]}'}
            if not sell_path:
                return {'status':'error','error':f'No valid sell path {opportunity["quoteToken"]}→{opportunity["baseToken"]} on {opportunity["sellDex"]}'}
            flags     = _pack_flags(provider_id, buy_dex_type, sell_dex_type,
                                    buy_fee_tier, sell_fee_tier)
            call_args = [
                base_addr, flash_amt,
                buy_router_cs, sell_router_cs,
                buy_path, sell_path,
                min_profit, flags,
            ]
            try:
                estimated = contract.functions.executeArbitrage(*call_args).estimate_gas({'from': sender})
                gas_limit = int(estimated * 1.25)
            except Exception as est_err:
                logger.warning(f"Gas estimate failed: {est_err} — using 600K fallback")
                gas_limit = 600_000

            tx = contract.functions.executeArbitrage(*call_args).build_transaction({
                'from': sender, 'gas': gas_limit, 'gasPrice': gas_price,
                'nonce': self.w3.eth.get_transaction_count(sender),
            })
            chain_id = 11155111 if self.testnet else 1
            return {'status':'ready','unsignedTx':{'to':tx['to'],'data':tx['data'],'gas':hex(tx['gas']),'gasPrice':hex(tx['gasPrice']),'nonce':hex(tx['nonce']),'value':'0x0','chainId':chain_id}}
        except Exception as e:
            return {'status':'error','error':str(e)}
