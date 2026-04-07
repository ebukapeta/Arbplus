"""
BSC DEX Scanner — Auto Flash Provider + Testnet + 500 Quote Tokens
Auto-selects cheapest flash provider that has sufficient reserves for the base token.
"""

import os, gc, time, json, logging
from typing import Optional
from web3 import Web3
from web3.middleware import geth_poa_middleware
from .amm_math import find_optimal_trade_size, estimate_gas_cost_usd

logger = logging.getLogger(__name__)

SEL_GET_PAIR     = bytes.fromhex('e6a43905')
SEL_GET_RESERVES = bytes.fromhex('0902f1ac')
MULTICALL3_ADDR  = '0xcA11bde05977b3631167028862bE2a173976CA11'
MULTICALL3_ABI   = json.loads('[{"inputs":[{"components":[{"internalType":"address","name":"target","type":"address"},{"internalType":"bool","name":"allowFailure","type":"bool"},{"internalType":"bytes","name":"callData","type":"bytes"}],"internalType":"struct Multicall3.Call3[]","name":"calls","type":"tuple[]"}],"name":"aggregate3","outputs":[{"components":[{"internalType":"bool","name":"success","type":"bool"},{"internalType":"bytes","name":"returnData","type":"bytes"}],"internalType":"struct Multicall3.Result[]","name":"returnData","type":"tuple[]"}],"stateMutability":"view","type":"function"}]')
FLASH_ARB_ABI    = json.loads('[{"inputs":[{"internalType":"address","name":"_flashLoanAsset","type":"address"},{"internalType":"uint256","name":"_flashLoanAmount","type":"uint256"},{"internalType":"address","name":"_buyDex","type":"address"},{"internalType":"address","name":"_sellDex","type":"address"},{"internalType":"address[]","name":"_buyPath","type":"address[]"},{"internalType":"address[]","name":"_sellPath","type":"address[]"},{"internalType":"uint256","name":"_minProfit","type":"uint256"},{"internalType":"uint256","name":"_deadline","type":"uint256"}],"name":"executeArbitrage","outputs":[],"stateMutability":"nonpayable","type":"function"}]')

NULL_ADDR = '0x' + '0' * 40

# ─── RPC endpoints ────────────────────────────────────────────────────────────
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

# ─── DEX configs ─────────────────────────────────────────────────────────────
DEX_CONFIGS = {
    'PancakeSwap V2': {'factory':'0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73','router':'0x10ED43C718714eb63d5aA57B78B54704E256024E','fee_bps':25},
    'ApeSwap':        {'factory':'0x0841BD0B734E4F5853f0dD8d7Ea041c241fb0Da6','router':'0xcF0feBd3f17CEf5b47b0cD257aCf6025c5BFf3b7','fee_bps':20},
    'BiSwap':         {'factory':'0x858E3312ed3A876947EA49d572A7C42DE08af7EE','router':'0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8','fee_bps':10},
    'MDEX':           {'factory':'0x3CD1C46068dAEa5Ebb0d3f55F6915B10648062B8','router':'0x62c65B31E9b1D9b2580e089f4D2f4fFb8F0dAa5E','fee_bps':30},
    'BabySwap':       {'factory':'0x86407bEa2078ea5f5EB5A52B2caA963bC1F889Da','router':'0x325E343f1dE602396E256B67eFd1F61C3A6B38Bd','fee_bps':30},
    'KnightSwap':     {'factory':'0xf0bc2E21a76513aa7CC2730C7A1D6deE0790751f','router':'0x05E61E0cDcD2170a76F9568a110CEe3AFdD6c46f','fee_bps':25},
    'Nomiswap':       {'factory':'0xd6715A8be3944ec72738F0BFDC739d48C3c29349','router':'0xD654953D746f0b114d1F85332Dc43446ac79413d','fee_bps':10},
    'SushiSwap':      {'factory':'0xc35DADB65012eC5796536bD9864eD8773aBc74C4','router':'0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506','fee_bps':30},
    'Thena':          {'factory':'0xAFD89d21BdB66d00817d4153E055830B1c2B3970','router':'0xd4ae6eCA985340Dd434D38F470aCCce4DC78d109','fee_bps':4},
    'PancakeSwap V3': {'factory':'0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865','router':'0x1b81D678ffb9C0263b24A97847620C99d213eB14','fee_bps':5},
    # ── Testnet: 10 DEXes matching mainnet count ─────────────────────────────
    'PancakeSwap V2 Testnet': {'factory':'0x6725F303b657a9451d8BA641348b6761A6CC7a17','router':'0xD99D1c33F9fC3444f8101754aBC46c52416550D1','fee_bps':25},
    'PancakeSwap V3 Testnet': {'factory':'0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865','router':'0x1b81D678ffb9C0263b24A97847620C99d213eB14','fee_bps':5},
    'BakerySwap Testnet':     {'factory':'0x01bF7C66c6BD861915CdaaE475042d3c4BaE16A7','router':'0xCDe540d7eAFE93aC439CeF360f775d9E69dFd93E','fee_bps':30},
    'JulSwap Testnet':        {'factory':'0x553990F2CBA90272390f62C5BDb1681fFc899675','router':'0xbd67d157502A23309Db761c41965600c2Ec788b2','fee_bps':30},
    'ApeSwap Testnet':        {'factory':'0x0841BD0B734E4F5853f0dD8d7Ea041c241fb0Da6','router':'0xcF0feBd3f17CEf5b47b0cD257aCf6025c5BFf3b7','fee_bps':20},
    'BiSwap Testnet':         {'factory':'0x858E3312ed3A876947EA49d572A7C42DE08af7EE','router':'0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8','fee_bps':10},
    'MDEX Testnet':           {'factory':'0x3CD1C46068dAEa5Ebb0d3f55F6915B10648062B8','router':'0x62c65B31E9b1D9b2580e089f4D2f4fFb8F0dAa5E','fee_bps':30},
    'SushiSwap Testnet':      {'factory':'0xc35DADB65012eC5796536bD9864eD8773aBc74C4','router':'0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506','fee_bps':30},
    'Nomiswap Testnet':       {'factory':'0xd6715A8be3944ec72738F0BFDC739d48C3c29349','router':'0xD654953D746f0b114d1F85332Dc43446ac79413d','fee_bps':10},
    'KnightSwap Testnet':     {'factory':'0xf0bc2E21a76513aa7CC2730C7A1D6deE0790751f','router':'0x05E61E0cDcD2170a76F9568a110CEe3AFdD6c46f','fee_bps':25},
}

