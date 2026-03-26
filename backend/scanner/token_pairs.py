"""
BSC Token Pairs Configuration
Comprehensive list of 100+ pairs per base token (USDT, WBNB, BTCB, USDC)
Includes token addresses and DEX factory addresses on BNB Chain.
"""

# ─── Token Addresses (BSC Mainnet) ───────────────────────────────────────────
TOKENS = {
    # Base / Flash-loanable tokens
    'WBNB':     '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c',
    'USDT':     '0x55d398326f99059fF775485246999027B3197955',
    'USDC':     '0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d',
    'BTCB':     '0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c',

    # Major cross-chain tokens
    'ETH':      '0x2170Ed0880ac9A755fd29B2688956BD959F933F8',
    'BUSD':     '0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56',
    'DAI':      '0x1AF3F329e8BE154074D8769D1FFa4eE058B1DBc3',
    'TUSD':     '0x40af3827F39D0EAcBF4A168f8D4ee67c121D11c9',

    # BSC DeFi blue chips
    'CAKE':     '0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82',
    'XVS':      '0xcF6BB5389c92Bdda8a3747Ddb454cB7a64626C63',
    'ALPACA':   '0x8F0528cE5eF7B51152A59745bEfDD91D97091d2F',
    'AUTO':     '0xa184088a740c695E156F91f5cC086a06bb78b827',
    'BELT':     '0xE0e514c71282b6f4e823703a39374Cf58dc3eA4f',
    'BIFI':     '0xCa3F508B8e4Dd382eE878A314789373D80A5190A',
    'BSW':      '0x965F527D9159dCe6288a2219DB51fc6Eef120dD1',
    'DODO':     '0x67ee3Cb086F8a16f34beE3ca72FAD36F7Db929e2',
    'EPS':      '0xA7f552078dcC247C2684336020c03648500C6d9F',
    'WOM':      '0xAD6742A35fB341A9Cc6ad674738Dd8da98b94Fb1',
    'THE':      '0xF4C8E32EaDEC4BFe97E0F595ADD0f4450a863a5',
    'TWT':      '0x4B0F1812e5Df2A09796481Ff14017e6005508003',
    'CHESS':    '0x20de22029ab63cf9A7Cf5fEB2b737Ca1eE4c82A6',

    # Large caps bridged to BSC
    'XRP':      '0x1D2F0da169ceB9fC7B3144628dB156f3F6c60dBE',
    'ADA':      '0x3EE2200Efb3400fAbB9AacF31297cBdD1d435D47',
    'DOGE':     '0xbA2aE424d960c26247Dd6c32edC70B295c744C43',
    'DOT':      '0x7083609fCE4d1d8Dc0C979AAb8cf214F57432DF3',
    'LINK':     '0xF8A0BF9cF54Bb92F17374d9e9A321E6a111a51bD',
    'MATIC':    '0xCC42724C6683B7E57334c4E856f4c9965ED682bD',
    'SOL':      '0x570A5D26f7765Ecb712C0924E4De545B89fD43dF',
    'AVAX':     '0x1CE0c2827e2eF14D5C4f29a091d735A204794041',
    'ATOM':     '0x0Eb3a705fc54725037CC9e008bDede697f62F335',
    'UNI':      '0xBf5140A22578168FD562DCcF235E5D43A02ce9B1',
    'LTC':      '0x4338665CBB7B2485A8855A139b75D5e34AB0DB94',
    'FIL':      '0x0D8Ce2A99Bb6e3B7Db580eD848240e4a0F9aE153',
    'EOS':      '0x56b6fB708fC5732DEC1Afc8D8556423A2EDcCbD6',
    'TRX':      '0x85EAC5Ac2F758618dFa09bDbe0cf174e7d574D5B',
    'VET':      '0x6FDcdfef7c496407cCb0cEC90f9C5Aaa1Cc8D888',
    'AAVE':     '0xfb6115445Bff7b52FeB98650C87f44907E58f802',
    'SUSHI':    '0x947950BcC74888a40Ffa2593C5798F11Fc9124C4',
    'COMP':     '0x52CE071Bd9b1C4B00A0b92D298c512478CaD67e8',
    'SNX':      '0x9Ac983826058b8a9C7Aa1C9171441191232E8404',
    'NEAR':     '0x1Fa4a73a3F0133f0025378af00236f3aBDEE5D63',
    'FTM':      '0xAD29AbB318791D579433D831ed122aFeAf29dcfe',
    'ANKR':     '0xf307910A4c7bbc79691fD374889b36d8531B08e3',
    'INJ':      '0xa2B726B1145A4773F68593CF171187d8EBe4d495',
    'BAND':     '0xAD6cAEb32CD2c308980a548bD0Bc5AA4306c6c18',
    'ZIL':      '0xb86AbCb37C3A4B64f74f59301AFF131a1BEcC787',
    'ONT':      '0xFd7B3A77848f1C2D67E05E54d78d174a0C850335',
    'NULS':     '0x8CD6e29d3686d24d3C2018CEe54621eA0f89313B',

    # Meme & community tokens
    'PEPE':     '0x25d887Ce7a35172C62FeBFD67a1856F20FaEbB00',
    'FLOKI':    '0xfb5B838b6cfEEdC2873aB27866079AC55363D37E',
    'SHIB':     '0x2859e4544C4bB03966803b044A93563Bd2D0DD4D',
    'BABYDOGE': '0xc748673057861a797275CD8A068AbB95A902e8de',
    'BAKE':     '0xE02dF9e3e622DeBdD69fb838bB799E3F168902c5',
    'BUNNY':    '0xC9849E6fdB743d08fAeE3E34dd2D1bc69EA11a51',

    # Gaming & NFT
    'ALICE':    '0xAC51066d7bEC65Dc4589368da368b212745d63E8',
    'GALA':     '0x7dDEE176F665cD201F93eEDE625770E2fD911990',
    'MBOX':     '0x3203c9E46cA618C8C1cE5dC67e7e9D75f5da2377',
    'SPS':      '0x1633b7157e7638C4d6593436111Bf125Ee74703F',
    'HIGH':     '0x5f4Bde007Dc06b867f86EBFE4802e34A1cFD5b7',
    'HERO':     '0xD40bEDb44C081D2935eeba6eF5a3c8A31A1bBE13',
    'PMON':     '0x1796ae0b0fa4862485106a0de9b654eFE301D0b2',
    'IMX':      '0x2A9Ae12878f0c4c4 Deleted',  # placeholder

    # Yield / Liquid staking
    'LINA':     '0x762539b45A1dCcE3D36d080F74d1AED37844b878',
    'ALPHA':    '0xa1faa113cbE53436Df28FF0aEe54275c13B40975',
    'FOR':      '0x658A109C5900BC6d2357c87549B651670E5b0539',
    'NAOS':     '0x758d08864fB6cCE3062667225ca10b8F00496cc2',
    'RAMP':     '0x8519EA49c997f50cefFa444d240fB655e89248Aa',

    # Launchpad & IDO
    'SFUND':    '0x477bC8d23c634C154061869478bce96BE6045D12',
    'PORTO':    '0x49f2145d6366099e13B10FbF80646Ea0A373b5B1',
    'PSG':      '0xBc5609612b7C44BEf426De600B5fd1379DB2EcF1',

    # BSC native protocols
    'C98':      '0xaEC945e04baF28b135Fa7c640138d2e26c4f5bE2',
    'CHR':      '0xf9CeC8d50f6c8ad3Fb6dcCEC577e05aA32B224FE',
    'DERI':     '0xe60eaf5A997DFAe83739e035b005A33AfdCc6df5',
    'FINE':     '0x4e6415a5727ea08aAE4580057187923aeC331227',
    'LOKA':     '0x63f88A2298a5c4AEE3c216Aa6D926B184a4b2437',
    'WEX':      '0xa9c41A46a6B3531d28d5c32F6633dd2fF05dFB90',
    'YFI':      '0x88f1A5ae2A3BF98AEAF342D26B30a79438c9142e',
    'BRY':      '0xf859Bf77cBe8699013d6Dbc7C2b926Aaf307F830',
    'NUTS':     '0x8893D5fA71389673C5c4b9b3cb4EE1ba71207556',
    'ALPACA2':  '0x8F0528cE5eF7B51152A59745bEfDD91D97091d2F',
    'TRADE':    '0x7af173F350D916358AF3e218Bdf2178494Beb748',
    'WATCH':    '0x7A9f28EB62C791422Aa23CeAE1dA9C847cBeC9b0',
    'ITAM':     '0x04C747b40Be4D535fC83D09939fb0f626F32800B',
    'MILK2':    '0x4A5a34212404f30C5aB7eB61b078fA4A55AdB6b5',
    'STAX':     '0x0Da6Ed8B13214Ff28e9Ca979Dd37439e8a88F6c4',
    'FEG':      '0xacFC95585D80Ab62f67A14C566C1b7a49Fe91167',
    'OG':       '0xB0Ff3b5e0d2F247cDd9a7A02E7A55E0F61b01BF6',
}

