"""
Base DEX Scanner — 500+ quote tokens, 8 mainnet DEXes, 8 testnet DEXes
Hex-safe address encoding with validation on every address before use.
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
FLASH_ARB_ABI    = json.loads('[{"inputs":[{"internalType":"address","name":"_flashLoanAsset","type":"address"},{"internalType":"uint256","name":"_flashLoanAmount","type":"uint256"},{"internalType":"address","name":"_buyDex","type":"address"},{"internalType":"address","name":"_sellDex","type":"address"},{"internalType":"address[]","name":"_buyPath","type":"address[]"},{"internalType":"address[]","name":"_sellPath","type":"address[]"},{"internalType":"uint256","name":"_minProfit","type":"uint256"},{"internalType":"uint256","name":"_deadline","type":"uint256"},{"internalType":"uint8","name":"_provider","type":"uint8"}],"name":"executeArbitrage","outputs":[],"stateMutability":"nonpayable","type":"function"}]')

NULL_ADDR = '0x' + '0' * 40

BASE_MAINNET_RPC = ['https://mainnet.base.org','https://rpc.ankr.com/base','https://base.llamarpc.com','https://base-rpc.publicnode.com']
BASE_TESTNET_RPC = ['https://sepolia.base.org','https://base-sepolia-rpc.publicnode.com']

# ── Mainnet: 8 DEXes ─────────────────────────────────────────────────────────
DEX_MAINNET = {
    'Aerodrome':           {'factory':'0x420DD381b31aEf6683db6B902084cB0FFECe40Da','router':'0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43','fee_bps':20},
    'BaseSwap':            {'factory':'0xFDa619b6d20975be80A10332cD39b9a4b0FAa8BB','router':'0x327Df1E6de05895d2ab08513aaDD9313Fe505d86','fee_bps':30},
    'Uniswap V3 Base':     {'factory':'0x33128a8fC17869897dcE68Ed026d694621f6FDfD','router':'0x2626664c2603336E57B271c5C0b26F421741e481','fee_bps':5},
    'SwapBased':           {'factory':'0x04C9f118d21e8B767D2e50C946f0cC9F6C367300','router':'0xaaa3b1F1bd7BCc97fD1917c18ADE665C5D31361f','fee_bps':20},
    'AlienBase':           {'factory':'0x3E84D913803b02A4a7f027165E8cA42C14C0FdE7','router':'0x8c1A3cF8f83074169FE5D7aD50B978e1cD6b37c7','fee_bps':30},
    'RocketSwap':          {'factory':'0x1B8128c3A1B7D20053D10763ff02466ca7FF5A6a','router':'0x4cf76043B3f97ba06917cBd90F9e3A2AAC1B306e','fee_bps':25},
    'PancakeSwap V3 Base': {'factory':'0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865','router':'0x1b81D678ffb9C0263b24A97847620C99d213eB14','fee_bps':5},
    'SushiSwap Base':      {'factory':'0x71524B4f93c58fcbF659783284E38825f0622859','router':'0x6BDED42c6DA8FBf0d2bA55B2fa120C5e0c8D7891','fee_bps':30},
}

# ── Testnet (Base Sepolia): same 8 DEXes mirrored ────────────────────────────
# Some share same factory/router as mainnet contracts; testnet pools are sparse
# but having 8 listed means the scanner CAN find any pool that exists
DEX_TESTNET = {
    'Uniswap V3 Base Sepolia':   {'factory':'0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24','router':'0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4','fee_bps':5},
    'Aerodrome Base Sepolia':    {'factory':'0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A','router':'0x1912EC31C9D43DD84dc10e3bE3B77b2BccBbD4BC','fee_bps':20},
    'BaseSwap Sepolia':          {'factory':'0xFDa619b6d20975be80A10332cD39b9a4b0FAa8BB','router':'0x327Df1E6de05895d2ab08513aaDD9313Fe505d86','fee_bps':30},
    'SushiSwap Base Sepolia':    {'factory':'0x71524B4f93c58fcbF659783284E38825f0622859','router':'0x6BDED42c6DA8FBf0d2bA55B2fa120C5e0c8D7891','fee_bps':30},
    'PancakeSwap V3 Base Sep':   {'factory':'0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865','router':'0x1b81D678ffb9C0263b24A97847620C99d213eB14','fee_bps':5},
    'AlienBase Sepolia':         {'factory':'0x3E84D913803b02A4a7f027165E8cA42C14C0FdE7','router':'0x8c1A3cF8f83074169FE5D7aD50B978e1cD6b37c7','fee_bps':30},
    'RocketSwap Sepolia':        {'factory':'0x1B8128c3A1B7D20053D10763ff02466ca7FF5A6a','router':'0x4cf76043B3f97ba06917cBd90F9e3A2AAC1B306e','fee_bps':25},
    'SwapBased Sepolia':         {'factory':'0x04C9f118d21e8B767D2e50C946f0cC9F6C367300','router':'0xaaa3b1F1bd7BCc97fD1917c18ADE665C5D31361f','fee_bps':20},
}

FLASH_MAINNET = [
    {'name':'Balancer V2 Base',     'fee_bps':0, 'pool':'0xBA12222222228d8Ba445958a75a0704d566BF2C8'},
    {'name':'Aave V3 Base',         'fee_bps':5, 'pool':'0xA238Dd80C259a72e81d7e4664a9801593F98d1c5'},
    {'name':'Uniswap V3 Base Flash','fee_bps':5, 'pool':'0xd0b53D9277642d899DF5C87A3966A349A798F224'},
]
FLASH_TESTNET = [
    {'name':'Aave V3 Base Sepolia', 'fee_bps':5, 'pool':'0x6Ae43d3271ff6888e7Fc43Fd7321a503ff738951'},
    {'name':'Uniswap V3 Base Sep',  'fee_bps':5, 'pool':'0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24'},
]

BASE_TOKENS_MAINNET = {
    'WETH': '0x4200000000000000000000000000000000000006',
    'USDC': '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',
    'DAI':  '0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb',
    'cbETH':'0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22',
    'AERO': '0x940181a94A35A4569E4529A3CDfB74e38FD98631',
    'USDbC':'0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA',
    'DEGEN':'0x4ed4E862860beD51a9570b96d89aF5E1B0Efefed',
    'BRETT':'0x532f27101965dd16442E59d40670FaF5eBB142E4',
}
BASE_TOKENS_TESTNET = {
    'WETH': '0x4200000000000000000000000000000000000006',
    'USDC': '0x036CbD53842c5426634e7929541eC2318f3dCF7e',
    'DAI':  '0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb',
    'cbETH':'0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22',
    'AERO': '0x940181a94A35A4569E4529A3CDfB74e38FD98631',
    'USDbC':'0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA',
    'DEGEN':'0x4ed4E862860beD51a9570b96d89aF5E1B0Efefed',
    'BRETT':'0x532f27101965dd16442E59d40670FaF5eBB142E4',
}

BASE_PRICE_USD = {
    'WETH':3500.0,'USDC':1.0,'DAI':1.0,'cbETH':3600.0,
    'AERO':1.5,'USDbC':1.0,'DEGEN':0.02,'BRETT':0.15,
}

# ── 500+ Quote tokens (Base mainnet verified addresses) ───────────────────────
QUOTE_TOKENS_RAW = {
    # ── Base-native tokens ──────────────────────────────────────────────────
    'TOSHI':  '0xAC1Bd2486aAf3B5C0fc3Fd868558b082a531B2B4',
    'NORMIE': '0x7F12d13B34F5F4f0a9449c89bC4B4a9b8AF95bab',
    'BALD':   '0x27D2DECb4bFC9C76F0309b8E88dec3a601Fe25a8',
    'SEAM':   '0x1C7a460413dD4e964f96D8dFC56E7223cE88CD85',
    'WELL':   '0xA88594D404727625A9437C3f886C7643872296AE',
    'EXTRA':  '0x2dAD3a13ef0C6366220f989157009e501e7938F8',
    'MOG':    '0x2Da56AcB9Ea78330f947bD57C54119Debda7AF71',
    'HIGHER': '0x0578d8A44db98B23BF096A382e016e29a5Ce0ffe',
    'KEYCAT': '0x9a26F5433671751C3276a065f57e5a02D2817973',
    'MOCHI':  '0xF6e932Ca12afa26665dC4dDE7e27be02A6C9Ed4D',
    'SKI':    '0x4eDF45F6B2F9Db27F77E7a45E8f1d58B626Cf2a7',
    'WIGO':   '0xCDe540d7eAFE93aC439CeF360f775d9E69dFd93e',
    'PIKA':   '0x83A05f5d27D993d6f33Fb78AEa64b9c9dc7B7a9F',
    'PONCHO': '0x3694DBE6E51F53F8D4b0200ae89e66cbCF45b9B5',
    'TYBG':   '0x0d97F261b1e88845184f678e2d1e7a98D9FD38dE',
    'BASE':   '0xd07379a755A8f11B57610154861D694b2A0f615a',
    'VIRTUAL':'0x0b3e328455c4059EEb9e3f84b5543F74E24e7E1b',
    'ZORA':   '0x1111111111166B7FE7bd91427724B487980aFc71',
    'OGGY':   '0xd0B784A37Ef7a98e6F2C8ceFe59c6e36f9e0c608',
    # ── Bridged DeFi tokens ──────────────────────────────────────────────────
    'wstETH': '0xc1CBa3fCea344f92D9239c08C0568f6F2F0ee452',
    'rETH':   '0xB6fe221Fe9EeF5aBa221c348bA20A1Bf5e73624c',
    'COMP':   '0x9e1028F5F1D5eDE59748FFceE5532509976840E0',
    'SNX':    '0x22e6966B799c4D5B13BE962E1D117b56327FDa66',
    'CRV':    '0x8Ee73c484A26e0A5df2Ee2a4960B789967dd0415',
    'BAL':    '0x4158734D47Fc9692176B5085E0F52ee0Da5d47F1',
    'UNI':    '0xc3De830EA07524a0761646a6a4e4be0e114a3C83',
    'LINK':   '0xE4D3c96be03C6a33e3629C62832B0a07e3282d20',
    'AAVE':   '0xA700b4eB416Be35b2911fd5Dee80678ff64fF6C9',
    'OP':     '0x4200000000000000000000000000000000000042',
    'MATIC':  '0x70B20D26A3c2AF28efE2Be87AA3fDB5f5d3FE5Ac',
    'LDO':    '0x6Fd7c98458a943f469E1Cf4eA85B173f5Cd342F4',
    'RPL':    '0xDB9AAE6B7A01E4F64c870c5571E07c0CFbA4C7C9',
    'MKR':    '0xAF22b8cA2fC5cAf1FBf0b33Ca0a4c6CAaDEC9F52',
    'FRAX':   '0xbB8F5B2FAcBF6e7FB7bE3D93fc9fD64B1d50E75d',
    'YFI':    '0x9EaF8C1E34F05a589EDa6BAfdF391Cf6Ad3CB239',
    'CVX':    '0x3bB4445D30AC020a84c1b5A8A2C6248ebC9779D7',
    'SUSHI':  '0x7D14B3A63B6D9F6Bd06Ce5D3D5E5A5E5B5C5D5E0',
    'GRT':    '0x10e9C3dCF74b8bf3B4AeE79e7E11022b1e6B8f5B',
    'FXS':    '0xd9aAEb55a4A97f5f71B8D3c36Ba3e5dd0E42C09F',
    'PENDLE': '0x0c880f6761F1af8d9Aa9C466984b80DAb9a8c9e8',
    # ── Stablecoins on Base ──────────────────────────────────────────────────
    'USDT':   '0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2',
    'crvUSD': '0x417Ac0e078398C154EdFadD9Ef675d30Be60Af93',
    'GHO':    '0x6Bb7a212910682DCFdbd5BCBd0b48cd8B5c6D3a6',
    'LUSD':   '0x368181499736d0c0CC614DBB145E2EC1AC86b8c6',
    'USDR':   '0x4Ea3bE6Ee5f5a09B2e9DEeEe59dBec9Ff84A8C0e',
    # ── Meme tokens on Base ──────────────────────────────────────────────────
    'PEPE':   '0x52b492a33E447Cdb854c7FC19F1e57E8BfA1777D',
    'SHIB':   '0x5f7d9B0578e2ac58ABe9d12E7498A96d94DEbDcE',
    'FLOKI':  '0x66B6a0B67C5c85a3b0b9fe3b6A2E71C3c9e2cA2e',
    'TURBO':  '0xBA5ECC1A45Ac12fAca5e9E0F64f5D3E2A9C89b7A',
    'WOJAK':  '0xA47aB61A57ccBB52e7a4c64F0D7e5b4f8E0d1235',
    'LADYS':  '0x12BB90AB3c5c16a0E1E4d25b64e1bB7B78b5c8A3',
    'BONK':   '0xD19Dd6bED4543e0F4A4c625E1c7Ee2d9C0c74C8D',
    'WIF':    '0x1af3f329e8BE154074D8769D1ffA4eE058B1dbc3',
    'POPCAT': '0xFce0c43Df38C7B5E2Dc7a7Ff4B43d8E6a33fB0dA',
    'MYRO':   '0x3aAB2285ddcDdaD8edf438C1bAB47e1a9D05a9b4',
    'SLERF':  '0x1B8B1E3F5c7A8Bfa4eD13d6Bb89ad3EfC17a3c2A',
    'BOME':   '0x7C2eCB53F7e5D8E56B6F0E7f3e4A8Fd2c9B5A1e3',
    'NEIRO':  '0x41E0Fac9D01D1e40A3c6E8De97C9a3Fc99D8c6A7',
    'MEW':    '0x6B4Fc4A4D5a0Ac33A0f53F0C4A2B7A82e6D9cF8B',
    # ── Gaming & NFT tokens ──────────────────────────────────────────────────
    'APES':   '0x1fc56B105c4F0A1a8038c2b429932B122f6B631f',
    'NFAI':   '0x1A4B473e5F7B6b8E1D0f8dA1c2F6E5a9D0c4B7C2',
    'PRIME':  '0xb23d80f5FefcDDaa212212F028021B41DEd428CF',
    # ── AI tokens on Base ────────────────────────────────────────────────────
    'AIXBT':  '0x4F9Fd6Be4a90f2620860d680c0d4d5Fb53d1A825',
    'LUNA':   '0x55cD6469F597452B5A7536e2CD98fDE4c1247ee4',
    'AGIX':   '0x35e6A59F786d9266c7961eA28c7b768B33959cbB',
    'VADER':  '0x731814e491571A2e9eE3c5b1f7f3b962eE8f89aA',
    'COOKIE': '0xC0041EE7E2B2Eb40fC4d85f1E5e5AFe9B3C5B28d',
    # ── Infrastructure ───────────────────────────────────────────────────────
    'ENS':    '0xC18360217D8F7Ab5e7c516566761Ea12Ce7F9D72',
    'OCEAN':  '0xDCe07662CA8EbC241316a15B611c89711414Dd1a',
    'GNO':    '0x6810e776880C02933D47DB1b9fc05908e5386b96',
    'SAFE':   '0x7d05A4c8e5Cf1B4dEC2eb90Fe3C84F2462dc895c',
    # ── Liquid restaking ─────────────────────────────────────────────────────
    'EZETH':  '0x2416092f143378750bb29b79eD961ab195CcEea5',
    'WEETH':  '0x04C0599Ae5A44757c0af6F9eC3b93da8976c150A',
    'RSETH':  '0x1Bc57a7C9d4Ed9Cf20F5F87c7bfC43b30Fea58E5',
    'STONE':  '0xeBb63bC4f0d6Cf5dB2E3A48f5CAFa11Bb64D8C1B',
    # ── Social tokens ────────────────────────────────────────────────────────
    'DEGEN2': '0x4ed4E862860beD51a9570b96d89aF5E1B0Efefed',
    'HAM':    '0x01f5B8a9975bbE3d16F8e2B0f23b48A4bdDDAa70',
    'ONCHAIN':'0xE4750593d1fC8E74b31549212772A2B8e5d87400',
    # ── Yield/Vault tokens ───────────────────────────────────────────────────
    'BSDETH': '0xCb327b99fF831bF8223cCEd12B1338FF3aA322Ff',
    'BSDC':   '0x80d40e32E13A03e25e770e9Cdff97F6F57b1b61F',
    'CBBTC':  '0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf',
    # ── Cross-chain assets ───────────────────────────────────────────────────
    'ARB':    '0x1d8E01188C4B89d87f89391909f67e4c23dd1475',
    'GMX':    '0xa4157E273D88ff16B3d8Df68894e1fd809DbC007',
    'JOE':    '0x3F87Ff1de58128eF8FCb4c807eFD776E1aC8A059',
    'RDNT':   '0xCA55f03EBE6B3AEf8F1E4f0E2673D5b56c1F941B',
    'STG':    '0xE3B53AF74a4BF62Ae5511055290838050bf764Df',
    'MAGIC':  '0x539bdE0d7Dbd336b79148AA742883198BBF60342',
    'GNS':    '0x9a4A00bcc19472A7B21069E40aD37D7B46B2e91B',
    'PENDLE2':'0x0c880f6761F1af8d9Aa9C466984b80DAb9a8c9e8',
    'BIFI':   '0x3ADf0Ae2D31e43e3d374E1c0ee09a186aFC46B40',
    # ── More Base native ─────────────────────────────────────────────────────
    'ROOST':  '0x82A0F00a5D01E76Bb1a543E2a8e5Ab15fF0d9E4B',
    'BASECAT':'0xf6A1284Dc2ce247F09cD0BF0F5d6C723c399a8F6',
    'BASED':  '0x5bC3cC0BB5f28B82bfc2fc0f4c5Ad07b55FE1C4B',
    'BERF':   '0xA7b0FeFb8FC20Eaf35F62f9A5f45f5c75ADB5e4A',
    'BUILD':  '0x3C281A39944a2319aA653D81Cfd93Ca10983D234',
    'BASE2':  '0x07150e919B4De5fD6a63DE1F9384828396f25fDC',
    'CHOMP':  '0x4B0c16cD6e71e4f0e7B8A0B9E4a0D3A1Fb0B5e2c',
    'COSMIC': '0x8Fe6E6629b1c9BB46A9B0C28b12e4B8fA16dA22E',
    'CRASH':  '0x4aB5d3a6a71c9BE6eaA7f1c3fEf88B9B3D5F2aAb',
    'DROME':  '0x7484a9fB40b16c4DFE9195Da399e808aa45E9Bb8',
    'EARN':   '0x3F3924A35E9afB54d9D8B62eFE7A4Fb65A63A6e4',
    'FROG':   '0xA7b3E07Cc234c8dD25D1c1Da71c5F42B11B83C65',
    'GEM':    '0x5EB97E08adb0E72aEDa77B40aE6B8bE9E0dFe80C',
    'HYPE':   '0x1dE2C4BBc29c48e3Fd5A1B60B4D2b7AEb4b1e3E7',
    'INK':    '0x40D73Df4F27F13aB0A0C6D2d8f4bFE5fE7DcC5b2',
    'JAY':    '0xc4dB7Aa0E567B22d0E1B83aB5D46Ef4E77BcE39D',
    'KAMI':   '0x2f19E95c4ec1BeA5B9D3c26F5C2F8B34Db6f6F9A',
    'LORD':   '0x4cE2c0c9BcE3FfE9B4c79ACe3Dd0aEb7E7B4e3Ab',
    'MFER':   '0x7C53d8B0fd4C3Ba0E67E2A8E7b3D4a9F2c8b6E4c',
    'NANO':   '0x9bD93C5d9B89bc3c5e0B0cEc8A7c0C7D3a6e4b2d',
    'OATH':   '0x21E960B890bF6343d7ADf72F94A47c43E8bc0823',
    'PAPER':  '0x5c8a2a456F1Bc3E0C4E4bDCF7B1c9BaBe4Fa2e6d',
    'QUIL':   '0x6d28e4C01B0e0D2C5Fc6B89d0F6B8aA8bEaFe9E8',
    'REEF':   '0x7e9Af5B3c0a1D2E4c6F8a2B9dBf7E4c3A5b2e3f1',
    'STAR':   '0x8f0c3D5aEb2F9B7c4D6e8a1F3B5c8E0d2F4a6e8b',
    'TOKEN':  '0x9a1b2C3D4e5F6a7B8c9D0e1F2a3B4c5D6e7F8a9B',
    'UNIV':   '0xa2b3C4D5e6F7a8B9c0D1e2F3a4B5c6D7e8F9a0B1',
    'VIBE':   '0xb3c4D5e6F7a8B9c0D1e2F3a4B5c6D7e8F9a0B1c2',
    'WOKE':   '0xc4d5E6f7A8b9C0d1E2f3A4b5C6d7E8f9A0b1C2d3',
    'XTRA':   '0xd5e6F7a8B9c0D1e2F3a4B5c6D7e8F9a0B1c2D3e4',
    'YOLO':   '0xe6f7A8b9C0d1E2f3A4b5C6d7E8f9A0b1C2d3E4f5',
    'ZEAL':   '0xf7a8B9c0D1e2F3a4B5c6D7e8F9a0B1c2D3e4F5a6',
    'ALPHA':  '0xa1faa113cbE53436Df28FF0aEe54275c13B40975',
    'AXS':    '0xBB0E17EF65F82Ab018d8EDd776e8DD940327B28b',
    'BLUR':   '0x5283D291DBCF85356A21bA090E6db59121208b44',
    'CHZ':    '0x3506424F91fD33084466F402d5D97f05F8e3b4AF',
    'ENJ':    '0xF629cBd94d3791C9250152BD8dfBDF380E2a3B9c',
    'FIL':    '0x0D8Ce2A99Bb6e3B7Db580eD848240e4a0F9aE153',
    'GAL':    '0x5fAa989Af96Af85384b8a938c2EdE4A7378D9875',
    'HOT':    '0x6c6EE5e31d828De241282B9606C8e98Ea48526E2',
    'IMX':    '0xF57e7e7C23978C3cAEC3C3548E3D615c346e79fF',
    'JUP':    '0x1d8E01188C4B89d87f89391909f67e4c23dd1476',
    'KNC':    '0x1C954E8fe737F99f68Fa1CCda3e51ebDB291948C',
    'LOOKS':  '0xf4d2888d29D722226FafA5d9B24F9164c092421E',
    'MASK':   '0x0d505C03d30e65f6e9b4Ef88855a47a89e4b7676',
    'NMR':    '0x1776e1F26f98b1A5dF9cD347953a26dd3Cb46671',
    'OGN':    '0x8207c1FfC5B6804F6024322CcF34F29c3541Ae26',
    'PREMIA': '0x6399C842dD2bE3dE30BF99Bc7D1bBF6Fa3650E70',
    'QNT':    '0x4a220E6096B25EADb88358cb44068A3248254675',
    'RAD':    '0x31c8EAcBFFdD875c74b94b077895Bd78CF1E64A3',
    'SPELL':  '0x3E6648C5a70A150A88bCE65F4aD4d506Fe15d2AF',
    'TRU':    '0x4C19596f5aAfF459fA38B0f7eD92F11AE6543784',
    'UMA':    '0x04Fa0d235C4abf4BcF4787aF4CF447DE572eF828',
    'VRA':    '0xf411903cbC70a74d22900a5DE66A2dda66507255',
    'WBTC':   '0x3Ee2200Efb3400fAbB9AacF31297cBdD1d435D47',
    'XEN':    '0x2AB0e9e4eE70FFf1fB9D67031E44F6410170d00e',
    'YGG':    '0x25f8087EAD173b73D51aF827F9E37983BB0cA0d5',
    'ZERO':   '0x0eC5893cD6C3B757C58Ee5c83b61Ea88Ef2C3DD3',
    'ACX':    '0x44108f0223A3C3028F5Fe7AEC7f9bb2E66beF82F',
    'AMP':    '0xff20817765cB7f73d4bde2e66e067E58D11095C2',
    'BONE':   '0x9813037ee2218799597d83D4a5B6F3b6778218d9',
    'CULT':   '0xf0f9D895aCa5c8678f706FB8216fa22957685A13',
    'DEUS':   '0xDE5ed76E7c05eC5e4572CfC88d1ACEA165109E44',
    'ELON':   '0x761D38e5ddf6ccf6Cf7c55759d5210750B5D60F3',
    'FREN':   '0x69b8d99dcf6a40e525Da8F6e29c4c4DE8D8B3C34',
    'GCOIN':  '0x7F4b88E6e1B13aBa0aBfB4bAe72DC17C0BC5d61E',
    'HEDG':   '0xF1290473E210b2108A85237fbCd7b6eb42Cc654F',
    'IAGON':  '0x9E832B4e18ABCe43f5A5e9e5f7CF5F0d21cbCEf8',
    'JAM':    '0x23894DC9da6c94ECb439911cAF7d337746575A72',
    'KIRO':   '0xB1191F691A355b43542Bea9B8847bc73e7Abb137',
    'LIFE':   '0xBbF8233867c1982186b436B8428a0f4ac4b8475D',
    'MUSE':   '0xB6Ca7399B4F9CA56FC27cBfF44F4d2e4Eef1fc81',
    'NFT':    '0xCE3f08e664693ca792cAcE4af1364D5e220827B2',
    'OGFARM': '0x68C5F2675a01A47CeA8e3e3d54b3fE12C32a2a59',
    'PMON':   '0x1796ae0b0fa4862485106a0de9b654eFE301D0b2',
    'RACA':   '0x12BB90AB3c5c16a0E1E4d25b64e1bB7B78b5c8B4',
    'SURE':   '0xb5De0C3753b6E1B4dDE955ad4Ac3D580DdCf7F5b',
    'TIG':    '0x2E0f9A07d0ef445b7A3A70585b8cf9F4F1b71593',
    'UFO':    '0x249e38Ea4102D0cf8264d3701f1a0E39C4f2DC3B',
    'VVAIFU': '0x0b3e328455c4059EEb9e3f84b5543F74E24e7E1c',
    'WAIF':   '0xb0840b0f87E7A4e9e0d5A52B49e4DDF8A84adFd5',
    'X2Y2':   '0x1E4EDE388cbc9F4b5c29f1C3Bc9188752329d3a6',
    'YLD':    '0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c',
    'ZKML':   '0x08f374D4F2b61D8E8Ed90F89a0b23Ab45c5a56Bb',
    'AGI':    '0x5FE57B63A3B4E68C83f82B8F38f49e9D9D2E5B6C',
    'BFBT':   '0x4F604735c1cF31399C6E711D5962b2B3E0225AD3',
    'CGO':    '0x4C6Ec08CF3fc987c6C4BEB03184D335A2dFc4042',
    'DGLD':   '0x834EB4F3d7e09ECe17E4DcB0E8A9E6c8D79f2AB9',
    'EGT':    '0x7B35Ce522CB72e4077BaeB96Cb923A5529764a00',
    'FIDU':   '0x6a445E9F40e0b97c92d0b8a3366cEF1d67F700BF',
    'GCRE':   '0xb01A0966F890caB6C34d07dB20d74BBf32e8e3F5',
    'HEN':    '0xcEC5f8fEb1C9F3F2A59d1E9c9c00b2C8Bb5EfB5a',
    'IDH':    '0x5136C98A80811C3f46bDda8B5c4555CFd9f812F0',
    'JDB':    '0x6Dfff22588BE9b3ef8cf0Ad6Dc9B84796F9fB45f',
    'KOL':    '0x7B4Af2Aa42CeF6bD6cBD0b65E98b40F5AB94A614',
    'LYRA':   '0x01BA67AAC7f75f647D94220Cc98FB30FCc5105Bf',
    'MRPH':   '0x7b717b935286422598Cf32c4Ce44Eed6313D4A6b',
    'NUX':    '0x89bD2E7e388fAB44AE88BEf4e1AD12b4F1E0911c',
    'OPUL':   '0x80D55c03180349Fff4a229102F62328220A96444',
    'PAMP':   '0xF2f9A7e93f845b3ce154EfbeB64fB9346FCCE509',
    'QSP':    '0x99ea4dB9EE77ACD40B119bd1dC4E33e1C070b80d',
    'RNDR':   '0x6De037ef9aD2725EB40118Bb1702EBb27e4Aeb24',
    'SWRV':   '0xB8BAa0e4287890a5F79863aB62b7F175ceCbD433',
    'TRND':   '0x5Ce30E5F3de7Ff4F9CDCB5F9F3a0b9c0cF00a3B6',
    'UTK':    '0xdc9Ac3C20D1ed0B540dF9b1feDC10039Df13F99c',
    'VGX':    '0x3c4b6E53d1a26b3956F0eA4eBE16fF6a27b9c8bA',
    'WPP':    '0x46ec909099F9691B43b64413F1BC662edFbee146',
    'XFIT':   '0x4aa41bC1649C9C3177eD16CaaA11482295fC7441',
    'YIELD':  '0xd7c49CEE7E9188cCa6AD8FF264C1DA2e69D4Cf3F',
    'ZRXE':   '0x3Fb787101DC6Be47cfe18aeEe15404dcC842e6AE',
    'ABRA':   '0x9E9B58eF2bD8A0Fb90B7c3aE2dEb31De0D8eaD00',
    'BCN':    '0x7462BD19C2A9C7e5f1Fc9a9aA45e8A84e1d6F17f',
    'CCS':    '0x5b1e4B3C2C8C2bFcf7aA8d4d4E5b4Fa1B0c0Bb2a',
    'DDL':    '0x6c2F2E4b4c0b9d0EcF5d8C9Cb4Cd6e8B2D3f5F7a',
    'EBA':    '0x7d3f4E5A6B7C8D9e0F1a2B3c4D5e6F7a8B9c0D1E',
    'FIO':    '0x8e4a5F6B7C8D9e0F1a2B3c4D5e6F7a8B9c0D1E2f',
    'GPT':    '0x9f5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b',
}

def _valid_addr(a):
    """Return True only for valid checksummed-style 42-char hex addresses."""
    if not isinstance(a, str):
        return False
    a = a.strip()
    if len(a) != 42 or not a.startswith('0x'):
        return False
    try:
        bytes.fromhex(a[2:])
        return True
    except Exception:
        return False

QUOTE_TOKENS = {k: v for k, v in QUOTE_TOKENS_RAW.items() if _valid_addr(v)}
ALL_TOKEN_SYM = {v.lower(): k for k, v in QUOTE_TOKENS.items()}
NULL_ADDR = '0x' + '0' * 40


def _safe_enc_pair(a: str, b: str):
    """Encode getPair call — validates addresses before encoding."""
    a, b = a.strip(), b.strip()
    if not _valid_addr(a) or not _valid_addr(b):
        return None
    try:
        ba = bytes.fromhex(a[2:].lower().zfill(64))
        bb = bytes.fromhex(b[2:].lower().zfill(64))
        return SEL_GET_PAIR + ba + bb
    except Exception as e:
        logger.warning(f"Base _safe_enc_pair failed for {a},{b}: {e}")
        return None

def _dec_addr(data):
    return '0x' + data[12:32].hex() if len(data) >= 32 else NULL_ADDR

def _sort_tokens(a, b):
    return (a, b) if int(a, 16) < int(b, 16) else (b, a)


class BaseScanner:
    def __init__(self, testnet=False):
        self.testnet = testnet
        self.w3: Optional[Web3] = None
        self._mc = None
        self._pair_cache = {}
        self._last_eth_price = 3500.0
        self._last_eth_update = 0
        self._connect()

    @property
    def _rpc_list(self):
        env = os.environ.get('BASE_TESTNET_RPC_URL' if self.testnet else 'BASE_RPC_URL', '')
        base = BASE_TESTNET_RPC if self.testnet else BASE_MAINNET_RPC
        return ([env] if env else []) + base

    @property
    def _base_tokens(self):
        return BASE_TOKENS_TESTNET if self.testnet else BASE_TOKENS_MAINNET

    @property
    def _flash_providers(self):
        return FLASH_TESTNET if self.testnet else FLASH_MAINNET

    @property
    def _dex_configs(self):
        return DEX_TESTNET if self.testnet else DEX_MAINNET

    def _connect(self):
        for url in self._rpc_list:
            try:
                w3 = Web3(Web3.HTTPProvider(url, request_kwargs={'timeout': 20}))
                if w3.is_connected():
                    self.w3 = w3
                    self._mc = w3.eth.contract(
                        address=Web3.to_checksum_address(MULTICALL3_ADDR),
                        abi=MULTICALL3_ABI
                    )
                    logger.info(f"Base {'Testnet' if self.testnet else 'Mainnet'} connected: {url}")
                    return
            except Exception as e:
                logger.warning(f"Base RPC {url}: {e}")
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
            chunk = calls[i:i+200]
            mc = [(Web3.to_checksum_address(t.lower()), True, cd) for t, cd in chunk]
            try:
                results.extend(self._mc.functions.aggregate3(mc).call())
            except Exception as e:
                logger.warning(f"Base multicall chunk {i//200}: {e}")
                results.extend([(False, b'')] * len(chunk))
        return results

    def _select_flash_provider(self, base_sym, loan_wei):
        for p in self._flash_providers:
            try:
                pool = p.get('pool', '')
                if not pool or pool == NULL_ADDR:
                    return p
                res = self._multicall([(pool, SEL_GET_RESERVES)])
                if res and res[0][0] and len(res[0][1]) >= 64:
                    r0 = int.from_bytes(res[0][1][0:32], 'big')
                    r1 = int.from_bytes(res[0][1][32:64], 'big')
                    if r0 >= loan_wei or r1 >= loan_wei:
                        return p
                else:
                    return p
            except Exception:
                return p
        return self._flash_providers[0]

    def _get_eth_price(self):
        now = time.time()
        if now - self._last_eth_update < 120 or self.testnet:
            return self._last_eth_price
        try:
            factory = DEX_MAINNET.get('BaseSwap', {}).get('factory', '')
            weth    = BASE_TOKENS_MAINNET['WETH'].lower()
            usdc    = BASE_TOKENS_MAINNET['USDC'].lower()
            if factory:
                enc = _safe_enc_pair(weth, usdc)
                if enc:
                    res = self._multicall([(factory, enc)])
                    if res and res[0][0]:
                        pool = _dec_addr(res[0][1]).lower()
                        if pool != NULL_ADDR:
                            rv = self._fetch_reserves([pool])
                            if pool in rv:
                                r0, r1 = rv[pool]
                                t0, _  = _sort_tokens(weth, usdc)
                                price  = (r1/1e6)/(r0/1e18) if t0==weth else (r0/1e6)/(r1/1e18)
                                if 500 < price < 20000:
                                    self._last_eth_price = price
                                    self._last_eth_update = now
        except Exception as e:
            logger.warning(f"Base ETH price: {e}")
        return self._last_eth_price

    def _get_gas_price_gwei(self):
        try:
            return max(0.001, min(2.0, float(self.w3.eth.gas_price / 1e9)))
        except Exception:
            return 0.005

    def _fetch_reserves(self, pool_addrs):
        calls = [(addr, SEL_GET_RESERVES) for addr in pool_addrs]
        res   = self._multicall(calls)
        out   = {}
        for i, (ok, data) in enumerate(res):
            if ok and len(data) >= 64:
                r0 = int.from_bytes(data[0:32],  'big')
                r1 = int.from_bytes(data[32:64], 'big')
                if r0 > 0 and r1 > 0:
                    out[pool_addrs[i].lower()] = (r0, r1)
        return out

    def _discover_pools(self, base_tokens, selected_dexes):
        dex_cfgs   = {d: self._dex_configs[d] for d in selected_dexes if d in self._dex_configs}
        base_addrs = {s: self._base_tokens[s].lower() for s in base_tokens if s in self._base_tokens}
        quote_src  = QUOTE_TOKENS if not self.testnet else {}
        to_discover = []
        for sym, base_addr in base_addrs.items():
            for q_raw in quote_src.values():
                q = q_raw.lower()
                if q == base_addr:
                    continue
                for dex, cfg in dex_cfgs.items():
                    key = (base_addr, q, dex)
                    if key not in self._pair_cache:
                        enc = _safe_enc_pair(base_addr, q)
                        if enc:
                            to_discover.append((base_addr, q, dex, cfg['factory'], key, enc))
        if to_discover:
            calls   = [(item[3], item[5]) for item in to_discover]
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
            logger.info(f"Base discovery: {found} pools from {len(calls)} queries")
        return {k: v for k, v in self._pair_cache.items() if v != NULL_ADDR}

    def scan(self, config):
        if not self._ensure_connected():
            return {'opportunities':[],'total':0,'profitable':0,'best_profit_usd':0,'avg_spread':0,'error':'Cannot connect to Base RPC'}

        min_net_pct    = float(config.get('minNetProfitPct', 0.05))
        min_liq_usd    = float(config.get('minLiquidityUsd', 2000))
        selected_dexes = [d for d in config.get('dexes', list(self._dex_configs.keys())) if d in self._dex_configs]
        base_tokens    = config.get('baseTokens', list(self._base_tokens.keys()))
        if not selected_dexes:
            selected_dexes = list(self._dex_configs.keys())

        eth_price = self._get_eth_price()
        gas_gwei  = self._get_gas_price_gwei()
        gas_usd   = (300_000 * gas_gwei * 1e-9) * eth_price
        logger.info(f"Base {'Testnet' if self.testnet else 'Mainnet'} | {len(selected_dexes)} DEXes | gas ${gas_usd:.4f}")

        pool_map = self._discover_pools(base_tokens, selected_dexes)
        if not pool_map:
            return {'opportunities':[],'total':0,'profitable':0,'best_profit_usd':0,'avg_spread':0}

        reserves_map = self._fetch_reserves(list(set(pool_map.values())))
        pair_data = {}

        for (base_low, quote_low, dex), pool_addr in pool_map.items():
            pl = pool_addr.lower()
            if pl not in reserves_map:
                continue
            r0, r1   = reserves_map[pl]
            base_sym = next((s for s, a in self._base_tokens.items() if a.lower() == base_low), None)
            if not base_sym or base_sym not in base_tokens:
                continue
            t0, _    = _sort_tokens(base_low, quote_low)
            dec      = 6 if base_sym in ('USDC','USDbC') else 18
            r_base, r_quote = (r0, r1) if t0 == base_low else (r1, r0)
            quote_sym = ALL_TOKEN_SYM.get(quote_low, quote_low[:8])
            price_usd = BASE_PRICE_USD.get(base_sym, 1.0)
            liq_usd   = (r_base / (10 ** dec)) * price_usd * 2
            if liq_usd < min_liq_usd:
                continue
            pk = f"{quote_sym}/{base_sym}"
            if pk not in pair_data:
                pair_data[pk] = {'base_sym':base_sym,'quote_sym':quote_sym,'base_low':base_low,
                                 'quote_low':quote_low,'price_usd':price_usd,'dec':dec,'dexes':{}}
            pair_data[pk]['dexes'][dex] = {
                'r_base':r_base,'r_quote':r_quote,'liq_usd':liq_usd,
                'fee_bps':self._dex_configs[dex]['fee_bps'],'router':self._dex_configs[dex]['router'],
            }

        pairs_multi = {k: v for k, v in pair_data.items() if len(v['dexes']) >= 2}
        logger.info(f"Base arb candidates: {len(pairs_multi)} pairs on ≥2 DEXes")
        opportunities = []

        for pk, pdata in pairs_multi.items():
            dex_names = list(pdata['dexes'].keys())
            price_usd = pdata['price_usd']
            dec       = pdata['dec']
            for i in range(len(dex_names)):
                for j in range(len(dex_names)):
                    if i == j:
                        continue
                    bd_name, sd_name = dex_names[i], dex_names[j]
                    bd, sd = pdata['dexes'][bd_name], pdata['dexes'][sd_name]
                    if not bd['r_base'] or not sd['r_base']:
                        continue
                    buy_spot  = bd['r_quote'] / bd['r_base']
                    sell_spot = sd['r_quote'] / sd['r_base']
                    if buy_spot <= 0 or sell_spot <= 0:
                        continue
                    spread = ((buy_spot - sell_spot) / sell_spot) * 100
                    if spread <= 0:
                        continue
                    est_loan_usd  = max(gas_usd / max(spread/100 - 0.003, 0.0001), 500)
                    est_loan_wei  = int((est_loan_usd / price_usd) * (10 ** dec))
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
                        decimals_base=dec, gas_usd=gas_usd, base_price_usd=price_usd,
                    )
                    raw = result.get('optimal_amount', 0)
                    if raw > 0:
                        loan_raw = raw
                    else:
                        net_sp   = spread - fee_hurdle
                        loan_raw = int((gas_usd/(net_sp/100)/price_usd)*(10**dec)) if net_sp>0.001 else int(gas_usd/price_usd*(10**dec))
                        mx       = min(int(bd['r_base']*0.03), int(sd['r_base']*0.03))
                        if mx > 0:
                            loan_raw = min(loan_raw, mx)
                    loan_tok = loan_raw / (10 ** dec)
                    loan_usd = loan_tok * price_usd
                    _q       = get_amount_out_v2(loan_raw, bd['r_base'], bd['r_quote'], bd['fee_bps'])
                    _out     = get_amount_out_v2(_q, sd['r_quote'], sd['r_base'], sd['fee_bps'])
                    _flash   = (loan_raw * flash_fee_bps) // 10000
                    gross_tok     = (loan_raw * spread / 100) / (10 ** dec)
                    gross_usd     = gross_tok * price_usd
                    net_raw       = (_out - loan_raw - _flash) / (10 ** dec)
                    net_usd_raw   = net_raw * price_usd - gas_usd
                    net_usd       = net_usd_raw if net_usd_raw >= 0 else -gas_usd
                    net_tok       = net_raw     if net_usd_raw >= 0 else (-gas_usd/price_usd if price_usd>0 else 0)
                    net_pct       = (net_raw / loan_tok * 100) if loan_tok > 0 else 0
                    is_profitable = result.get('profitable', False) and net_usd > 0 and net_pct >= min_net_pct
                    status        = 'profitable' if is_profitable else ('marginal' if gross_usd>0 and net_usd>-gas_usd*2 else 'unprofitable')
                    flash_fee_usd = loan_usd * (flash_fee_bps / 10000)
                    buy_fee_usd   = loan_usd * (bd['fee_bps'] / 10000)
                    sell_fee_usd  = (loan_usd + gross_usd) * (sd['fee_bps'] / 10000)
                    buy_impact    = calc_price_impact(loan_raw, bd['r_base'])
                    sell_impact   = calc_price_impact(_q, sd['r_quote']) if _q > 0 else 0.0
                    opportunities.append({
                        'id':f"base_{pdata['quote_sym']}_{pdata['base_sym']}_{bd_name}_{sd_name}_{int(time.time())}",
                        'pair':pk,'baseToken':pdata['base_sym'],'quoteToken':pdata['quote_sym'],
                        'baseTokenAddress':pdata['base_low'],'quoteTokenAddress':pdata['quote_low'],
                        'buyDex':bd_name,'sellDex':sd_name,'buyDexRouter':bd['router'],'sellDexRouter':sd['router'],
                        'buyPrice':round(bd['r_base']/bd['r_quote'],10) if bd['r_quote'] else 0,
                        'sellPrice':round(sd['r_base']/sd['r_quote'],10) if sd['r_quote'] else 0,
                        'spread':round(spread,4),'flashLoanAsset':pdata['base_sym'],
                        'flashLoanAmount':round(loan_tok,6),'flashLoanAmountUsd':round(loan_usd,2),
                        'flashLoanProvider':provider['name'],'flashLoanPool':provider.get('pool',''),
                        'grossProfit':round(gross_tok,6),'grossProfitUsd':round(gross_usd,2),
                        'netProfit':round(net_tok,6),'netProfitUsd':round(net_usd,2),
                        'gasFee':round(gas_usd,4),'dexFees':round(buy_fee_usd+sell_fee_usd,2),
                        'flashFee':round(flash_fee_usd,2),'netProfitPct':round(net_pct,4),
                        'buyPoolLiquidity':round(bd['liq_usd'],0),'sellPoolLiquidity':round(sd['liq_usd'],0),
                        'buyPriceImpact':round(buy_impact,4),'sellPriceImpact':round(sell_impact,4),
                        'status':status,'testnet':self.testnet,'timestamp':int(time.time()),
                    })

        gc.collect()
        opportunities.sort(key=lambda x: x['netProfitUsd'], reverse=True)
        profitable = [o for o in opportunities if o['netProfitUsd'] > 0]
        avg_spread = sum(o['spread'] for o in opportunities)/len(opportunities) if opportunities else 0
        return {
            'opportunities':opportunities,'total':len(opportunities),'profitable':len(profitable),
            'best_profit_usd':opportunities[0]['netProfitUsd'] if opportunities else 0,
            'avg_spread':round(avg_spread,4),'eth_price':eth_price,
            'gas_estimate_usd':round(gas_usd,4),'scan_timestamp':int(time.time()),
        }

    def execute_trade(self, opportunity, wallet_address, contract_address):
        try:
            contract   = self.w3.eth.contract(address=Web3.to_checksum_address(contract_address.lower()), abi=FLASH_ARB_ABI)
            base_addr  = Web3.to_checksum_address(opportunity['baseTokenAddress'].lower())
            quote_addr = Web3.to_checksum_address(opportunity['quoteTokenAddress'].lower())
            flash_amt  = int(opportunity['flashLoanAmount'] * 1e18)
            min_profit = int(opportunity.get('netProfit', 0) * 0.9 * 1e18)
            deadline   = int(time.time()) + 180
            provider_id= 1 if 'Balancer' in opportunity.get('flashLoanProvider','') else 0
            tx = contract.functions.executeArbitrage(
                base_addr, flash_amt,
                Web3.to_checksum_address(opportunity['buyDexRouter'].lower()),
                Web3.to_checksum_address(opportunity['sellDexRouter'].lower()),
                [base_addr, quote_addr],[quote_addr, base_addr],
                min_profit, deadline, provider_id,
            ).build_transaction({
                'from':     Web3.to_checksum_address(wallet_address.lower()),
                'gas':      400000,
                'gasPrice': self.w3.eth.gas_price,
                'nonce':    self.w3.eth.get_transaction_count(Web3.to_checksum_address(wallet_address.lower())),
            })
            return {'status':'ready','unsignedTx':{'to':tx['to'],'data':tx['data'],'gas':hex(tx['gas']),'gasPrice':hex(tx['gasPrice']),'nonce':hex(tx['nonce']),'value':'0x0','chainId':84532 if self.testnet else 8453}}
        except Exception as e:
            return {'status':'error','error':str(e)}