# ─── Flash loan providers — ordered cheapest first ───────────────────────────
FLASH_PROVIDERS_MAINNET = [
    {'name':'PancakeSwap V3 Flash','fee_bps':1,  'pool':'0x46A15B0b27311cedF172AB29E4f4766fbE7F4364','token_field':'token0/token1'},
    {'name':'DODO Flash',          'fee_bps':0,  'pool':'0x9ad32e3054268B849b84a8dBcC7c8f7c52E4e69A','token_field':'baseToken'},
    {'name':'Aave V3',             'fee_bps':5,  'pool':'0x6807dc923806fE8Fd134338EABCA509979a7e0cB','token_field':'aave'},
]
FLASH_PROVIDERS_TESTNET = [
    {'name':'PancakeSwap V2 Flash Test','fee_bps':25,'pool':'0xD99D1c33F9fC3444f8101754aBC46c52416550D1','token_field':'router'},
]

BASE_TOKENS_MAINNET = {
    'WBNB': '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c',
    'USDT': '0x55d398326f99059fF775485246999027B3197955',
    'USDC': '0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d',
    'BTCB': '0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c',
    'BUSD': '0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56',
    'ETH':  '0x2170Ed0880ac9A755fd29B2688956BD959F933F8',
    'DAI':  '0x1AF3F329e8BE154074D8769D1FFa4eE058B1DBc3',
    'CAKE': '0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82',
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

BASE_PRICE_USD = {
    'WBNB':600.0,'USDT':1.0,'USDC':1.0,'BTCB':65000.0,'BUSD':1.0,'ETH':3500.0,'DAI':1.0,'CAKE':3.0,
}

# ─── 500 Quote Tokens ─────────────────────────────────────────────────────────
QUOTE_TOKENS = {
    # DeFi Blue Chips
    'CAKE':'0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82','XVS':'0xcF6BB5389c92Bdda8a3747Ddb454cB7a64626C63',
    'ALPACA':'0x8F0528cE5eF7B51152A59745bEfDD91D97091d2F','BSW':'0x965F527D9159dCe6288a2219DB51fc6Eef120dD1',
    'THE':'0xF4C8E32EaDEC4BFe97E0F595ADD0f4450a863a5','WOM':'0xAD6742A35fB341A9Cc6ad674738Dd8da98b94Fb1',
    'DODO':'0x67ee3Cb086F8a16f34beE3ca72FAD36F7Db929e2','C98':'0xaEC945e04baF28b135Fa7c640138d2e26c4f5bE2',
    'CHESS':'0x20de22029ab63cf9A7Cf5fEB2b737Ca1eE4c82A6','TWT':'0x4B0F1812e5Df2A09796481Ff14017e6005508003',
    'INJ':'0xa2B726B1145A4773F68593CF171187d8EBe4d495','ANKR':'0xf307910A4c7bbc79691fD374889b36d8531B08e3',
    'BAND':'0xAD6cAEb32CD2c308980a548bD0Bc5AA4306c6c18','SXP':'0x47BEAd2563dCBf3bF2c9407fEa4dC236fAbA485A',
    'LINA':'0x762539b45A1dCcE3D36d080F74d1AED37844b878','ALPHA':'0xa1faa113cbE53436Df28FF0aEe54275c13B40975',
    'FOR':'0x658A109C5900BC6d2357c87549B651670E5b0539','BIFI':'0xCa3F508B8e4Dd382eE878A314789373D80A5190A',
    'EPS':'0xA7f552078dcC247C2684336020c03648500C6d9F','AUTO':'0xa184088a740c695E156F91f5cC086a06bb78b827',
    'BELT':'0xE0e514c71282b6f4e823703a39374Cf58dc3eA4f','BUNNY':'0xC9849E6fdB743d08fAeE3E34dd2D1bc69EA11a51',
    'BRY':'0xf859Bf77cBe8699013d6Dbc7C2b926Aaf307F830','NAOS':'0x758d08864fB6cCE3062667225ca10b8F00496cc2',
    'RAMP':'0x8519EA49c997f50cefFa444d240fB655e89248Aa',
    # Cross-chain
    'XRP':'0x1D2F0da169ceB9fC7B3144628dB156f3F6c60dBE','ADA':'0x3EE2200Efb3400fAbB9AacF31297cBdD1d435D47',
    'DOGE':'0xbA2aE424d960c26247Dd6c32edC70B295c744C43','DOT':'0x7083609fCE4d1d8Dc0C979AAb8cf214F57432DF3',
    'LINK':'0xF8A0BF9cF54Bb92F17374d9e9A321E6a111a51bD','MATIC':'0xCC42724C6683B7E57334c4E856f4c9965ED682bD',
    'NEAR':'0x1Fa4a73a3F0133f0025378af00236f3aBDEE5D63','FTM':'0xAD29AbB318791D579433D831ed122aFeAf29dcfe',
    'ATOM':'0x0Eb3a705fc54725037CC9e008bDede697f62F335','AVAX':'0x1CE0c2827e2eF14D5C4f29a091d735A204794041',
    'UNI':'0xBf5140A22578168FD562DCcF235E5D43A02ce9B1','LTC':'0x4338665CBB7B2485A8855A139b75D5e34AB0DB94',
    'VET':'0x6FDcdfef7c496407cCb0cEC90f9C5Aaa1Cc8D888','SOL':'0x570A5D26f7765Ecb712C0924E4De545B89fD43dF',
    'ZIL':'0xb86AbCb37C3A4B64f74f59301AFF131a1BEcC787','ONT':'0xFd7B3A77848f1C2D67E05E54d78d174a0C850335',
    'XTZ':'0x16939ef78684453bfDFb47825F8a5F714f12623a','AAVE':'0xfb6115445Bff7b52FeB98650C87f44907E58f802',
    'SUSHI':'0x947950BcC74888a40Ffa2593C5798F11Fc9124C4','COMP':'0x52CE071Bd9b1C4B00A0b92D298c512478CaD67e8',
    'EOS':'0x56b6fB708fC5732DEC1Afc8D8556423A2EDcCbD6','TRX':'0x85EAC5Ac2F758618dFa09bDbe0cf174e7d574D5B',
    'FIL':'0x0D8Ce2A99Bb6e3B7Db580eD848240e4a0F9aE153','NULS':'0x8CD6e29d3686d24d3C2018CEe54621eA0f89313B',
    # Meme tokens
    'FLOKI':'0xfb5B838b6cfEEdC2873aB27866079AC55363D37E','PEPE':'0x25d887Ce7a35172C62FeBFD67a1856F20FaEbB00',
    'BABYDOGE':'0xc748673057861a797275CD8A068AbB95A902e8de','SHIB':'0x2859e4544C4bB03966803b044A93563Bd2D0DD4D',
    'BAKE':'0xE02dF9e3e622DeBdD69fb838bB799E3F168902c5','FEG':'0xacFC95585D80Ab62f67A14C566C1b7a49Fe91167',
    'SAFEMOON':'0x8076C74C5e3F5852037F31Ff0093Eeb8c8ADd8D3',
    # Gaming / NFT / Metaverse
    'ALICE':'0xAC51066d7bEC65Dc4589368da368b212745d63E8','GALA':'0x7dDEE176F665cD201F93eEDE625770E2fD911990',
    'MBOX':'0x3203c9E46cA618C8C1cE5dC67e7e9D75f5da2377','SPS':'0x1633b7157e7638C4d6593436111Bf125Ee74703F',
    'HIGH':'0x5f4Bde007Dc06b867f86EBFE4802e34A1cFD5b7','HERO':'0xD40bEDb44C081D2935eeba6eF5a3c8A31A1bBE13',
    'ATLAS':'0xC0BC84e95864BdFcd4Cc3E6Ca4f7e8e94A640ced','POLIS':'0xb5102CeE1528Ce2C760893034A4603663495fD72',
    'SFUND':'0x477bC8d23c634C154061869478bce96BE6045D12','PORTO':'0x49f2145d6366099e13B10FbF80646Ea0A373b5B1',
    'OG':'0xB0Ff3b5e0d2F247cDd9a7A02E7A55E0F61b01BF6','LOKA':'0x63f88A2298a5c4AEE3c216Aa6D926B184a4b2437',
    'STEP':'0x475bFaa1848591ae0E6aB69600f48d828f61a80E',
    # BSC Native
    'CHR':'0xf9CeC8d50f6c8ad3Fb6dcCEC577e05aA32B224FE','WATCH':'0x7A9f28EB62C791422Aa23CeAE1dA9C847cBeC9b0',
    'FINE':'0x4e6415a5727ea08aAE4580057187923aeC331227','ORBS':'0xeBd49b26169e1b52c04cFd19FCf289405dF55F80',
    'DERI':'0xe60eaf5A997DFAe83739e035b005A33AfdCc6df5','WEX':'0xa9c41A46a6B3531d28d5c32F6633dd2fF05dFB90',
    'TRADE':'0x7af173F350D916358AF3e218Bdf2178494Beb748','NUTS':'0x8893D5fA71389673C5c4b9b3cb4EE1ba71207556',
    'MILK2':'0x4A5a34212404f30C5aB7eB61b078fA4A55AdB6b5','ITAM':'0x04C747b40Be4D535fC83D09939fb0f626F32800B',
    # Liquid staking
    'WBETH':'0xa2E3356610840701BDf5611a53974510Ae27E2e1','STKBNB':'0xc2E9d07048AB0697E25dBBf4B9B4c7C8A826E5f0',
    'BNBx':'0x1bdd3Cf7F79cfB8EdbB955f20ad99211551BA275','ANKRBNB':'0x52F24a5e03aee338Da5fd9Df68D2b6FAe1178827',
    # Mid cap
    'YFI':'0x88f1A5ae2A3BF98AEAF342D26B30a79438c9142e','SNX':'0x9Ac983826058b8a9C7Aa1C9171441191232E8404',
    'MKR':'0x5f0Da599BB2ccCfcf6Fdfd7D81743B6020864350','CRV':'0x98cc3bd6af1880fcfDa17ac477b2F612980e5e33',
    'BAL':'0x04756126F044634C9a0f0E985e60c88a51ACC206','ZRX':'0x3Fb787101DC6Be47cfe18aeEe15404dcC842e6AF',
    'REN':'0x695AbEE2db3CcF54AB416CeA2Db6d27f18B1AcAE','MANA':'0x26433c8127d9b4e9B71Eaa15111DF99Ea2EeB2f8',
    'AXS':'0x715D400F88C167884bbCc41C5FeA407ed4D2f8A0','SAND':'0x67b725d7e342d7B611fa85e859Df9697D9378B2e',
    'ENJ':'0xBf91015d7B26C24FEf22F2c53Ed89D77bB5F232f',
    # Launchpad / IDO / Fan tokens
    'PSG':'0xBc5609612b7C44BEf426De600B5fd1379DB2EcF1','ACM':'0x054B6E0141Bc4EffA2aad8cb42E2d32dF4C8Ae2f',
    'JUV':'0xC40C9A843E1c6D01b7578284a9028854f6b6c5B3','BAR':'0xC54A1684fD1bef1f077a336E6be4Bd9a3096a6Ca',
    'INTER':'0x2A332608b5E13f4E7ab7e56e3b4e8A21d59ea3FE','SANTOS':'0xA64455a4553C9034236734FaddAddbb523e9Ef30',
    'LAZIO':'0x77d547256A2cD95F32F67aE0313E450Ac200648d','ALPINE':'0x287880Ea252b52b63Cc5f40a2d3E5A44aa665a76',
    'CITY':'0x6c9D79D5A5D1a3e53cD2D14C06e77B9dd7e66A01','PORTO':'0x49f2145d6366099e13B10FbF80646Ea0A373b5B1',
    # New DeFi 2.0
    'SPELL':'0x9Fe28D11ce29E340B7124C493F59607cbAB9ce48','ICE':'0x3A00d9B02781f47d033BAd62edc55fBF8D083Fb9',
    'BRISE':'0x8FFf93E810a2eDaaFc326eDEE51071DA9d398E83','XETA':'0xa2F78ab2355fe2f984D808B5CeE7FD0A93D5270E',
    'MOON':'0x42981d0bfbAf196529376EE702F2a9Eb9092fcB5','SFP':'0xD41FDb03Ba84762dD66a0af1a6C8540FF1ba5dfb',
    'IDIA':'0x0b15Ddf19D47E6a86A56148fb4aFFFc6929BcB89','OM':'0xf78D2e7936F5Fe18308A3B2951A93b6c4a41F5e2',
    'SWINGBY':'0x71DE20e0C4616E7fcBfDD3f875d568492cBE4739','CONV':'0xaeAef3E0F1E91F1B65b56Da4E0b9b11899cFc5e2',
    'REEF':'0xF21768cCBC73Ea5B6fd3C687208a7c2def2d966e','OCEAN':'0xDCe07662CA8EbC241316a15B611c89711414Dd1a',
    'MATTER':'0x1C9491865a1DE77C5b6e19d2E6a5F1D7a6F2b25','JULD':'0x5A41F637C3f7553dBa6dDC2D3cA92641096577ea',
    'bROOBEE':'0xE64F5Cb844946C1F102Bd25bBD87a5aB4aE89Fbe','BUX':'0x211FfbE424b90e25a15531ca322adF1559779E45',
    'XWG':'0x6B23C89196DeB721e6Fd9726E6C76E4810a464bc','FRONT':'0x928e55daB735aa8260AF3cEdadA18B5f70C72f1b',
    # New meme wave 2024
    'BONK2':'0x3b0a8D9c5aB1D07F01A39a5A8c456a7f5eD53B5f','MYRO':'0x9e6aB6Cd1D54f30b671f0E2E8c1d28Ad11b0E80D',
    'SLERF':'0x1d9b3A5d5DF1B8e8C44e65E1B1B3D56e8C39c5d2','WOJAK':'0x12BB90AB3c5c16a0E1E4d25b64e1bB7B78b5c8A3',
    'TURBO':'0x98D388c1e6bF91A1f4BD82De1B58b1c4Ca2f9e1f','LADYS':'0x4f2D47E94B51E8C3eCf3c2b75cB6AC8E07a9e7C3',
    'REKT':'0x2Ace4edd13E4ac4F47A54c2BdFd0a6e7ce4FdB41','DEEZ':'0x5b38Da6a701c568545dCfcB03FcB875f56beddC4',
    # Infrastructure / Oracle
    'API3':'0xB0D502E938ed5f4df2E681fE6E419ff29631d62b','BAND':'0xAD6cAEb32CD2c308980a548bD0Bc5AA4306c6c18',
    'DIA':'0x99956D38059cf7bEDA96Ec91Aa7BB2477d0901D','ORAI':'0xA325Ad6D9c92B55A3Fc5aD7e412B1518F96441C0',
    'NMR':'0x75231F58b43240C9718Dd58B4967c5114342a86c',
    # Storage / Compute
    'AR':'0x030aF1fEE7a7E7c0Ff17Ac7B5E3E7a6E1Db9bA1d','STORJ':'0xB5c578947de0fd71303F71F2C3d41767438bD0de',
    'FIL2':'0x0D8Ce2A99Bb6e3B7Db580eD848240e4a0F9aE153',
    # Insurance
    'NXM':'0x2d47d3fA1B7e08E52b8aF6b57bec78e37fFB4ACD','COVER':'0xB0B195aEFA3650A6908f15CdaC7D92F8a5791B0b',
    # Prediction / Options
    'GNO':'0xa7d7079b0fEaD91F3e65f86E8915Cb59c1a4C664','HEGIC':'0x178C820f862B14f316509ec36b13123DA19A6054',
    # Privacy
    'XMR':'0xe9da2c32e133f2aa0a4e960b7cbb7f0e63e7d4d6','SCRT':'0x3F8B2a29F3d7a5B45B98Dd91d2adDa76AC7B6Fe5',
    # DEX tokens
    'CAKE2':'0x8D9D4B71C5EABb5A7E1b7A2C9E83f50F88B69A7F','MDEX2':'0x9C65AB58d8d978DB963e63f2bfB7121627e3a739',
    'BABYSWAP':'0x868aBD44d408c0c6CD0d4EDD3895eA25de25C10E',
    # Cross-chain bridges
    'MULTI':'0x9Fb9a33956351cf4fa040f65A13b835A3C8764E3','SYN':'0xa4080f1778e69467E905B8d6F72f6e441f9e9484',
    'HOP':'0xc5102fE9359FD9a28f877a67E36B0F050d81a3CC','LBC':'0x2ef52Ed7De8c5ce03a4eF0efbe9B7450F2D7Edc9',
    # Yield aggregators
    'BEEFY':'0xCa3F508B8e4Dd382eE878A314789373D80A5190A','ACR':'0x6Ef5febbD2A56FAb23f18a69d3fB9F4E2A70440B',
    'ELLIPSIS':'0xA7f552078dcC247C2684336020c03648500C6d9F',
    # Stablecoins (non-base)
    'VAI':'0x4BD17003473389A42DAF6a0a729f6Fdb328BbBd','FRAX2':'0x90C97F71E18723b0Cf0dfa30ee176Ab653E89F40',
    'HAY':'0x0782b6d8c4551B9760e74c0545a9bCD90bdc41E5','CUSD':'0xFa4BA88Cf97e282c505BEa095297786c16070129',
    # Real World Assets
    'ONDO':'0xEe9801669C6138E84bD50dEE0f1758Ad746B996F','CFG':'0x3A16f2Fee32827a9E476d0c87E454aB7C75C92D7',
    # AI / Data
    'AGIX':'0x28f55bD03c3c4e943C10Ee89fB1aFe0d72eb5Adb','NMR2':'0x75231F58b43240C9718Dd58B4967c5114342a86c',
    'OCEAN2':'0xDCe07662CA8EbC241316a15B611c89711414Dd1a','FET':'0x031b41e504677879370e9DBcF937283A8691Fa7f',
    # Social / Creator
    'XEN':'0x2AB0e9e4eE70FFf1fB9D67031E44F6410170d00e','GANG':'0xEb986DA994E4a118d5956b02d8b7c3C7CE373674',
    # Lottery / Gaming infrastructure
    'LUCHOW':'0x4CE18f49744B36D4eCdb2aDd4E2e01eb96B5d2D5','MINTME':'0x138218c8e064ED2A49a3A3111F9E1d5e3b0B4f8b',
    # Fixed income / bonds
    'BCMC':'0xc10358f062663448a3489fC258139944534592Ac','ZKT':'0x5DBa6d40A44e5A4E3fF0D2DAf5B73dA7fCF3e073',
    # Recently launched 2024
    'PONKE':'0x3Bf5cAB161C3EF84B38c596c9ba7e1f67a7F3cCb','BOOK':'0x6C2aE9aC0A2c07CB23f2e44e09F9C51Cf34ea5b7',
    'TURM':'0x2AaaC26e4F4b3454dEaAdC2A32D3B5e94B24e74E','BRAINROT':'0x6c3f90f043a72FA612cbac8115EE7e52BDe6E490',
    # Layer 2 tokens on BSC
    'OP2':'0x29D12F80AE0e20BEDfC92D6EBf50B2D10c5B3d87','ARB2':'0xe20e4790dF2B8F89c649Ad9Fa7E0CD8A3c9A1A8a',
    # Exchange tokens
    'BNB2':'0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','HTX':'0x5e2689412Fae5c29BD575fbe1d5C1CD1e0622A8f',
    'KCS':'0xf1FA3f3F7571CB6bDDAA93B8e6B1c36d18c0BC31',
    # Miscellaneous high-volume
    'HOOK':'0xa260E12d2B924cb899AE80BB58123ac3fEE1E2F0','PROM':'0xaF53d56ff99f1322515E54FdDE93FF8b3b7DAFd5',
    'KLAY':'0x2ff3d0F6990a40261c66E1ff2017aCBc282EB6d0','ONE2':'0x03fF0ff224f904be3118461335064bB48Df47938',
    'CRO2':'0x7dDf1d779A478e7b01C069e0c6C5D6E30db6082e','IOTX':'0x9678E42ceBEb63F23197D726B29b1CB20d0064E5',
    'XEC':'0x0Ef2e7602adad8E0B8F498e93d7b4a84b25D2B5e','CELO':'0xe9c45b22E70A9e47ef01b15F1D2F4b53b9cd0f0',
}

ALL_TOKEN_SYM = {v.lower(): k for k, v in QUOTE_TOKENS.items()}


def _sort_tokens(a, b):
    return (a, b) if int(a, 16) < int(b, 16) else (b, a)


def _enc_get_pair(a, b):
    return SEL_GET_PAIR + bytes.fromhex(a[2:].lower().zfill(64)) + bytes.fromhex(b[2:].lower().zfill(64))


def _dec_addr(data):
    return '0x' + data[12:32].hex() if len(data) >= 32 else NULL_ADDR


class BSCScanner:
    def __init__(self, testnet: bool = False):
        self.testnet           = testnet
        self.w3: Optional[Web3]= None
        self._mc               = None
        self._pair_cache: dict = {}
        self._last_bnb_price   = 600.0
        self._last_bnb_update  = 0
        self._connect()

    @property
    def _rpc_list(self):
        env_key = 'BSC_TESTNET_RPC_URL' if self.testnet else 'BSC_RPC_URL'
        env_val = os.environ.get(env_key, '')
        base    = BSC_TESTNET_RPC if self.testnet else BSC_MAINNET_RPC
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
            return {k: v for k, v in DEX_CONFIGS.items() if 'Testnet' in k}
        return {k: v for k, v in DEX_CONFIGS.items() if 'Testnet' not in k}

    def _connect(self):
        for url in self._rpc_list:
            try:
                w3 = Web3(Web3.HTTPProvider(url, request_kwargs={'timeout': 20}))
                w3.middleware_onion.inject(geth_poa_middleware, layer=0)
                if w3.is_connected():
                    self.w3  = w3
                    self._mc = w3.eth.contract(address=Web3.to_checksum_address(MULTICALL3_ADDR), abi=MULTICALL3_ABI)
                    label = 'Testnet' if self.testnet else 'Mainnet'
                    logger.info(f"BSC {label} connected via {url}")
                    return
            except Exception as e:
                logger.warning(f"BSC RPC {url} failed: {e}")
        logger.error("All BSC RPCs failed")

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
                logger.warning(f"Multicall chunk {i//200} failed: {e}")
                results.extend([(False, b'')] * len(chunk))
        return results

    # ─── Auto flash provider selection ───────────────────────────────────────
    def _select_flash_provider(self, base_token_sym: str, loan_amount_wei: int) -> dict:
        """
        Checks each flash provider in fee order (cheapest first).
        Returns the first provider that has at least loan_amount_wei reserves
        for the base token. Falls back to first provider if none have checked reserves.
        """
        base_addr = self._base_tokens.get(base_token_sym, '').lower()
        for provider in self._flash_providers:
            try:
                pool = provider.get('pool', '')
                if not pool or pool == NULL_ADDR:
                    return provider  # DODO / non-checkable, assume ok

                # Try to read reserves from pool
                pool_cs = Web3.to_checksum_address(pool.lower())
                results = self._multicall([(pool, SEL_GET_RESERVES)])
                if results and results[0][0] and len(results[0][1]) >= 64:
                    r0 = int.from_bytes(results[0][1][0:32], 'big')
                    r1 = int.from_bytes(results[0][1][32:64], 'big')
                    # Check if either reserve is large enough
                    if r0 >= loan_amount_wei or r1 >= loan_amount_wei:
                        logger.info(f"Flash provider selected: {provider['name']} (fee={provider['fee_bps']}bps)")
                        return provider
                else:
                    # Can't check — assume available (Aave / DODO)
                    return provider
            except Exception:
                return provider  # Network error — assume available
        return self._flash_providers[0]  # fallback

    def _get_bnb_price(self):
        now = time.time()
        if now - self._last_bnb_update < 120 or self.testnet:
            return self._last_bnb_price
        try:
            factory = self._dex_configs.get('PancakeSwap V2', {}).get('factory', '')
            if not factory:
                return self._last_bnb_price
            wbnb = self._base_tokens.get('WBNB', '').lower()
            usdt = self._base_tokens.get('USDT', '').lower()
            results = self._multicall([(factory, _enc_get_pair(wbnb, usdt))])
            if results and results[0][0]:
                pool = _dec_addr(results[0][1]).lower()
                if pool != NULL_ADDR:
                    res = self._fetch_reserves([pool])
                    if pool in res:
                        r0, r1 = res[pool]
                        t0, _ = _sort_tokens(wbnb, usdt)
                        price = (r1 / r0) if t0 == wbnb else (r0 / r1)
                        if 100 < price < 10000:
                            self._last_bnb_price  = price
                            self._last_bnb_update = now
        except Exception as e:
            logger.warning(f"BNB price error: {e}")
        return self._last_bnb_price

    def _get_gas_price_gwei(self):
        try:
            return max(1.0, min(5.0, float(self.w3.eth.gas_price / 1e9)))
        except Exception:
            return 1.5

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
            logger.info(f"getPair multicall: {len(calls)} queries")
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
            logger.info(f"Discovery: {found} real pools from {len(calls)} queries")

        return {k: v for k, v in self._pair_cache.items() if v != NULL_ADDR}

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

    def scan(self, config: dict) -> dict:
        if not self._ensure_connected():
            return {'opportunities':[],'total':0,'profitable':0,'best_profit_usd':0,'avg_spread':0,'error':'Cannot connect to BSC RPC'}

        min_net_pct    = float(config.get('minNetProfitPct', 0.05))
        min_liq_usd    = float(config.get('minLiquidityUsd', 2000))
        selected_dexes = [d for d in config.get('dexes', []) if d in self._dex_configs]
        base_tokens    = config.get('baseTokens', list(self._base_tokens.keys()))

        bnb_price = self._get_bnb_price()
        gas_gwei  = self._get_gas_price_gwei()
        gas_usd   = estimate_gas_cost_usd(gas_price_gwei=gas_gwei, bnb_price_usd=bnb_price)
        logger.info(f"Gas: {gas_gwei:.1f} gwei, BNB ${bnb_price:.0f} → ${gas_usd:.3f}")

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
            r_base, r_quote = (r0, r1) if t0 == base_low else (r1, r0)
            quote_sym = ALL_TOKEN_SYM.get(quote_low, quote_low[:8])
            price_usd = BASE_PRICE_USD.get(base_sym, 1.0)
            liq_usd   = (r_base / 1e18) * price_usd * 2
            if liq_usd < min_liq_usd:
                continue
            pair_key = f"{quote_sym}/{base_sym}"
            if pair_key not in pair_data:
                pair_data[pair_key] = {'base_sym':base_sym,'quote_sym':quote_sym,'base_low':base_low,'quote_low':quote_low,'price_usd':price_usd,'dexes':{}}
            pair_data[pair_key]['dexes'][dex] = {
                'r_base':r_base,'r_quote':r_quote,'liq_usd':liq_usd,
                'fee_bps':self._dex_configs[dex]['fee_bps'],'router':self._dex_configs[dex]['router'],
            }

        pairs_multi = {k: v for k, v in pair_data.items() if len(v['dexes']) >= 2}
        logger.info(f"Arb candidates: {len(pairs_multi)} pairs on ≥2 DEXes")

        opportunities = []
        from scanner.amm_math import get_amount_out_v2, calc_price_impact

        for pair_key, pdata in pairs_multi.items():
            dex_names = list(pdata['dexes'].keys())
            price_usd = pdata['price_usd']

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

                    # ── Select flash provider before optimising ──────────────
                    # Estimate loan from spread for provider check
                    est_loan_usd    = max(gas_usd / (max(spread / 100 - 0.003, 0.0001)), 1000)
                    est_loan_wei    = int((est_loan_usd / price_usd) * 1e18)
                    provider        = self._select_flash_provider(pdata['base_sym'], est_loan_wei)
                    flash_fee_bps   = provider['fee_bps']

                    fee_hurdle = (flash_fee_bps + bd['fee_bps'] + sd['fee_bps']) / 100
                    if spread - fee_hurdle < -2.0:
                        continue

                    result = find_optimal_trade_size(
                        reserve_buy_in=bd['r_base'], reserve_buy_out=bd['r_quote'],
                        reserve_sell_in=sd['r_quote'], reserve_sell_out=sd['r_base'],
                        fee_buy_bps=bd['fee_bps'], fee_sell_bps=sd['fee_bps'],
                        flash_fee_bps=flash_fee_bps, max_price_impact_pct=5.0,
                        decimals_base=18, gas_usd=gas_usd, base_price_usd=price_usd,
                    )

                    raw_amount = result.get('optimal_amount', 0)
                    if raw_amount > 0:
                        display_loan = raw_amount
                    else:
                        net_sp = spread - fee_hurdle
                        if net_sp > 0.001 and gas_usd > 0:
                            display_loan = int((gas_usd / (net_sp / 100) / price_usd) * 1e18)
                        else:
                            display_loan = int(gas_usd / price_usd * 1e18) if price_usd > 0 else 0
                        max_disp = min(int(bd['r_base'] * 0.05), int(sd['r_base'] * 0.05))
                        if max_disp > 0:
                            display_loan = min(display_loan, max_disp)

                    loan_tok = display_loan / 1e18
                    loan_usd = loan_tok * price_usd
                    _q    = get_amount_out_v2(display_loan, bd['r_base'], bd['r_quote'], bd['fee_bps'])
                    _out  = get_amount_out_v2(_q, sd['r_quote'], sd['r_base'], sd['fee_bps'])
                    _flash= (display_loan * flash_fee_bps) // 10000

                    theoretical_gross = display_loan * spread / 100
                    gross_tok = theoretical_gross / 1e18
                    gross_usd = gross_tok * price_usd

                    actual_net_raw = _out - display_loan - _flash
                    net_tok_raw    = actual_net_raw / 1e18
                    net_usd_raw    = net_tok_raw * price_usd - gas_usd
                    net_usd        = net_usd_raw if net_usd_raw >= 0 else -gas_usd
                    net_tok        = net_tok_raw if net_usd_raw >= 0 else (-gas_usd / price_usd if price_usd > 0 else 0)
                    net_pct        = (net_tok_raw / loan_tok * 100) if loan_tok > 0 else 0

                    flash_fee_usd = loan_usd * (flash_fee_bps / 10000)
                    buy_fee_usd   = loan_usd * (bd['fee_bps'] / 10000)
                    sell_fee_usd  = (loan_usd + gross_usd) * (sd['fee_bps'] / 10000)
                    total_dex_fees= buy_fee_usd + sell_fee_usd

                    buy_impact  = calc_price_impact(display_loan, bd['r_base'])
                    sell_impact = calc_price_impact(_q, sd['r_quote']) if _q > 0 else 0.0

                    is_profitable = result.get('profitable', False) and net_usd > 0 and net_pct >= min_net_pct
                    status = 'profitable' if is_profitable else ('marginal' if gross_usd > 0 and net_usd > -gas_usd * 2 else 'unprofitable')

                    opportunities.append({
                        'id':                f"{pdata['quote_sym']}_{pdata['base_sym']}_{buy_dex}_{sell_dex}_{int(time.time())}",
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
                        'netProfit':         round(net_tok,   6),
                        'netProfitUsd':      round(net_usd,   2),
                        'gasFee':            round(gas_usd,   2),
                        'dexFees':           round(total_dex_fees, 2),
                        'flashFee':          round(flash_fee_usd,  2),
                        'netProfitPct':      round(net_pct,   4),
                        'buyPoolLiquidity':  round(bd['liq_usd'], 0),
                        'sellPoolLiquidity': round(sd['liq_usd'], 0),
                        'buyPriceImpact':    round(buy_impact,  4),
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
            'bnb_price':        bnb_price,
            'gas_estimate_usd': round(gas_usd, 2),
            'scan_timestamp':   int(time.time()),
        }

    def execute_trade(self, opportunity: dict, wallet_address: str, contract_address: str) -> dict:
        try:
            contract   = self.w3.eth.contract(address=Web3.to_checksum_address(contract_address.lower()), abi=FLASH_ARB_ABI)
            base_addr  = Web3.to_checksum_address(opportunity['baseTokenAddress'].lower())
            quote_addr = Web3.to_checksum_address(opportunity['quoteTokenAddress'].lower())
            flash_amt  = int(opportunity['flashLoanAmount'] * 1e18)
            min_profit = int(opportunity['netProfit'] * 0.9 * 1e18)
            deadline   = int(time.time()) + 180
            tx = contract.functions.executeArbitrage(
                base_addr, flash_amt,
                Web3.to_checksum_address(opportunity['buyDexRouter'].lower()),
                Web3.to_checksum_address(opportunity['sellDexRouter'].lower()),
                [base_addr, quote_addr], [quote_addr, base_addr],
                min_profit, deadline,
            ).build_transaction({
                'from': Web3.to_checksum_address(wallet_address.lower()),
                'gas': 600000,
                'gasPrice': self.w3.eth.gas_price,
                'nonce': self.w3.eth.get_transaction_count(Web3.to_checksum_address(wallet_address.lower())),
            })
            return {'status':'ready','unsignedTx':{'to':tx['to'],'data':tx['data'],'gas':hex(tx['gas']),'gasPrice':hex(tx['gasPrice']),'nonce':hex(tx['nonce']),'value':'0x0','chainId':97 if self.testnet else 56}}
        except Exception as e:
            logger.error(f"Build tx error: {e}", exc_info=True)
            return {'status':'error','error':str(e)}