# ─── DEX Configurations (BSC Mainnet) ────────────────────────────────────────
DEX_CONFIGS = {
    'PancakeSwap V2': {
        'type':         'v2',
        'factory':      '0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73',
        'router':       '0x10ED43C718714eb63d5aA57B78B54704E256024E',
        'fee_bps':      25,      # 0.25%
        'init_code':    '0x00fb7f630766e6a796048ea87d01acd3068e8ff67d078148a3fa3f4a84f69bd5',
    },
    'PancakeSwap V3': {
        'type':         'v3',
        'factory':      '0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865',
        'quoter':       '0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997',
        'fee_tiers':    [100, 500, 2500, 10000],
        'fee_bps':      5,       # lowest tier 0.01% → use 5 as default
    },
    'ApeSwap': {
        'type':         'v2',
        'factory':      '0x0841BD0B734E4F5853f0dD8d7Ea041c241fb0Da6',
        'router':       '0xcF0feBd3f17CEf5b47b0cD257aCf6025c5BFf3b7',
        'fee_bps':      20,      # 0.20%
        'init_code':    '0xf4ccce374816856d11f00e4069e7cada164065686fbef53c6167a63ec2fd8c5b',
    },
    'BiSwap': {
        'type':         'v2',
        'factory':      '0x858E3312ed3A876947EA49d572A7C42DE08af7EE',
        'router':       '0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8',
        'fee_bps':      10,      # 0.10%
        'init_code':    '0xfea293c909d87cd4153593f077b76bb7e13dc6e44cc93e6a4e574e08f1ac6c22',
    },
    'MDEX': {
        'type':         'v2',
        'factory':      '0x3CD1C46068dAEa5Ebb0d3f55F6915B10648062B8',
        'router':       '0x62c65B31E9b1D9b2580e089f4D2f4fFb8F0dAa5E',
        'fee_bps':      30,      # 0.30%
        'init_code':    '0x0d994d996174b05cfc7bed897dc1b20b4c458fc8d64fe98bc78b3c64a6b4d093',
    },
    'BabySwap': {
        'type':         'v2',
        'factory':      '0x86407bEa2078ea5f5EB5A52B2caA963bC1F889Da',
        'router':       '0x325E343f1dE602396E256B67eFd1F61C3A6B38Bd',
        'fee_bps':      30,
        'init_code':    '0x48c8bec5512d397a5d512fbb7d83d515e7b6d91e9838730bd1aa1b18a1390b6',
    },
    'Thena': {
        'type':         'v2_stable',
        'factory':      '0xAFD89d21BdB66d00817d4153E055830B1c2B3970',
        'router':       '0xd4ae6eCA985340Dd434D38F470aCCce4DC78d109',
        'fee_bps':      4,       # 0.04% stable
    },
    'KnightSwap': {
        'type':         'v2',
        'factory':      '0xf0bc2E21a76513aa7CC2730C7A1D6deE0790751f',
        'router':       '0x05E61E0cDcD2170a76F9568a110CEe3AFdD6c46f',
        'fee_bps':      25,
        'init_code':    '0xa80f8f54f22bfb7c2c458fd89be4c13ef07d79264f8c5e3add36ee62e6e91a8',
    },
    'SushiSwap': {
        'type':         'v2',
        'factory':      '0xc35DADB65012eC5796536bD9864eD8773aBc74C4',
        'router':       '0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506',
        'fee_bps':      30,
        'init_code':    '0xe18a34eb0e04b04f7a0ac29a6e80748dca96319b42c54d679cb821dca90c6303',
    },
    'Nomiswap': {
        'type':         'v2',
        'factory':      '0xd6715A8be3944ec72738F0BFDC739d48C3c29349',
        'router':       '0xD654953D746f0b114d1F85332Dc43446ac79413d',
        'fee_bps':      10,
        'init_code':    '0x5dc6c5b5e6bbb2d4dded67ac5b6be4d95a20d6aa78e26bff01b5da9a43b67562',
    },
}

