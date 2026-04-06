"""
Ethereum DEX Scanner — Same architecture as BSC Scanner
Auto flash provider: Balancer V2 Flash (0%) → Uniswap V3 Flash (0.05%) → Aave V3 (0.05%)
Supports mainnet and Sepolia testnet.
"""

import os, gc, time, json, logging
from typing import Optional
from web3 import Web3
from .amm_math import find_optimal_trade_size, estimate_gas_cost_usd, calc_price_impact, get_amount_out_v2

logger = logging.getLogger(__name__)

SEL_GET_PAIR     = bytes.fromhex('e6a43905')
SEL_GET_RESERVES = bytes.fromhex('0902f1ac')
MULTICALL3_ADDR  = '0xcA11bde05977b3631167028862bE2a173976CA11'
MULTICALL3_ABI   = json.loads('[{"inputs":[{"components":[{"internalType":"address","name":"target","type":"address"},{"internalType":"bool","name":"allowFailure","type":"bool"},{"internalType":"bytes","name":"callData","type":"bytes"}],"internalType":"struct Multicall3.Call3[]","name":"calls","type":"tuple[]"}],"name":"aggregate3","outputs":[{"components":[{"internalType":"bool","name":"success","type":"bool"},{"internalType":"bytes","name":"returnData","type":"bytes"}],"internalType":"struct Multicall3.Result[]","name":"returnData","type":"tuple[]"}],"stateMutability":"view","type":"function"}]')
FLASH_ARB_ABI    = json.loads('[{"inputs":[{"internalType":"address","name":"_flashLoanAsset","type":"address"},{"internalType":"uint256","name":"_flashLoanAmount","type":"uint256"},{"internalType":"address","name":"_buyDex","type":"address"},{"internalType":"address","name":"_sellDex","type":"address"},{"internalType":"address[]","name":"_buyPath","type":"address[]"},{"internalType":"address[]","name":"_sellPath","type":"address[]"},{"internalType":"uint256","name":"_minProfit","type":"uint256"},{"internalType":"uint256","name":"_deadline","type":"uint256"}],"name":"executeArbitrage","outputs":[],"stateMutability":"nonpayable","type":"function"}]')

NULL_ADDR = '0x' + '0' * 40

ETH_MAINNET_RPC = ['https://eth.llamarpc.com','https://rpc.ankr.com/eth','https://ethereum.publicnode.com']
ETH_TESTNET_RPC = ['https://rpc.sepolia.org','https://ethereum-sepolia.publicnode.com']

DEX_CONFIGS = {
    'Uniswap V2':         {'factory':'0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f','router':'0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D','fee_bps':30},
    'SushiSwap ETH':      {'factory':'0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac','router':'0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F','fee_bps':30},
    'Shibaswap':          {'factory':'0x115934131916C8b277DD010Ee02de363c09d037c','router':'0x03f7724180AA6b939894B5Ca4314783B0b36b329','fee_bps':30},
    'Fraxswap':           {'factory':'0x43eC799eAdd63848443E2347C49f5f52e8Fe0F6f','router':'0xC14d550632db8592D1243Edc8B95b0Ad06703867','fee_bps':30},
    'PancakeSwap V3 ETH': {'factory':'0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865','router':'0x1b81D678ffb9C0263b24A97847620C99d213eB14','fee_bps':5},
    'Uniswap V3':         {'factory':'0x1F98431c8aD98523631AE4a59f267346ea31F984','router':'0xE592427A0AEce92De3Edee1F18E0157C05861564','fee_bps':5},
    'Balancer V2':        {'factory':'0xBA12222222228d8Ba445958a75a0704d566BF2C8','router':'0xBA12222222228d8Ba445958a75a0704d566BF2C8','fee_bps':15},
    # Testnet
    'Uniswap V2 Sepolia': {'factory':'0xF62c03E08ada871A0bEb309762E260a7a6a880E6','router':'0xeE567Fe1712Faf6149d80dA1E6934E354124CfE3','fee_bps':30},
    'Uniswap V3 Sepolia': {'factory':'0x0227628f3F023bb0B980b67D528571c95c6DaC1c','router':'0x3bFA4769FB09eefC5a80d6E87c3B9C650f7Ae48','fee_bps':5},
}

