"""
Arbitrum DEX Scanner — Same architecture as BSC/ETH Scanner
Auto flash provider: Aave V3 Arb (0.05%) → Camelot Flash → Uniswap V3 Arb Flash
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

ARB_MAINNET_RPC = ['https://arb1.arbitrum.io/rpc','https://rpc.ankr.com/arbitrum','https://arbitrum.llamarpc.com']
ARB_TESTNET_RPC = ['https://sepolia-rollup.arbitrum.io/rpc']

DEX_CONFIGS = {
    'Camelot V2':       {'factory':'0x6EcCab422D763aC031210895C81787E87B43A652','router':'0xc873fEcbd354f5A56E00E710B90EF4201db2448d','fee_bps':30},
    'Uniswap V3 Arb':   {'factory':'0x1F98431c8aD98523631AE4a59f267346ea31F984','router':'0xE592427A0AEce92De3Edee1F18E0157C05861564','fee_bps':5},
    'SushiSwap Arb':    {'factory':'0xc35DADB65012eC5796536bD9864eD8773aBc74C4','router':'0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506','fee_bps':30},
    'Ramses':           {'factory':'0xAAA20D08e59F6561f242b08513D36266C5A29415','router':'0xAAA87963EFeB6f7E0a2711F397663105Acb1805e','fee_bps':20},
    'Trader Joe Arb':   {'factory':'0xaE4EC9901c3076D0DdBe76A520F9E90a6227aCB7','router':'0x5573405636F4b895E511C9CB54329B88BA862000','fee_bps':30},
    'Zyberswap':        {'factory':'0xaC2ee06A14c52570Ef3B9812Ed240BCe359772e7','router':'0xFa58b8024B49836772180f2Df902f231ba712F72','fee_bps':30},
    # Testnet
    'Uniswap V3 Arb Sepolia': {'factory':'0x248AB79Bbb9bC29bB72f7Cd42F17e054Fc40188e','router':'0x101F443B4d1b059569D643917553c771E1b9663A','fee_bps':5},
    'Camelot V2 Testnet':     {'factory':'0x9b4a460da4B3BeDe5b9c86B2B96a5b86503e42e3','router':'0xdf39c8f7B09B9E3B1e3a9Ae78dE5e36E9Ac9EE72','fee_bps':30},
}

FLASH_PROVIDERS_MAINNET = [
    {'name':'Aave V3 Arb',       'fee_bps':5,  'pool':'0x794a61358D6845594F94dc1DB02A252b5b4814aD'},
    {'name':'Uniswap V3 Arb Flash','fee_bps':5, 'pool':'0xC31E54c7a869B9FcBEcc14363CF510d1c41fa443'},
    {'name':'Camelot Flash',     'fee_bps':30,  'pool':'0xaA2BEc2FBaE13e7b2F58dAe32B79A3e8f83E0bE1'},
]
FLASH_PROVIDERS_TESTNET = [
    {'name':'Uniswap V3 Arb Sep Flash','fee_bps':5,'pool':'0x248AB79Bbb9bC29bB72f7Cd42F17e054Fc40188e'},
]

BASE_TOKENS_MAINNET = {
    'WETH':  '0x82aF49447D8a07e3bd95BD0d56f35241523fBab1',
    'USDT':  '0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9',
    'USDC':  '0xaf88d065e77c8cC2239327C5EDb3A432268e5831',
    'DAI':   '0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1',
    'WBTC':  '0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f',
    'ARB':   '0x912CE59144191C1204E64559FE8253a0e49E6548',
    'FRAX':  '0x17FC002b466eEc40DaE837Fc4bE5c67993ddBd6F',
    'GMX':   '0xfc5A1A6EB076a2C7aD06eD22C90d7E710E35ad0a',
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

BASE_PRICE_USD = {
    'WETH':3500.0,'USDT':1.0,'USDC':1.0,'DAI':1.0,'WBTC':65000.0,
    'ARB':1.2,'FRAX':1.0,'GMX':25.0,
}

QUOTE_TOKENS = {
    'GNS':'0x18c11FD286C5EC11c3b683Caa813B77f5163A122','RDNT':'0x3082CC23568eA640225c2467653dB90e9250AaA0',
    'MAGIC':'0x539bdE0d7Dbd336b79148AA742883198BBF60342','JONES':'0x10393c20975cF177a3513071bC110f7962CD67da',
    'STG':'0x6694340fc020c5E6B96567843da2df01b2CE1eb6','BIFI':'0x99C409E5f62E4bd2AC142f17caFb6810B8F0BAAE',
    'PENDLE':'0x0c880f6761F1af8d9Aa9C466984b80DAb9a8c9e8','Y2K':'0x65352B65aA56B7c5E3EAA83E2FD5aA5Ed3E775B4',
    'UMAMI':'0x1622bF67e6e5747b81866fE0b85178a93C7F86e3','PREMIA':'0x51fC0f6660482Ea73330E414eFd7808811a57Fa2',
    'VELA':'0x088cd8f5eF3652623c22D48b1605DCfE860Cd704','HMX':'0x84F5fAeF1BF3F8D44e2B923b45fbe4Cc47E9c380',
    'GRAIL':'0x3d9907F9a368ad0a51Be60f7Da3b97cf940982D8','CAM':'0x7f172E9A2ABFBf3B8D50be92d1dd6FaF0B9bea0d',
    'xGRAIL':'0x3CAaE25Ee616f2C8E13C74dA0813402eae3F496b','MUX':'0x8BB2Ac0DCF1E86550534cEE5E9C8DED4269b679B',
    'CPD':'0xd9016A907Dc0ECfA3ca425ab20B6b785B42F2373','DPEX':'0x1eC789e9Bf685D8B3b72c985E4a59F48B62af11F',
    'LEVEL':'0xB64E280e9D1B5DbEc4AcceDb2257A87b400DB149','MYC':'0xC74fE4c715510Ec2F8C61d70D397B32043F55Abe',
    'PLV':'0x5326E71Ff593Ecc2CF7AcaE5Fe57582D6e74CFF7','OATH':'0x6693Ec7C2DFb0AEBeD9BD7c6E7dc1C1c80B3a8Ff',
    'FST':'0x10010078a54396F62c96dF8532dc2B4847d47ED3','ELITE':'0xbC11E52A3439e62ee61F26eAa8f8dF73Dd33Ea6F',
    'USDC.e':'0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8','USDCe':'0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8',
    'LINK':'0xf97f4df75117a78c1A5a0DBb814Af92458539FB4','UNI':'0xFa7F8980b0f1E64A2062791cc3b0871572f1F7f0',
    'AAVE':'0xba5DdD1f9d7F570dc94a51479a000E3BCE967196','CRV':'0x11cDb42B0EB46D95f990BeDD4695A6e3fA034978',
    'BAL':'0x040d1EdC9569d4Bab2D15287Dc5A4F10F56a56B2','SNX':'0xcBA56Cd8216FCBBF3fA6DF6137F3147cBcA37D60',
    'YFI':'0x82e3A8F066a6989666b031d916c43672085b1582','SUSHI':'0xd4d42F0b6DEF4CE0383636770eF773390d85c61A',
    'COMP':'0x354A6dA3fcde098F8389cad84b0182725c6C91dE','MKR':'0x2e9a897b295fea7905FeD97B5Bc83F84F85218e4',
    'RPL':'0xB766039cc6DB368759C1E56B79AFE5254b4d5fAd','LDO':'0x13Ad51ed4F1B7e9Dc168d8a00cB3f4dDD85EfA60',
    'stETH':'0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84',
    'wstETH':'0x5979D7b546E38E414F7E9822514be443A4800529','rETH':'0xEC70Dcb4A1EFa46b8F2D97C310C9c4790ba5ffA8',
    'PENDLE2':'0x0c880f6761F1af8d9Aa9C466984b80DAb9a8c9e8',
    'GLP':'0x4277f8F2c384827B5273592FF7CeBd9f2C1ac258','esGMX':'0xf42Ae1D54fd613C9bb14810b0588FaAa09a426cA',
    'DOPEX':'0x6C2C06790b3E3E3c38e12Ee22F8183b37a13EE55',
    'USDD':'0x680447595e8B7b3Aa1B43beB9f6098C79ac2Ab3f','MIM':'0xFEa7a6a0B346362BF88A9e4A88416B77a57D6c2A',
    'TUSD':'0x4D15a3A2286D883AF0AA1B3f21367843FAc63E07','LUSD':'0x93b346b6BC2548dA6A1E7d98E9a421B42541425b',
    'DODO':'0x69Eb4FA4a2fbd498C257C57Ea8b7655a2559A581',
    'SPELL':'0x3E6648C5a70A150A88bCE65F4aD4d506Fe15d2AF','TIME':'0xCE2D6d89D939ae1E0e37600FC26B67aFbfEF06F4',
    'BOBA':'0xd2bcd32dE895b40B0FDF27CA959E8DeBA14c2B4b',
    'PEPE':'0x25d887Ce7a35172C62FeBFD67a1856F20FaEbB00','SHIB':'0x5033833c9fe8B9d3E09EEd2f73d2aaF7E3872fd9',
    'FLOKI':'0x6bC3870B29C218f14eCC2ea5cF1a3Aa8917F0DE0','BONK':'0x09199d9A5F4448D0848e4395D065d23DBfA3Cf1b',
    'TURBO':'0x6C45c6Bf3e09F5D3bc00D27b8Ad2F1CAFa930F79',
    'MATIC':'0x561877b6b3DD7651313794e5F2954B714Bd4eB26','SOL':'0x2bcC6D6CdBbDC0a4071e48bb3B969b06B3330c07',
    'AVAX':'0x565609fAF65B92F7be02468acF86f8979423e514','DOT':'0x85F138bfEE4ef8e540895CFb2e8a32a6F4AfFBa9',
    'ADA':'0x3A29dCbB49829Aca42E03F9a0F42aB69B78CF3e7','BNB':'0x20865e63B111B2649ef829EC220536c82C58ad7B',
    'SUI':'0xA1b854be7BDba6Fe5e3AD39B78dB49b0aD61F8FA','APT':'0x11979F28EF5B46E59808CD4B00F0cf7c8b3D7E56',
    'OP':'0xaC23F75a9E8f36e2929C6c9E42B01A0e3A14e2d8','STRK':'0xAFAf52c2D3d9A5d76A75Ae8BCA2dE3bC11da59fF',
    'RNDR':'0xCA72bd4c1feA4C59f0B02BA65C2aC37Ca47e78B8','FET':'0xEC26f1551dCb6BB5B3b42D7b61B82f66dFF9d8B2',
    'AGIX':'0x2e10C3D78c4D9FA50F47C99f5b8f61c2f73A3aAa','WLD':'0x8C4d842A96A3A1B569a5A3a83A97B7b2D98E0862',
}

ALL_TOKEN_SYM = {v.lower(): k for k, v in QUOTE_TOKENS.items()}

def _sort_tokens(a, b):
    return (a, b) if int(a, 16) < int(b, 16) else (b, a)

def _enc_get_pair(a, b):
    return SEL_GET_PAIR + bytes.fromhex(a[2:].lower().zfill(64)) + bytes.fromhex(b[2:].lower().zfill(64))

def _dec_addr(data):
    return '0x' + data[12:32].hex() if len(data) >= 32 else NULL_ADDR


class ArbitrumScanner:
    """Arbitrum scanner — identical architecture to BSC/ETH scanners."""

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
        env_key = 'ARB_TESTNET_RPC_URL' if self.testnet else 'ARB_RPC_URL'
        env_val = os.environ.get(env_key, '')
        base    = ARB_TESTNET_RPC if self.testnet else ARB_MAINNET_RPC
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
            return {k: v for k, v in DEX_CONFIGS.items() if 'Testnet' in k or 'Sepolia' in k}
        return {k: v for k, v in DEX_CONFIGS.items() if 'Testnet' not in k and 'Sepolia' not in k}

    def _connect(self):
        for url in self._rpc_list:
            try:
                w3 = Web3(Web3.HTTPProvider(url, request_kwargs={'timeout': 20}))
                if w3.is_connected():
                    self.w3  = w3
                    self._mc = w3.eth.contract(address=Web3.to_checksum_address(MULTICALL3_ADDR), abi=MULTICALL3_ABI)
                    logger.info(f"Arbitrum {'Testnet' if self.testnet else 'Mainnet'} connected via {url}")
                    return
            except Exception as e:
                logger.warning(f"ARB RPC {url} failed: {e}")
        logger.error("All Arbitrum RPCs failed")

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
                logger.warning(f"ARB Multicall chunk {i//200} failed: {e}")
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
            factory = self._dex_configs.get('Camelot V2', {}).get('factory', '')
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
            logger.warning(f"ARB ETH price error: {e}")
        return self._last_eth_price

    def _get_gas_price_gwei(self):
        try:
            return max(0.01, min(5.0, float(self.w3.eth.gas_price / 1e9)))
        except Exception:
            return 0.1  # Arbitrum is very cheap

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
            logger.info(f"ARB Discovery: {found} pools from {len(calls)} queries")

        return {k: v for k, v in self._pair_cache.items() if v != NULL_ADDR}

    def scan(self, config: dict) -> dict:
        if not self._ensure_connected():
            return {'opportunities':[],'total':0,'profitable':0,'best_profit_usd':0,'avg_spread':0,'error':'Cannot connect to Arbitrum RPC'}

        min_net_pct    = float(config.get('minNetProfitPct', 0.05))
        min_liq_usd    = float(config.get('minLiquidityUsd', 5000))
        selected_dexes = [d for d in config.get('dexes', []) if d in self._dex_configs]
        base_tokens    = config.get('baseTokens', list(self._base_tokens.keys()))

        eth_price = self._get_eth_price()
        gas_gwei  = self._get_gas_price_gwei()
        gas_usd   = (350_000 * gas_gwei * 1e-9) * eth_price
        logger.info(f"ARB Gas: {gas_gwei:.4f} gwei, ETH ${eth_price:.0f} → gas ${gas_usd:.4f}")

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
            decimals_base = 6 if base_sym in ('USDT','USDC') else 18
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
        logger.info(f"ARB arb candidates: {len(pairs_multi)}")

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

                    fee_hurdle = (flash_fee_bps + bd['fee_bps'] + sd['fee_bps']) / 100
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
                        'id':                f"arb_{pdata['quote_sym']}_{pdata['base_sym']}_{buy_dex}_{sell_dex}_{int(time.time())}",
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
                'gas': 500000,
                'gasPrice': self.w3.eth.gas_price,
                'nonce': self.w3.eth.get_transaction_count(Web3.to_checksum_address(wallet_address.lower())),
            })
            chain_id = 421614 if self.testnet else 42161
            return {'status':'ready','unsignedTx':{'to':tx['to'],'data':tx['data'],'gas':hex(tx['gas']),'gasPrice':hex(tx['gasPrice']),'nonce':hex(tx['nonce']),'value':'0x0','chainId':chain_id}}
        except Exception as e:
            return {'status':'error','error':str(e)}
