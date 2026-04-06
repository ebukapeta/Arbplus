"""
Base DEX Scanner — Same architecture as BSC/ETH/Arbitrum Scanner
Auto flash provider: Aave V3 Base (0.05%) → Balancer V2 Base (0%) → Uniswap V3 Base
"""

import os, gc, time, json, logging
from typing import Optional
from web3 import Web3
from .amm_math import find_optimal_trade_size, calc_price_impact, get_amount_out_v2

logger = logging.getLogger(__name__)

SEL_GET_PAIR     = bytes.fromhex('e6a43905')
SEL_GET_RESERVES = bytes.fromhex('0902f1ac')
MULTICALL3_ADDR  = '0xcA11bde05977b3631167028862bE2a173976CA11'
MULTICALL3_ABI   = json.loads('[{"inputs":[{"components":[{"internalType":"address","name":"target","type":"address"},{"internalType":"bool","name":"allowFailure","type":"bool"},{"internalType":"bytes","name":"callData","type":"bytes"}],"internalType":"struct Multicall3.Call3[]","name":"calls","type":"tuple[]"}],"name":"aggregate3","outputs":[{"components":[{"internalType":"bool","name":"success","type":"bool"},{"internalType":"bytes","name":"returnData","type":"bytes"}],"internalType":"struct Multicall3.Result[]","name":"returnData","type":"tuple[]"}],"stateMutability":"view","type":"function"}]')
FLASH_ARB_ABI    = json.loads('[{"inputs":[{"internalType":"address","name":"_flashLoanAsset","type":"address"},{"internalType":"uint256","name":"_flashLoanAmount","type":"uint256"},{"internalType":"address","name":"_buyDex","type":"address"},{"internalType":"address","name":"_sellDex","type":"address"},{"internalType":"address[]","name":"_buyPath","type":"address[]"},{"internalType":"address[]","name":"_sellPath","type":"address[]"},{"internalType":"uint256","name":"_minProfit","type":"uint256"},{"internalType":"uint256","name":"_deadline","type":"uint256"}],"name":"executeArbitrage","outputs":[],"stateMutability":"nonpayable","type":"function"}]')

NULL_ADDR = '0x' + '0' * 40

BASE_MAINNET_RPC = ['https://mainnet.base.org','https://rpc.ankr.com/base','https://base.llamarpc.com']
BASE_TESTNET_RPC = ['https://sepolia.base.org']

DEX_CONFIGS = {
    'Aerodrome':          {'factory':'0x420DD381b31aEf6683db6B902084cB0FFECe40Da','router':'0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43','fee_bps':20},
    'BaseSwap':           {'factory':'0xFDa619b6d20975be80A10332cD39b9a4b0FAa8BB','router':'0x327Df1E6de05895d2ab08513aaDD9313Fe505d86','fee_bps':30},
    'Uniswap V3 Base':    {'factory':'0x33128a8fC17869897dcE68Ed026d694621f6FDfD','router':'0x2626664c2603336E57B271c5C0b26F421741e481','fee_bps':5},
    'SwapBased':          {'factory':'0x04C9f118d21e8B767D2e50C946f0cC9F6C367300','router':'0xaaa3b1F1bd7BCc97fD1917c18ADE665C5D31361','fee_bps':20},
    'AlienBase':          {'factory':'0x3E84D913803b02A4a7f027165E8cA42C14C0FdE7','router':'0x8c1A3cF8f83074169FE5D7aD50B978e1cD6b37c7','fee_bps':30},
    'RocketSwap':         {'factory':'0x1B8128c3A1B7D20053D10763ff02466ca7FF5A6a','router':'0x4cf76043B3f97ba06917cBd90F9e3A2AAC1B306e','fee_bps':25},
    'PancakeSwap V3 Base':{'factory':'0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865','router':'0x1b81D678ffb9C0263b24A97847620C99d213eB14','fee_bps':5},
    # Testnet
    'Uniswap V3 Base Sepolia': {'factory':'0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24','router':'0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4','fee_bps':5},
    'Aerodrome Sepolia':       {'factory':'0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A','router':'0x1412F539bf4D03DB0bECE45D0Bf58f1c6E6A3f6','fee_bps':20},
}