FLASH_PROVIDERS_MAINNET = [
    {'name':'Balancer V2 Flash','fee_bps':0,  'pool':'0xBA12222222228d8Ba445958a75a0704d566BF2C8'},
    {'name':'Uniswap V3 Flash', 'fee_bps':5,  'pool':'0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640'},
    {'name':'Aave V3 ETH',      'fee_bps':5,  'pool':'0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2'},
]
FLASH_PROVIDERS_TESTNET = [
    {'name':'Uniswap V3 Sepolia Flash','fee_bps':5,'pool':'0x3bFA4769FB09eefC5a80d6E87c3B9C650f7Ae48'},
]

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

BASE_PRICE_USD = {
    'WETH':3500.0,'USDT':1.0,'USDC':1.0,'DAI':1.0,'WBTC':65000.0,
    'FRAX':1.0,'LUSD':1.0,'LINK':15.0,'UNI':8.0,'AAVE':100.0,
}

# ─── 1000 Quote Tokens (Ethereum) ─────────────────────────────────────────────
QUOTE_TOKENS = {
    # Major DeFi
    'SHIB':'0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE','PEPE':'0x6982508145454Ce325dDbE47a25d4ec3d2311933',
    'FLOKI':'0xcf0C122c6b73ff809C693DB761e7BaeBe62b6a2E','BONK2':'0x1151CB3d861920e07a38e03eEAd12C32178567F6',
    'APE':'0x4d224452801ACEd8B2F0aebE155379bb5D594381','BLUR':'0x5283D291DBCF85356A21bA090E6db59121208b44',
    'IMX':'0xF57e7e7C23978C3cAEC3C3548E3D615c346e79fF','SAND':'0x3845badAde8e6dFF049820680d1F14bD3903a5d0',
    'MANA':'0x0F5D2fB29fb7d3CFeE444a200298f468908cC942','AXS':'0xBB0E17EF65F82Ab018d8EDd776e8DD940327B28b',
    'ENJ':'0xF629cBd94d3791C9250152BD8dfBDF380E2a3B9c','ILV':'0x767FE9EDC9E0dF98E07454847909b5E959D7ca0E',
    'GALA2':'0xd1d2Eb1B1e90B638588728b4130137D262C87cae','ALICE2':'0xAC51066d7bEC65Dc4589368da368b212745d63E8',
    # Stablecoins
    'MIM':'0x99D8a9C45b2ecA8864373A26D1459e3Dff1e17F3','GHO':'0x40D16FC0246aD3160Ccc09B8D0D3A2cD28aE6C2f',
    'crvUSD':'0xf939E0A03FB07F59A73314E73794Be0E57ac1b4','PYUSD':'0x6c3ea9036406852006290770BEdFcAbA0e23A0e8',
    'TUSD':'0x0000000000085d4780B73119b644AE5ecd22b376','USDP':'0x8E870D67F660D95d5be530380D0eC0bd388289E1',
    'GUSD':'0x056Fd409E1d7A124BD7017459dFEa2F387b6d5Cd','SUSD':'0x57Ab1ec28D129707052df4dF418D58a2D46d5f51',
    'EURS':'0xdB25f211AB05b1c97D595516F45794528a807ad8','EURT':'0xC581b735A1688071A1746c968e0798D642EDE491',
    'LUSD':'0x5f98805A4E8be255a32880FDeC7F6728C6568bA0','RAI':'0x03ab458634910AaD20eF5f1C8ee96F1D6ac54919',
    # DeFi infrastructure
    'MKR':'0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2','CRV':'0xD533a949740bb3306d119CC777fa900bA034cd52',
    'CVX':'0x4e3FBD56CD56c3e72c1403e103b45Db9da5B9D2B','SNX':'0xC011a73ee8576Fb46F5E1c5751cA3B9Fe0af2a6f',
    'YFI':'0x0bc529c00C6401aEF6D220BE8C6Ea1667F6Ad93e','BAL':'0xba100000625a3754423978a60c9317c58a424e3D',
    'COMP':'0xc00e94Cb662C3520282E6f5717214004A7f26888','GRT':'0xc944E90C64B2c07662A292be6244BDf05Cda44a7',
    'LDO':'0x5A98FcBEA516Cf06857215779Fd812CA3beF1B32','RPL':'0xD33526068D116cE69F19A9ee46F0bd304F21A51f',
    'FXS':'0x3432B6A60D23Ca0dFCa7761B7ab56459D9C964D0','INST':'0x6f40d4A6237C257fff2dB00FA0510DeEECd303eb',
    'ALCX':'0xdBdb4d16EdA451D0503b854CF79D55697F90c8DF','TOKE':'0x2e9d63788249371f1DFC918a52f8d799F4a38C94',
    'SPELL':'0x090185f2135308BaD17527004364eBcC2D37e5F','ICE2':'0xf16e81dce15B08F326220742020379B855B87DF9',
    'FLOAT':'0xb05097849BCA421A3f51B249BA6CCa4aF98B590F',
    # Liquid staking
    'stETH':'0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84','wstETH':'0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0',
    'rETH':'0xae78736Cd615f374D3085123A210448E74Fc6393','cbETH':'0xBe9895146f7AF43049ca1c1AE358B0541Ea49704',
    'frxETH':'0x5E8422345238F34275888049021821E8E08CAa1f','sfrxETH':'0xac3E018457B222d93114458476f3E3416Abbe38F',
    'ankrETH':'0xE95A203B1a91a908F9B9CE46459d101078c2c3cb','swETH':'0xf951E335afb289353dc249e82926178EaC7DEd78',
    'ETHX':'0xA35b1B31Ce002FBF2058D22F30f95D405200A15b',
    # Layer 2 tokens
    'ARB':'0xB50721BCf8d664c30412Cfbc6cf7a15145234ad1','OP':'0x4200000000000000000000000000000000000042',
    'MATIC':'0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0','IMX2':'0xF57e7e7C23978C3cAEC3C3548E3D615c346e79fF',
    'METIS':'0x9E32b13ce7f2E80A01932B42553652E053D6ed8e','BOBA':'0x42bBFa2e77757C645eeaAd1655E0911a7553Efbc',
    'CELO':'0x3294395e62F4eB6aF3f1Fcf89f5602D90Fb3Ef69','GLMR':'0x3D9285E5Ec20dCe88C9Fd7D8c0e97B8B7dFC2e6F',
    'MOVR':'0x65Ef703f5594D2573eb71Aaf55BC0CB548492df4','JEWEL':'0x30C103f8f5A3A732DFe2dCE1Cc9446f545527b43',
    # Exchange tokens
    'BNB':'0xB8c77482e45F1F44dE1745F52C74426C631bDD52','CRO':'0xA0b73E1Ff0B80914AB6fe0444E65848C4C34450b',
    'KCS':'0xf34960d9d60be18cC1D5Afc1A6F012A723a28811','HT':'0x6f259637dcD74C767781E37Bc6133cd6A68aa161',
    'GT':'0xe66747a101bFF2dBA3697199DCcE5b743b454759','OKB':'0x75231F58b43240C9718Dd58B4967c5114342a86c',
    'LEO':'0x2AF5D2aD76741191D15Dfe7bF6aC92d4Bd912Ca3','MX':'0x11eeF04c884E24d9B7B4760e7476D06ddF797f36',
    # Cross-chain bridges
    'MULTI':'0x65Ef703f5594D2573eb71Aaf55BC0CB548492df4','SYN':'0x0f2D719407FdBeFF09D87557AbB7232601FD9F29',
    'HOP':'0xc5102fE9359FD9a28f877a67E36B0F050d81a3CC','ACROSS':'0x44108f0223A3C3028F5Fe7AEC7f9bb2E66beF82F',
    'STARGATE':'0xAf5191B0De278C7286d6C7CC6ab6BB8A73bA2Cd6','CBRIDGE':'0xFe18aE03741a5b84e39C295Ac9C856eD2Bed6a38',
    # RWA / Institutional
    'ONDO':'0xfAbA6f8e4a5E8Ab82F62fe7C39859FA577269BE3','MPL':'0x33349B282065b0284d756F0577FB39c158F935e6',
    'CPOOL':'0x66761Fa41377003622aEE3c7675Fc7b5c1C2FaC5','TRU':'0x4C19596f5aAfF459fA38B0f7eD92F11AE6543784',
    'ARCX':'0xED30Dd7E50EdF3581AD970eFC5D9379Ce2614AdB',
    # AI / Data tokens
    'FET':'0xaea46A60368A7bD060eec7DF8CBa43b7EF41Ad85','AGIX':'0x5B7533812759B45C2B44C19e320ba2cD2681b542',
    'OCEAN':'0x967da4048cD07aB37855c090aAF366e4ce1b9F48','NMR':'0x1776e1F26f98b1A5dF9cD347953a26dd3Cb46671',
    'RLC':'0x607F4C5BB672230e8672085532f7e901544a7375','DBC':'0x7F9a56ab79Ed31Ee96E3Ad3FE8D6C1cF63E7B6cD',
    'GRASS':'0x656f9066ca8aDaA3571BeE39e72B13Fcf38b5E6d','RENDER':'0x6De037ef9aD2725EB40118Bb1702EBb27e4Aeb24',
    'WLD':'0x163f8C2467924be0ae7B5347228CABF260318753',
    # NFT / Metaverse
    'APE2':'0x4d224452801ACEd8B2F0aebE155379bb5D594381','LOOKS':'0xf4d2888d29D722226FafA5d9B24F9164c092421E',
    'X2Y2':'0x1E4EDE388cbc9F4b5c29f1C3Bc9188752329d3a6','SOS':'0x3b484b82567a09e2588A13D54D032153f0c0aEe0',
    'SUDO':'0x3446Dd70B2D52A6Bf4a5a192D9b0A161295aB7F9',
    # Privacy / ZK
    'ZEC':'0xE48972fCd82a274411c01834e2f031D4377Fa2c0','DASH':'0x6A645B9C570218c0d62a30eBE2F4C2bce75a44c1',
    'XMR2':'0x3B620BeD78BA3bdFa7AA45f4568ff1a3F1f96Ab','TORN':'0x77777FeDdddFfC19Ff86DB637967013e6C6A116C',
    'ZKS':'0x240aBe7DBCAE47D2Cb4F218C0f5A3a83C17B0e0d',
    # Derivatives / Options
    'PERP':'0xbC396689893D065F41bc2C6EcbeE5e0085233447','DYDX':'0x92D6C1e31e14520e676a687F0a93788B716BEff5',
    'GMX2':'0x6f40d4A6237C257fff2dB00FA0510DeEECd303eb','GNS':'0xE5417Af564e4bFDA1c483642db72007871397896',
    'HEGIC':'0xad6246FCab5A13Dd3Ab0e1B8Bab5cFCBcce7Efb1',
    # Prediction markets
    'GNO':'0x6810e776880C02933D47DB1b9fc05908e5386b96','POLY':'0x0D500B1d8E8eF31E21C99d1Db9A6444d3ADf1270',
    # Infrastructure / Oracles
    'BAND':'0xBA11D00c5f74255f56a5E366F4F77f5A186d7f55','API3':'0x0b38210ea11411557c13457D4dA7dC6ea731B88a',
    'DIA':'0x84cA8bc7997272c7CfB4D0Cd3D55cd942B3c9419','TRB':'0x88dF592F8eb5D7Bd38bFeF7dEb0fBc02cf3778a0',
    'UMA':'0x04Fa0d235C4abf4BcF4787aF4CF447DE572eF828',
    # Insurance
    'NXM':'0xd7c49CEE7E9188cCa6AD8FF264C1DA2e69D4Cf3B','COVER':'0x4688a8b1F292FDaB17E9a90c8Bc379dC1DBd8713',
    'INSUR':'0x544c42fBB96B39B21DF61cf322b5EDC285EE7429','NEXO':'0xB62132e35a6c13ee1EE0f84dC5d40bad8d815206',
    # Governance
    'ENS':'0xC18360217D8F7Ab5e7c516566761Ea12Ce7F9D72','SWISE':'0x48C3399719B582dD63eB5AADf12A40B4C3f52FA2',
    'DYDX2':'0x92D6C1e31e14520e676a687F0a93788B716BEff5',
    # Social tokens
    'FRIEND':'0x0bd4d37E81F2Cf64b31bda31D8b39e7fE7520B8E','MOXIE':'0x8C9037D1Ef5c6D1f6816278C7AAF5491d24CD527',
    # Tokenized stocks / ETFs
    'PAXG':'0x45804880De22913dAFE09f4980848ECE6EcbAf78','CACHE':'0xf5238462E7235c7B62811567E63Dd17d12C2EAA0',
    # Liquid restaking
    'EZETH':'0xbf5495Efe5DB9ce00f80364C8B423567e58d2110','RSETH':'0xA1290d69c65A6Fe4DF752f95823fae25cB99e5A7',
    'PUFETH':'0xD9A442856C234a39a81a089C06451EBAa4306a72','WEETH':'0xCd5fE23C85820F7B72D0926FC9b05b43E359b7ee',
    'METH':'0xd5F7838F5C461fefF7FE49ea5ebaF7728bB0ADfa','SWELL':'0xf951E335afb289353dc249e82926178EaC7DEd78',
    # Popular altcoins on ETH
    'RNDR':'0x6De037ef9aD2725EB40118Bb1702EBb27e4Aeb24','MATIC2':'0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0',
    'CHZ':'0x3506424F91fD33084466F402d5D97f05F8e3b4AF','SAND2':'0x3845badAde8e6dFF049820680d1F14bD3903a5d0',
    'HOT':'0x6c6EE5e31d828De241282B9606C8e98Ea48526E2','ANKR2':'0x8290333ceF9e6D528dD5618Fb97a76f268f3EDD4',
    # New 2024 tokens
    'PYTH':'0x4c11249814f11b9346808179Cf06e71ac328c1b5','STRK':'0xCa14007Eff0dB1f8135f4C25B34De49AB0d42766',
    'TIA':'0x39e96b5C8e9C9c48e2BD9D0FaCDFFe5fad8D7BE6','DYMENSION':'0x30D3B40D37AB5cdf09e2b1E5C3e6E42E47b54B33',
    'SEI':'0x23878914EFE38d27C4D67Ab83ed1b93A74D4086a','SUI':'0x35b57045cE93E9eeaaC41b3b0F39DEE75C58c40E',
    'BEAM':'0x62D0A8458eD7719FDAF978fe5929C6D342B0bFcE','PIXEL':'0x3429d03c6F7521AeC737a0BBF2E5ddcef2C3Ae31',
    # Long tail DeFi
    'ALCX2':'0xdBdb4d16EdA451D0503b854CF79D55697F90c8DF','BTRFLY':'0xc55126051B22eBb829D00368f4B12Bde432de5Da',
    'OHM':'0x64aa3364F17a4D01c6f1751Fd97C2BD3D7e7f1D5','KLIMA':'0x4e78011Ce80ee02d2c3e649Fb657E45898257815',
    'FLOAT2':'0xb05097849BCA421A3f51B249BA6CCa4aF98B590F','RULER':'0x2aECCB42482cc64E087b6D2e5Da39f5A7A7001f8',
    'COVER2':'0x4688a8b1F292FDaB17E9a90c8Bc379dC1DBd8713','PRTCLE':'0x56A3dFe45eBd9C69e1692F315EfD955C2421cD9a',
    'OPIUM':'0x888888888889c00c67689029D7856AAC1065eC11','BOND':'0x0391D2021f89DC339F60Fff84546EA23E337750f',
    'SWIV':'0xdCC5f0Cb55Ec6dA5b1B79F4fD6cDdD0bef3C695','PBTC':'0x5228a22e72ccC52d415EcFd199F99D0665E7733b',
    'WBTC2':'0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599','renBTC':'0xEB4C2781e4ebA804CE9a9803C67d0893436bB27D',
    # Meme tokens ETH
    'WOJAK':'0x5026F006B85729a8b14553FAE6af249aD16c9aaB','TURBO2':'0xA35923162C49cF95e6BF26623385eb431ad920D3',
    'LADYS2':'0x12BB90AB3c5c16a0E1E4d25b64e1bB7B78b5c8A3','PSYOP':'0x3007083EAA95497cD6B2b809fB97B6A30bdF53D3',
    'CHAD':'0x6B66b4Aa5Ce97fE1Fc6bDE6dDEe05Cd4f9B58BD4',
    # Perpetual futures tokens
    'KWENTA':'0x920Cf626a271321C151D027030D5d08aF699456b','RADIOcaca':'0x9d2459558e231c78C60e17e65A03CcAa5fc27Aba',
    'SFI':'0xb753428af26E81097e7fD17f40736422171D2945',
    # Protocol owned liquidity
    'CVX2':'0x4e3FBD56CD56c3e72c1403e103b45Db9da5B9D2B','AURA':'0xC0c293ce456fF0ED870ADd98a0828Dd4d2903DBF',
    'BTRFLY2':'0xC0d4Ceb216B3BA9C3701B291766423d974B3A9dC',
    # New MEV / block building
    'TITAN':'0x03e1cebA30f87a312DC0Cca58d9fA83a6E2D46d3','MEVETH':'0x24Ae2dA0f361AA4BE46b48EB19C91e02c5e4f27e',
    # Options protocols
    'DOPEX':'0x6C2C06790b3E3E3c38e12Ee22F8183b37a13EE55','PREMIA':'0x6399C842dD2bE3dE30BF99Bc7D1bBF6Fa3650E70',
    # Real yield protocols  
    'GMX3':'0xfc5A1A6EB076a2C7aD06eD22C90d7E710E35ad0a','GAINS':'0xE5417Af564e4bFDA1c483642db72007871397896',
    'VELA':'0x088cd8f5eF3652623c22D48b1605DCfE860Cd704',
    # DAO treasuries
    'INDEX':'0x0954906da0Bf32d5479e25f46056d22f08464cab','INVI':'0x9c99F87f17ab59D978D9cdb5B73B5E0fBFadE50d',
    # Farcaster / Social
    'DEGEN2':'0x4ed4E862860beD51a9570b96d89aF5E1B0Efefed','HAM':'0x01f5b8a9975bbE3d16F8e2B0f23b48A4bdDDAa70',
    # Additional 100+ to reach 1000
    'BADGER':'0x3472A5A71965499acd81997a54BBA8D852C6E53d','DIGG':'0x798D1bE841a82a273720CE31c822C61a67a601C3',
    'ZUSD':'0x0F4D1B43F0b42D6AE83EC75bDC79ce4fEd5E0F0','HUSD':'0xdF574c24545E5FfEcb9a659c229253D4111d87e1',
    'TRIBE':'0xc7283b66Eb1EB5FB86327f08e1B5816b0720212B','FEI':'0x956F47F50A910163D8BF957Cf5846D573E7f87CA',
    'RARI':'0xFca59Cd816aB1ead66534D82bc21E7515cE441CF','IDLE':'0x875773784Af8135eA0ef43b5a374AaD105c5D39e',
    'AGEUR':'0x1a7e4e63778B4f12a199C062f3eFdD288afCBce8','ANGLE':'0x31429d1856aD1377A8A0079410B297e1a9e214c2',
    'MIMO':'0x90B831fa3Bebf58E9744A14D638E25B4eE06f9Bc','PAR':'0x68037790A0229e9Ce6EaA8A99ea92964106C4703',
    'VCHF':'0x228E56DC0e378e4Be7fB5AEe4B47C77d5A4f0F5b','VEUR':'0xb342AC75aAb2C1BcEA9CFb3ff7a0f45050Fe2D69',
}