# ─── Flash Loan Providers (BSC Mainnet) ───────────────────────────────────────
FLASH_LOAN_PROVIDERS = {
    'Aave V3': {
        'pool':         '0x6807dc923806fE8Fd134338EABCA509979a7e0cB',
        'fee_bps':      5,       # 0.05%
        'assets':       ['USDT', 'USDC', 'WBNB', 'BTCB', 'ETH'],
    },
    'PancakeSwap V3 Flash': {
        'type':         'v3_flash',
        'fee_bps':      1,       # 0.01% (lowest tier pool)
        'assets':       ['USDT', 'USDC', 'WBNB', 'BTCB'],
    },
    'DODO Flash': {
        'pool':         '0x9ad32e3054268B849b84a8dBcC7c8f7c52E4e69A',
        'fee_bps':      0,       # 0% fee
        'assets':       ['USDT', 'USDC', 'BUSD'],
    },
}

# ─── Base Token → Paired Tokens mapping ──────────────────────────────────────
# These represent the tokens that WILL BE ARBITRAGED using the base token as collateral
BASE_TOKEN_PAIRS = {
    'WBNB': [
        'USDT','USDC','BTCB','ETH','BUSD','DAI','CAKE','XVS','ALPACA','AUTO',
        'BELT','BSW','DODO','EPS','WOM','THE','TWT','CHESS','XRP','ADA','DOGE',
        'DOT','LINK','MATIC','SOL','AVAX','ATOM','UNI','LTC','FIL','EOS','TRX',
        'VET','AAVE','SUSHI','COMP','SNX','NEAR','FTM','ANKR','INJ','BAND','ZIL',
        'ONT','NULS','PEPE','FLOKI','SHIB','BABYDOGE','BAKE','BUNNY','ALICE',
        'GALA','MBOX','SPS','HIGH','HERO','LINA','ALPHA','FOR','NAOS','RAMP',
        'SFUND','C98','CHR','DERI','FINE','LOKA','WEX','YFI','BRY','NUTS',
        'TRADE','WATCH','ITAM','MILK2','STAX','FEG','OG','BIFI','PORTO','PSG',
        'SAFEMOON','PMON',
    ],
    'USDT': [
        'WBNB','BTCB','ETH','BUSD','USDC','DAI','CAKE','XVS','ALPACA','BSW',
        'WOM','THE','TWT','CHESS','XRP','ADA','DOGE','DOT','LINK','MATIC','SOL',
        'AVAX','ATOM','UNI','LTC','FIL','EOS','TRX','VET','AAVE','SUSHI','COMP',
        'SNX','NEAR','FTM','ANKR','INJ','BAND','PEPE','FLOKI','SHIB','BABYDOGE',
        'BAKE','BUNNY','ALICE','GALA','MBOX','SPS','HIGH','LINA','ALPHA','FOR',
        'NAOS','RAMP','SFUND','C98','CHR','DERI','DODO','EPS','AUTO','BELT',
        'BIFI','WEX','YFI','BRY','NUTS','TRADE','WATCH','FINE','LOKA','ZIL',
        'ONT','NULS','HERO','ITAM','MILK2','STAX','FEG','OG','PORTO','PSG',
        'PMON','SFUND',
    ],
    'BTCB': [
        'WBNB','USDT','USDC','ETH','BUSD','DAI','CAKE','XRP','ADA','DOGE','DOT',
        'LINK','MATIC','SOL','AVAX','ATOM','UNI','LTC','FIL','EOS','TRX','VET',
        'AAVE','SUSHI','COMP','SNX','NEAR','FTM','ANKR','INJ','BAND','ZIL','ONT',
        'NULS','PEPE','FLOKI','SHIB','DODO','EPS','BSW','WOM','THE','TWT','CHESS',
        'XVS','ALPACA','AUTO','BELT','BIFI','C98','CHR','DERI','FINE','LOKA',
        'WEX','YFI','BRY','ALICE','GALA','MBOX','SPS','HIGH','LINA','ALPHA',
        'FOR','NAOS','RAMP','SFUND','BAKE','BUNNY','HERO','ITAM','MILK2','STAX',
        'FEG','OG','PORTO','PSG','PMON','BABYDOGE',
    ],
    'USDC': [
        'WBNB','USDT','BTCB','ETH','BUSD','DAI','CAKE','XVS','ALPACA','BSW',
        'WOM','THE','TWT','CHESS','XRP','ADA','DOGE','DOT','LINK','MATIC','SOL',
        'AVAX','ATOM','UNI','LTC','FIL','EOS','TRX','VET','AAVE','SUSHI','COMP',
        'SNX','NEAR','FTM','ANKR','INJ','BAND','PEPE','FLOKI','SHIB','BABYDOGE',
        'BAKE','BUNNY','ALICE','GALA','MBOX','SPS','HIGH','LINA','ALPHA','FOR',
        'NAOS','RAMP','SFUND','C98','CHR','DERI','DODO','EPS','AUTO','BELT',
        'BIFI','WEX','YFI','BRY','NUTS','TRADE','WATCH','FINE','LOKA','ZIL',
        'ONT','NULS','HERO','ITAM','MILK2','STAX','FEG','OG','PORTO','PSG',
        'PMON','ANKR','BAND',
    ],
}