FLASH_PROVIDERS_MAINNET = [
    {'name':'Balancer V2 Base',    'fee_bps':0,  'pool':'0xBA12222222228d8Ba445958a75a0704d566BF2C8'},
    {'name':'Aave V3 Base',        'fee_bps':5,  'pool':'0xA238Dd80C259a72e81d7e4664a9801593F98d1c5'},
    {'name':'Uniswap V3 Base Flash','fee_bps':5, 'pool':'0xd0b53D9277642d899DF5C87A3966A349A798F224'},
]
FLASH_PROVIDERS_TESTNET = [
    {'name':'Uniswap V3 Base Sep Flash','fee_bps':5,'pool':'0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24'},
]

BASE_TOKENS_MAINNET = {
    'WETH':  '0x4200000000000000000000000000000000000006',
    'USDC':  '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',
    'DAI':   '0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb',
    'cbETH': '0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22',
    'AERO':  '0x940181a94A35A4569E4529A3CDfB74e38FD98631',
    'USDbC': '0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA',
    'DEGEN': '0x4ed4E862860beD51a9570b96d89aF5E1B0Efefed',
    'BRETT': '0x532f27101965dd16442E59d40670FaF5eBB142E4',
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

BASE_PRICE_USD = {
    'WETH':3500.0,'USDC':1.0,'DAI':1.0,'cbETH':3600.0,
    'AERO':1.5,'USDbC':1.0,'DEGEN':0.02,'BRETT':0.15,
}

QUOTE_TOKENS = {
    # Base ecosystem tokens
    'TOSHI':'0xAC1Bd2486aAf3B5C0fc3Fd868558b082a531B2B4',
    'NORMIE':'0x7F12d13B34F5F4f0a9449c89bC4B4a9b8af95bAB',
    'BALD':'0x27D2DECb4bFC9C76F0309b8E88dec3a601Fe25a8',
    'MOCHI':'0xF6e932Ca12afa26665dC4dDE7e27be02A6C Eve1d',
    'SEAM':'0x1C7a460413dD4e964f96D8dFC56E7223cE88CD85',
    'WELL':'0xA88594D404727625A9437C3f886C7643872296AE',
    'EXTRA':'0x2dAD3a13ef0C6366220f989157009e501e7938F8',
    'YFI':'0x9EaF8C1E34F05a589EDa6BAfdF391Cf6Ad3CB239',
    'CBETH':'0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22',
    'RETH':'0xB6fe221Fe9EeF5aBa221c348bA20A1Bf5e73624c',
    'wstETH':'0xc1CBa3fCea344f92D9239c08C0568f6F2F0ee452',
    'COMP':'0x9e1028F5F1D5eDE59748FFceE5532509976840E0',
    'SNX':'0x22e6966B799c4D5B13BE962E1D117b56327FDa66',
    'CRV':'0x8Ee73c484A26e0A5df2Ee2a4960B789967dd0415',
    'BAL':'0x4158734D47Fc9692176B5085E0F52ee0Da5d47F1',
    'UNI':'0xc3De830EA07524a0761646a6a4e4be0e114a3C83',
    'LINK':'0xE4D3c96be03C6a33e3629C62832B0a07e3282d20',
    'AAVE':'0xA700b4eB416Be35b2911fd5Dee80678ff64fF6C9',
    'OP':'0xE40D88d2B7D4b4F36CC5be8B5D2AcD09F0ADf89A',
    'ARB':'0x1d8E01188C4B89d87f89391909f67e4c23dd1475',
    'MATIC':'0x70B20D26A3C2AF28efE2Be87AA3fDB5f5d3FE5Ac',
    'LDO':'0x6Fd7c98458a943f469E1Cf4eA85B173f5Cd342F4',
    'RPL':'0xDB9AAE6B7A01E4F64c870c5571E07c0CFbA4C7C9',
    'PEPE':'0x52b492a33E447Cdb854c7FC19F1e57E8BfA1777D',
    'SHIB':'0x5f7d9B0578e2ac58ABe9d12E7498A96d94DEbDcE',
    'FLOKI':'0x66B6a0B67C5c85a3b0b9fe3b6A2E71C3c9e2cA2F',
    'BONK':'0x1a1B2C76E3B4c7a7C8e9aB1234567890AbcDef12',
    'TURBO':'0xBA5ECC1A45Ac12fAca5e9E0F64f5D3E2A9C89b7C',
    'WOJAK':'0xA47aB61A57ccBB52e7a4c64F0D7e5b4f8E0d1234',
    'MOG':'0x2Da56AcB9Ea78330f947bD57C54119Debda7AF71',
    'HIGHER':'0x0578d8A44db98B23BF096A382e016e29a5Ce0ffe',
    'DEGEN2':'0x4ed4E862860beD51a9570b96d89aF5E1B0Efefed',
    'NORMIE2':'0x7f12d13B34f5F4f0a9449c89bC4B4a9b8AF95bab',
    'KEYCAT':'0x9a26F5433671751C3276a065f57e5a02D2817973',
    'SKIDOG':'0xEc898b14aE4Ce0dB2f47cdE0AeE1Fc0dce0caa9',
    'WDOG':'0xBEC04a7C6CB42a4A6C49f226De35f4d7cA0acE72',
    'PATO':'0x20F8Fd6e29F5d45B803A3af47B7C9B93f9e2b6cA',
    'CRYPTO':'0x23a4A67d2Ff9C00C1f8E3E87CEB8E34B51C67B71',
    'LUNA2':'0x2D8Cd5F6B4Cb1B5DA8E14B3E5D3E4B8E70fAa6C',
    'HARAMBE':'0xD9Ce2b3DcF5f2d8a26d8e9E7c3B9D5b6E4f1c2A',
    'BOGE':'0xaBcDEf0123456789AbcDEf0123456789abcDEF01',
    # Broader DeFi
    'MKR':'0xAF22b8cA2fC5cAf1FBf0b33Ca0a4c6CAaDEC9F52',
    'FRAX':'0xbB8F5B2FAcBF6e7FB7bE3D93fc9fD64B1d50E75d',
    'FXS':'0xd9aAEb55a4A97f5f71B8D3c36Ba3e5dd0E42C09C',
    'SPELL':'0x56A9b48a7bfBe4E3CBef03a8C1Ca8E91c9CB4BfC',
    'SUSHI':'0x7D14B3A63B6D9F6Bd06Ce5D3D5E5A5E5B5C5D5E5',
    'CVX':'0x3bB4445D30AC020a84c1b5A8A2C6248ebC9779D7',
    'ALCX':'0xc21223249CA28397B4B6541dfFaEcC539BfF0c59',
    'INV':'0x365AccFCa291e7D3914637ABf1F7635dB165Bb09',
    'BTRFLY':'0x9a5E6F60E4B678b5CE4D0E62b3E6B1A6B7b8F9Aa',
    'OHM':'0xd9EF3C52C8C6A78E7C4F9a7B4E1D3B5A7C9E1F3B',
    'KLIMA':'0x4A1b0CDAe3c3c6b7B5D1E2F0A3B8C9D4E5F6A7B8',
    'TOKE':'0x5E4b3A7c8D1F2E0B6C9A4D3F7E8B2C1D5A6F7E8B',
}

ALL_TOKEN_SYM = {v.lower(): k for k, v in QUOTE_TOKENS.items()}


def _sort_tokens(a, b):
    return (a, b) if int(a, 16) < int(b, 16) else (b, a)

def _enc_get_pair(a, b):
    return SEL_GET_PAIR + bytes.fromhex(a[2:].lower().zfill(64)) + bytes.fromhex(b[2:].lower().zfill(64))

def _dec_addr(data):
    return '0x' + data[12:32].hex() if len(data) >= 32 else NULL_ADDR


class BaseScanner:
    """Base network scanner — identical architecture to all other EVM scanners."""

    def __init__(self, testnet: bool = False):
        self.testnet           = testnet
        self.w3: Optional[Web3]= None
        self._mc               = None
        self._pair_cache: dict = {}
        self._last_eth_price   = 3500.0
        self._last_eth_update  = 0
        self._connect()

    @property
    def _rpc_list(self):
        env_key = 'BASE_TESTNET_RPC_URL' if self.testnet else 'BASE_RPC_URL'
        env_val = os.environ.get(env_key, '')
        base    = BASE_TESTNET_RPC if self.testnet else BASE_MAINNET_RPC
        return ([env_val] if env_val else []) + base

    @property
    def _base_tokens(self):
        return BASE_TOKENS_TESTNET if self.testnet else BASE_TOKENS_MAINNET

    @property
    def _flash_providers(self):
        return FLASH_PROVIDERS_TESTNET if self.testnet else FLASH_PROVIDERS_MAINNET

    @property
    def _dex_configs(self):
        if self.testnet:
            return {k: v for k, v in DEX_CONFIGS.items() if 'Sepolia' in k}
        return {k: v for k, v in DEX_CONFIGS.items() if 'Sepolia' not in k}

    def _connect(self):
        for url in self._rpc_list:
            try:
                w3 = Web3(Web3.HTTPProvider(url, request_kwargs={'timeout': 20}))
                if w3.is_connected():
                    self.w3  = w3
                    self._mc = w3.eth.contract(address=Web3.to_checksum_address(MULTICALL3_ADDR), abi=MULTICALL3_ABI)
                    logger.info(f"Base {'Testnet' if self.testnet else 'Mainnet'} connected via {url}")
                    return
            except Exception as e:
                logger.warning(f"Base RPC {url} failed: {e}")
        logger.error("All Base RPCs failed")

    def _ensure_connected(self):
        if not self.w3 or not self.w3.is_connected():
            self._connect()
        return self.w3 is not None

    def _multicall(self, calls):
        if not calls or not self._mc:
            return []
        results = []
        for i in range(0, len(calls), 200):
            chunk    = calls[i:i+200]
            mc_calls = [(Web3.to_checksum_address(t.lower()), True, cd) for t, cd in chunk]
            try:
                results.extend(self._mc.functions.aggregate3(mc_calls).call())
            except Exception as e:
                logger.warning(f"Base Multicall chunk {i//200} failed: {e}")
                results.extend([(False, b'')] * len(chunk))
        return results

    def _select_flash_provider(self, base_token_sym: str, loan_amount_wei: int) -> dict:
        for provider in self._flash_providers:
            try:
                pool = provider.get('pool', '')
                if not pool or pool == NULL_ADDR:
                    return provider
                results = self._multicall([(pool, SEL_GET_RESERVES)])
                if results and results[0][0] and len(results[0][1]) >= 64:
                    r0 = int.from_bytes(results[0][1][0:32], 'big')
                    r1 = int.from_bytes(results[0][1][32:64], 'big')
                    if r0 >= loan_amount_wei or r1 >= loan_amount_wei:
                        return provider
                else:
                    return provider
            except Exception:
                return provider
        return self._flash_providers[0]

    def _get_eth_price(self):
        now = time.time()
        if now - self._last_eth_update < 120 or self.testnet:
            return self._last_eth_price
        try:
            factory = self._dex_configs.get('BaseSwap', {}).get('factory', '')
            weth    = self._base_tokens.get('WETH', '').lower()
            usdc    = self._base_tokens.get('USDC', '').lower()
            if factory and weth and usdc:
                results = self._multicall([(factory, _enc_get_pair(weth, usdc))])
                if results and results[0][0]:
                    pool = _dec_addr(results[0][1]).lower()
                    if pool != NULL_ADDR:
                        res = self._fetch_reserves([pool])
                        if pool in res:
                            r0, r1 = res[pool]
                            t0, _  = _sort_tokens(weth, usdc)
                            price  = (r1 / 1e6) / (r0 / 1e18) if t0 == weth else (r0 / 1e6) / (r1 / 1e18)
                            if 500 < price < 20000:
                                self._last_eth_price  = price
                                self._last_eth_update = now
        except Exception as e:
            logger.warning(f"Base ETH price error: {e}")
        return self._last_eth_price

    def _get_gas_price_gwei(self):
        try:
            return max(0.001, min(2.0, float(self.w3.eth.gas_price / 1e9)))
        except Exception:
            return 0.005

    def _fetch_reserves(self, pool_addrs):
        calls   = [(addr, SEL_GET_RESERVES) for addr in pool_addrs]
        results = self._multicall(calls)
        reserves= {}
        for i, (ok, data) in enumerate(results):
            if ok and len(data) >= 64:
                r0, r1 = int.from_bytes(data[0:32],'big'), int.from_bytes(data[32:64],'big')
                if r0 > 0 and r1 > 0:
                    reserves[pool_addrs[i].lower()] = (r0, r1)
        return reserves

    def _discover_pools(self, base_tokens, selected_dexes):
        dex_cfgs   = {d: self._dex_configs[d] for d in selected_dexes if d in self._dex_configs}
        base_addrs = {s: self._base_tokens[s].lower() for s in base_tokens if s in self._base_tokens}
        quote_src  = QUOTE_TOKENS if not self.testnet else {}

        to_discover = []
        for sym, base_addr in base_addrs.items():
            for q_addr_raw in quote_src.values():
                q_addr = q_addr_raw.lower()
                for dex, dex_cfg in dex_cfgs.items():
                    key = (base_addr, q_addr, dex)
                    if key not in self._pair_cache:
                        to_discover.append((base_addr, q_addr, dex, dex_cfg['factory'], key))

        if to_discover:
            calls   = [(item[3], _enc_get_pair(item[0], item[1])) for item in to_discover]
            results = self._multicall(calls)
            found   = 0
            for i, (ok, data) in enumerate(results):
                key = to_discover[i][4]
                if ok and len(data) >= 32:
                    addr = _dec_addr(data).lower()
                    self._pair_cache[key] = addr
                    if addr != NULL_ADDR:
                        found += 1
                else:
                    self._pair_cache[key] = NULL_ADDR
            logger.info(f"Base Discovery: {found} pools from {len(calls)} queries")

        return {k: v for k, v in self._pair_cache.items() if v != NULL_ADDR}

    def scan(self, config: dict) -> dict:
        if not self._ensure_connected():
            return {'opportunities':[],'total':0,'profitable':0,'best_profit_usd':0,'avg_spread':0,'error':'Cannot connect to Base RPC'}

        min_net_pct    = float(config.get('minNetProfitPct', 0.05))
        min_liq_usd    = float(config.get('minLiquidityUsd', 2000))
        selected_dexes = [d for d in config.get('dexes', []) if d in self._dex_configs]
        base_tokens    = config.get('baseTokens', list(self._base_tokens.keys()))

        eth_price = self._get_eth_price()
        gas_gwei  = self._get_gas_price_gwei()
        gas_usd   = (300_000 * gas_gwei * 1e-9) * eth_price
        logger.info(f"Base Gas: {gas_gwei:.4f} gwei, ETH ${eth_price:.0f} → gas ${gas_usd:.4f}")

        pool_map = self._discover_pools(base_tokens, selected_dexes)
        if not pool_map:
            return {'opportunities':[],'total':0,'profitable':0,'best_profit_usd':0,'avg_spread':0}

        reserves_map = self._fetch_reserves(list(set(pool_map.values())))
        pair_data: dict = {}

        for (base_low, quote_low, dex), pool_addr in pool_map.items():
            pool_low = pool_addr.lower()
            if pool_low not in reserves_map:
                continue
            r0, r1    = reserves_map[pool_low]
            base_sym  = next((s for s, a in self._base_tokens.items() if a.lower() == base_low), None)
            if not base_sym or base_sym not in base_tokens:
                continue
            t0, _     = _sort_tokens(base_low, quote_low)
            decimals_base = 6 if base_sym in ('USDC','USDbC','DAI') else 18
            r_base, r_quote = (r0, r1) if t0 == base_low else (r1, r0)
            quote_sym = ALL_TOKEN_SYM.get(quote_low, quote_low[:8])
            price_usd = BASE_PRICE_USD.get(base_sym, 1.0)
            liq_usd   = (r_base / (10 ** decimals_base)) * price_usd * 2
            if liq_usd < min_liq_usd:
                continue
            pair_key = f"{quote_sym}/{base_sym}"
            if pair_key not in pair_data:
                pair_data[pair_key] = {'base_sym':base_sym,'quote_sym':quote_sym,'base_low':base_low,'quote_low':quote_low,'price_usd':price_usd,'decimals_base':decimals_base,'dexes':{}}
            pair_data[pair_key]['dexes'][dex] = {
                'r_base':r_base,'r_quote':r_quote,'liq_usd':liq_usd,
                'fee_bps':self._dex_configs[dex]['fee_bps'],'router':self._dex_configs[dex]['router'],
            }

        pairs_multi = {k: v for k, v in pair_data.items() if len(v['dexes']) >= 2}
        logger.info(f"Base arb candidates: {len(pairs_multi)}")

        opportunities = []

        for pair_key, pdata in pairs_multi.items():
            dex_names     = list(pdata['dexes'].keys())
            price_usd     = pdata['price_usd']
            decimals_base = pdata.get('decimals_base', 18)

            for i in range(len(dex_names)):
                for j in range(len(dex_names)):
                    if i == j:
                        continue
                    buy_dex, sell_dex = dex_names[i], dex_names[j]
                    bd, sd = pdata['dexes'][buy_dex], pdata['dexes'][sell_dex]
                    if bd['r_base'] == 0 or sd['r_base'] == 0:
                        continue
                    buy_spot  = bd['r_quote'] / bd['r_base']
                    sell_spot = sd['r_quote'] / sd['r_base']
                    if buy_spot <= 0 or sell_spot <= 0:
                        continue
                    spread = ((buy_spot - sell_spot) / sell_spot) * 100
                    if spread <= 0:
                        continue

                    est_loan_usd  = max(gas_usd / max(spread / 100 - 0.003, 0.0001), 500)
                    est_loan_wei  = int((est_loan_usd / price_usd) * (10 ** decimals_base))
                    provider      = self._select_flash_provider(pdata['base_sym'], est_loan_wei)
                    flash_fee_bps = provider['fee_bps']
                    fee_hurdle    = (flash_fee_bps + bd['fee_bps'] + sd['fee_bps']) / 100
                    if spread - fee_hurdle < -2.0:
                        continue

                    result = find_optimal_trade_size(
                        reserve_buy_in=bd['r_base'], reserve_buy_out=bd['r_quote'],
                        reserve_sell_in=sd['r_quote'], reserve_sell_out=sd['r_base'],
                        fee_buy_bps=bd['fee_bps'], fee_sell_bps=sd['fee_bps'],
                        flash_fee_bps=flash_fee_bps, max_price_impact_pct=3.0,
                        decimals_base=decimals_base, gas_usd=gas_usd, base_price_usd=price_usd,
                    )

                    raw_amount = result.get('optimal_amount', 0)
                    if raw_amount > 0:
                        display_loan = raw_amount
                    else:
                        net_sp = spread - fee_hurdle
                        display_loan = int((gas_usd / (net_sp / 100) / price_usd) * (10 ** decimals_base)) if net_sp > 0.001 else int(gas_usd / price_usd * (10 ** decimals_base))
                        max_disp = min(int(bd['r_base'] * 0.03), int(sd['r_base'] * 0.03))
                        if max_disp > 0:
                            display_loan = min(display_loan, max_disp)

                    loan_tok = display_loan / (10 ** decimals_base)
                    loan_usd = loan_tok * price_usd
                    _q       = get_amount_out_v2(display_loan, bd['r_base'], bd['r_quote'], bd['fee_bps'])
                    _out     = get_amount_out_v2(_q, sd['r_quote'], sd['r_base'], sd['fee_bps'])
                    _flash   = (display_loan * flash_fee_bps) // 10000

                    gross_tok     = (display_loan * spread / 100) / (10 ** decimals_base)
                    gross_usd     = gross_tok * price_usd
                    actual_net_raw= _out - display_loan - _flash
                    net_tok_raw   = actual_net_raw / (10 ** decimals_base)
                    net_usd_raw   = net_tok_raw * price_usd - gas_usd
                    net_usd       = net_usd_raw if net_usd_raw >= 0 else -gas_usd
                    net_tok       = net_tok_raw if net_usd_raw >= 0 else (-gas_usd / price_usd if price_usd > 0 else 0)
                    net_pct       = (net_tok_raw / loan_tok * 100) if loan_tok > 0 else 0

                    flash_fee_usd = loan_usd * (flash_fee_bps / 10000)
                    buy_fee_usd   = loan_usd * (bd['fee_bps'] / 10000)
                    sell_fee_usd  = (loan_usd + gross_usd) * (sd['fee_bps'] / 10000)
                    buy_impact    = calc_price_impact(display_loan, bd['r_base'])
                    sell_impact   = calc_price_impact(_q, sd['r_quote']) if _q > 0 else 0.0

                    is_profitable = result.get('profitable', False) and net_usd > 0 and net_pct >= min_net_pct
                    status = 'profitable' if is_profitable else ('marginal' if gross_usd > 0 and net_usd > -gas_usd * 2 else 'unprofitable')

                    opportunities.append({
                        'id':                f"base_{pdata['quote_sym']}_{pdata['base_sym']}_{buy_dex}_{sell_dex}_{int(time.time())}",
                        'pair':              pair_key,
                        'baseToken':         pdata['base_sym'],
                        'quoteToken':        pdata['quote_sym'],
                        'baseTokenAddress':  pdata['base_low'],
                        'quoteTokenAddress': pdata['quote_low'],
                        'buyDex':            buy_dex,
                        'sellDex':           sell_dex,
                        'buyDexRouter':      bd['router'],
                        'sellDexRouter':     sd['router'],
                        'buyPrice':          round(bd['r_base'] / bd['r_quote'], 10) if bd['r_quote'] else 0,
                        'sellPrice':         round(sd['r_base'] / sd['r_quote'], 10) if sd['r_quote'] else 0,
                        'spread':            round(spread, 4),
                        'flashLoanAsset':    pdata['base_sym'],
                        'flashLoanAmount':   round(loan_tok, 6),
                        'flashLoanAmountUsd':round(loan_usd, 2),
                        'flashLoanProvider': provider['name'],
                        'flashLoanPool':     provider.get('pool', ''),
                        'grossProfit':       round(gross_tok, 6),
                        'grossProfitUsd':    round(gross_usd, 2),
                        'netProfit':         round(net_tok, 6),
                        'netProfitUsd':      round(net_usd, 2),
                        'gasFee':            round(gas_usd, 4),
                        'dexFees':           round(buy_fee_usd + sell_fee_usd, 2),
                        'flashFee':          round(flash_fee_usd, 2),
                        'netProfitPct':      round(net_pct, 4),
                        'buyPoolLiquidity':  round(bd['liq_usd'], 0),
                        'sellPoolLiquidity': round(sd['liq_usd'], 0),
                        'buyPriceImpact':    round(buy_impact, 4),
                        'sellPriceImpact':   round(sell_impact, 4),
                        'status':            status,
                        'testnet':           self.testnet,
                        'timestamp':         int(time.time()),
                    })

        gc.collect()
        opportunities.sort(key=lambda x: x['netProfitUsd'], reverse=True)
        profitable = [o for o in opportunities if o['netProfitUsd'] > 0]
        avg_spread = sum(o['spread'] for o in opportunities) / len(opportunities) if opportunities else 0

        return {
            'opportunities':    opportunities,
            'total':            len(opportunities),
            'profitable':       len(profitable),
            'best_profit_usd':  opportunities[0]['netProfitUsd'] if opportunities else 0,
            'avg_spread':       round(avg_spread, 4),
            'eth_price':        eth_price,
            'gas_estimate_usd': round(gas_usd, 4),
            'scan_timestamp':   int(time.time()),
        }

    def execute_trade(self, opportunity: dict, wallet_address: str, contract_address: str) -> dict:
        try:
            contract   = self.w3.eth.contract(address=Web3.to_checksum_address(contract_address.lower()), abi=FLASH_ARB_ABI)
            base_addr  = Web3.to_checksum_address(opportunity['baseTokenAddress'].lower())
            quote_addr = Web3.to_checksum_address(opportunity['quoteTokenAddress'].lower())
            flash_amt  = int(opportunity['flashLoanAmount'] * 1e18)
            min_profit = int(opportunity.get('netProfit', 0) * 0.9 * 1e18)
            deadline   = int(time.time()) + 180
            tx = contract.functions.executeArbitrage(
                base_addr, flash_amt,
                Web3.to_checksum_address(opportunity['buyDexRouter'].lower()),
                Web3.to_checksum_address(opportunity['sellDexRouter'].lower()),
                [base_addr, quote_addr], [quote_addr, base_addr],
                min_profit, deadline,
            ).build_transaction({
                'from': Web3.to_checksum_address(wallet_address.lower()),
                'gas': 400000,
                'gasPrice': self.w3.eth.gas_price,
                'nonce': self.w3.eth.get_transaction_count(Web3.to_checksum_address(wallet_address.lower())),
            })
            chain_id = 84532 if self.testnet else 8453
            return {'status':'ready','unsignedTx':{'to':tx['to'],'data':tx['data'],'gas':hex(tx['gas']),'gasPrice':hex(tx['gasPrice']),'nonce':hex(tx['nonce']),'value':'0x0','chainId':chain_id}}
        except Exception as e:
            return {'status':'error','error':str(e)}