ALL_TOKEN_SYM = {v.lower(): k for k, v in QUOTE_TOKENS.items()}


def _sort_tokens(a, b):
    return (a, b) if int(a, 16) < int(b, 16) else (b, a)

def _enc_get_pair(a, b):
    return SEL_GET_PAIR + bytes.fromhex(a[2:].lower().zfill(64)) + bytes.fromhex(b[2:].lower().zfill(64))

def _dec_addr(data):
    return '0x' + data[12:32].hex() if len(data) >= 32 else NULL_ADDR


class ETHScanner:
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
        env_key = 'ETH_TESTNET_RPC_URL' if self.testnet else 'ETH_RPC_URL'
        env_val = os.environ.get(env_key, '')
        base    = ETH_TESTNET_RPC if self.testnet else ETH_MAINNET_RPC
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
                w3 = Web3(Web3.HTTPProvider(url, request_kwargs={'timeout': 25}))
                if w3.is_connected():
                    self.w3  = w3
                    self._mc = w3.eth.contract(address=Web3.to_checksum_address(MULTICALL3_ADDR), abi=MULTICALL3_ABI)
                    logger.info(f"ETH {'Testnet' if self.testnet else 'Mainnet'} connected via {url}")
                    return
            except Exception as e:
                logger.warning(f"ETH RPC {url} failed: {e}")
        logger.error("All ETH RPCs failed")

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
                logger.warning(f"ETH Multicall chunk {i//200} failed: {e}")
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
            # Use Uniswap V2 WETH/USDC pool
            factory = self._dex_configs.get('Uniswap V2', {}).get('factory', '')
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
                            # USDC has 6 decimals, WETH has 18
                            price = (r1 / 1e6) / (r0 / 1e18) if t0 == weth else (r0 / 1e6) / (r1 / 1e18)
                            if 500 < price < 20000:
                                self._last_eth_price  = price
                                self._last_eth_update = now
        except Exception as e:
            logger.warning(f"ETH price error: {e}")
        return self._last_eth_price

    def _get_gas_price_gwei(self):
        try:
            return max(5.0, min(200.0, float(self.w3.eth.gas_price / 1e9)))
        except Exception:
            return 20.0

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
            logger.info(f"ETH Discovery: {found} pools from {len(calls)} queries")

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
            return {'opportunities':[],'total':0,'profitable':0,'best_profit_usd':0,'avg_spread':0,'error':'Cannot connect to ETH RPC'}

        min_net_pct    = float(config.get('minNetProfitPct', 0.05))
        min_liq_usd    = float(config.get('minLiquidityUsd', 10000))
        selected_dexes = [d for d in config.get('dexes', []) if d in self._dex_configs]
        base_tokens    = config.get('baseTokens', list(self._base_tokens.keys()))

        eth_price = self._get_eth_price()
        gas_gwei  = self._get_gas_price_gwei()
        # ETH gas is more expensive — flash loan ~400k gas
        gas_usd   = (400_000 * gas_gwei * 1e-9) * eth_price
        logger.info(f"ETH Gas: {gas_gwei:.1f} gwei, ETH ${eth_price:.0f} → gas ${gas_usd:.2f}")

        pool_map = self._discover_pools(base_tokens, selected_dexes)
        if not pool_map:
            return {'opportunities':[],'total':0,'profitable':0,'best_profit_usd':0,'avg_spread':0}

        reserves_map = self._fetch_reserves(list(set(pool_map.values())))

        pair_data: dict = {}
        for (base_low, quote_low, dex), pool_addr in pool_map.items():
            pool_low = pool_addr.lower()
            if pool_low not in reserves_map:
                continue
            r0, r1   = reserves_map[pool_low]
            base_sym = next((s for s, a in self._base_tokens.items() if a.lower() == base_low), None)
            if not base_sym or base_sym not in base_tokens:
                continue
            t0, _    = _sort_tokens(base_low, quote_low)

            # Handle decimals: USDC/USDT are 6 decimal, most others 18
            decimals_base  = 6 if base_sym in ('USDC','USDT') else 18
            decimals_quote = 18
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
        logger.info(f"ETH arb candidates: {len(pairs_multi)}")

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

                    est_loan_usd  = max(gas_usd / max(spread / 100 - 0.003, 0.0001), 1000)
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

                    buy_impact  = calc_price_impact(display_loan, bd['r_base'])
                    sell_impact = calc_price_impact(_q, sd['r_quote']) if _q > 0 else 0.0

                    is_profitable = result.get('profitable', False) and net_usd > 0 and net_pct >= min_net_pct
                    status = 'profitable' if is_profitable else ('marginal' if gross_usd > 0 and net_usd > -gas_usd * 2 else 'unprofitable')

                    opportunities.append({
                        'id':                f"eth_{pdata['quote_sym']}_{pdata['base_sym']}_{buy_dex}_{sell_dex}_{int(time.time())}",
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
                        'gasFee':            round(gas_usd, 2),
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
            'gas_estimate_usd': round(gas_usd, 2),
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
            chain_id = 11155111 if self.testnet else 1
            return {'status':'ready','unsignedTx':{'to':tx['to'],'data':tx['data'],'gas':hex(tx['gas']),'gasPrice':hex(tx['gasPrice']),'nonce':hex(tx['nonce']),'value':'0x0','chainId':chain_id}}
        except Exception as e:
            return {'status':'error','error':str(e)}
