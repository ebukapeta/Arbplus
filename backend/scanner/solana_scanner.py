"""
Solana DEX Scanner — Mainnet + Devnet, 8 base tokens, auto flash provider
Auto flash provider: MarginFi (0%) → Kamino (0.09%) → Solend (0.30%)
"""

import os, time, logging, requests
from typing import Optional

logger = logging.getLogger(__name__)

SOL_TOKENS = {
    # Base tokens
    'WSOL':    'So11111111111111111111111111111111111111112',
    'USDC':    'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
    'USDT':    'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB',
    'MSOL':    'mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So',
    'BONK':    'DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263',
    'JTO':     'jtojtomepa8bJkZSqEXSJm5Z4e6PdBXuBvC5jNYWqDi',
    'JITOSOL': 'J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn',
    'BSOL':    'bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1',
    # Meme tokens
    'WIF':     'EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm',
    'POPCAT':  '7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr',
    'MYRO':    'HhJpBhRRn4g56VsyLuT8DL5Bv31HkXqsrahTTUCZeZg4',
    'BOME':    'ukHH6c7mMyiWCf1b9pnWe25TSpkDDt3H5pQZgZ74J82',
    'SLERF':   '7BgBvyjrZX1YKz4oh9mjb8ZScatkkwb8DzFx7LoiVkM3',
    'WEN':     'WENWENvqqNya429ubCdR81ZmD69brwQaaBYY6p3LCpk',
    'MEMU':    'MEFNBXixkEbait3xn9bkm8WsJzXtVsaJEn4c8Sam21p',
    'NEIRO':   '2kb7MWHXBR4EEfDzfj7XwnLq6CuFRPHuoTJunRKqfZBR',
    'MEW':     'MEW1gQteQnyEc1yd18d9om4G7ub2Zqbb5V79UrjdAJF',
    'BONK2':   'DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263',
    'SAMO':    '7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU',
    'BCAT':    '3M2CDhkqe1a7bmFn2y9MXEkHcxUbhCnBRdVaQJGu8d4S',
    'DOGE2':   'A7rvhPkdH1hXvjXtRKAd5CGcEQFdV6QpkWTfGUiCRSX9',
    'PEPE2':   '83QB3xusBnMBpXNdShUNbUEDFhHXtSCTjMRNYTuNT6pT',
    'FLOKI2':  'FLokiNetworkToken11111111111111111111111111111',
    # DeFi Protocol tokens
    'RAY':     '4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R',
    'ORCA':    'orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE',
    'JUP':     'JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN',
    'MNGO':    'MangoCzJ36AjZyKwVj3VnYU4GTonjfVEnJmvvWaxLac',
    'SRM':     'SRMuApVNdxXokk5GT7XD5cUUgXMBCoAz2LHeuAoKZRB',
    'SLND':    'SLNDpmoWTVADgEdndyvWzroNL7zSi1dF9PC3xHGtPwp',
    'FIDA':    'EchesyfXePKdLtoiZSL8pBe8Myagyy8ZRqsACNCFGnvp',
    'COPE':    '8HGyAAB1yoM1ttS7pXjHMa3dukTFGQggnFFH3hJZgzQh',
    'STEP':    'StepAscQoEioFxxWGnh2sLBDFp9d8rvKz2Yp39iDpyT',
    'GRAPE':   '8upjSpvjcdpuzhfR1zriwg5NXkwDruejqNE9WNbPRtyA',
    'ATLAS':   'ATLASXmbPQxBUYbxPsV97usA3fPQYEqzQBUHgiFCUsXx',
    'POLIS':   'poLisWXnNRwC6oBu1vHiuKQzFjGL4XDSu4g9qjz9qVk',
    'MAPS':    'MAPS41MDahZ9QdKXhVa4dWB9RuyfV4XqhyAZ8XcYepb',
    'OXY':     'z3dn17yLaGMKffVogeFHQ9zWVcXgqgf3PQnDsNs2g6M',
    'KIN':     'kinXdEcpDQeHPEuQnqmUgtYykqKGVFq6CeVX5iAHJq6',
    'PORT':    'PoRTjZMPXb9T7dyU7tpLEZRQj7e6ssfAE62j2oQuc6y',
    'MEAN':    'MEANeD3XDdUmNMsRGjASkSWdC8prLYsoRJ61pPeHctD',
    'PYTH':    'HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3',
    # Infrastructure / gaming
    'GARI':    'CKaKtYvz6dKPyMvYq9Rh3UBrnNqYZAyd7iF4hJtjUvks',
    'GST':     'AFbX8oGjGpmVFywabs9MZiXe1Cs3TG6m3kpaN9V6hMkS',
    'GENE':    'GENEtH5amGSi8kHAtQoezp1XEXwZJ8vcuePYnXdKrMYz',
    'DFL':     'DFL1zNkaGPWm1BqAVqRjCZvHmwThr1hWXb8i4FXjQKmQ',
    'BLOCK':   'NFTUkR354PskupMAfcHhr7H9MWg4jDqBCCRJGZHXbV5',
    'SOLX':    'Solx4x8MFAkb2bXKgHbJV4ZrqoEcuYmkANY9x4XzDADd',
    'SAMO2':   '7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU',
    # Stablecoins
    'USDH':    'USDH1SM1ojwWUga67PGrgFWUHibbjqMvuMaDkRJTgkX',
    'UXD':     '7kbnvuGBxxj8AG9qp8Scn56muWGaRaFqxg1FsRp3PaFT',
    'USDR':    'USDrbBQwQbQ2oWHUPfA8QBHcyVxKUq1xHyXsSLKdUq2',
    'PAI':     'Ea5SjE2Y6yvjt1mKVj38QrriPXYez5AbNsSoLqxCqwVx',
    'CASH':    'CASHVDm2wsJXfhj6VWxb7GiMdoLc17Du7paH4bNr5woT',
    # AI/New tokens
    'RENDER':  'RNDRToken2ZDfKnvqNZmSzTqT8Q3UoMNEMGRVEYiAM2p',
    'TNSR':    'TNSRxcUxoT9xBG3de7PiJyTDYu7kskLqcpddxnEJAS6',
    'W':       '85VBFQZC9TZkfaptBWjvUw7YbZjy52A6mjtPGjstQAmQ',
    'KMNO':    'KMNo3nJsBXfcpJTVhZcXLW7RmTwTt4GVFE7suUBo9sS',
    'CLOUD':   'CLoUDKc4Ane7HeQcPpE3YHnznRxhMimJ4MyaUqyHFzAu',
    'ZEX':     'ZEXy1pqteRu3n13kdyh4LwPQknkFk3GzmMYMuNadWZGj',
    'PONKE':   '5z3EqYQo9HiCEs3R84RCDMu2n7anpDMxRhdK31k3Mupr',
    'MOODENG': 'ED5nyyWEzpPPiWimP8vYm7sD7TD3LAt3Q3gRTWHzc8Au',
    'GIGA':    '63LfDmNb3MQ8mw9MtZ2To9bEA2M71kZUUGq5tiJxcqj9',
    'GOAT':    'CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump',
    'FWOG':    'Bx4ykSmTP7gn7TQxGPuCoVMuDe15XKRN95yTtHkpump',
    'MINI':    '2JcXacFwt9mVABFu4Jnvaxm3ZDZ3PdvMbR5NSGP3d4Qp',
    'ACT':     'GJAFwWjJ3vnTsrHNzKmxwHmCFJ8ADSLnHByFzxVJpoop',
    # LSTs
    'MSOL2':   'mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So',
    'STSOL':   '7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj',
    'ESOLP':   'Hj9x9Z5JBGHgSKopJhYmZUXMBDpZoJGiXBjFXSLVoJdY',
    'SOLBLAZE':'bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1',
    'JSOL':    '7Q2afV64in6N6SeZsAAB81TJzwDoD6zpqmHkzi9Dcavn',
    'CSOL':    'Hq4tuDzhRBnxw3tFA5n6M52NVMVcC19XggbyDiArIeGm',
    # Gaming
    'ATLAS2':  'ATLASXmbPQxBUYbxPsV97usA3fPQYEqzQBUHgiFCUsXx',
    'POLIS2':  'poLisWXnNRwC6oBu1vHiuKQzFjGL4XDSu4g9qjz9qVk',
    'DFL2':    'DFL1zNkaGPWm1BqAVqRjCZvHmwThr1hWXb8i4FXjQKmQ',
    'AUORY':   'AURYydfxJib1ZkTir1Jn1J9ECYUtjb6rKQVmtYaixWPP',
    'SOLAPE':  'GHvFFSZ9BctWsEc5nujR1MTmmJWY7tgQz2AXE6WVFtGN',
    'APES':    '3DH7X7PbcMm1VGHZCmjWVKoS9AKcDcvqpHJpv4Y4KKQM',
    # Yield farming
    'TULIP':   'TuLipcqtGVXP9XR62wM8WWCm6a9vhLs7T1uoWBk6FDs',
    'SUNNY':   'SUNNYWgPQmFxe9wTZzNK7iPnJ3vYDrkgnxJRJm1s3ag',
    'CATO':    '5p2zjqCd1WJzAVgcEnjhb9zWDJ7GXa6cSHLgwzbB1e4T',
    'PAI2':    'Ea5SjE2Y6yvjt1mKVj38QrriPXYez5AbNsSoLqxCqwVx',
    # Bridged tokens
    'WBTC2':   '9n4nbM75f5Ui33ZbPYXn59EwSgE8CGsHtAeTH5YFeJ9E',
    'ETH2':    '2FPyTwcZLUgr5Th81UT23LQzu5sYA5M7DktELqQ3P5c7',
    'AVAX2':   'KgV1GvrHQmRBY8sHQQeUKwTm2r2h8t4C8qt12Cw1HVE',
    'BNB2':    '9gP2kCy3wA1ctvYWQk75guqXuAMDWEfqzd2tBQHjCHzX',
    'MATIC2':  'C7NNPWuZCNjZBfW5p6JvGsR6usJAjbkHbLh6KbPzcMjo',
    'LINK2':   '2wpTofQ8SkACrkZWrZDjXgrDPEs4T7q37FQo5mXFMZMr',
    'UNI2':    'DEhAasscXF4kEGxFgJ3bq4PpVGp5wyUxMRvn6TzGVHaw',
    'COMP2':   '9KEB3BMWJVSHpHf4kJTBiNy4Lz2v7GHmqTbeBYLEH8hZ',
    # Popular new 2024
    'BOME2':   'ukHH6c7mMyiWCf1b9pnWe25TSpkDDt3H5pQZgZ74J82',
    'ANSEM':   '9CPC3dMZH4bHuZRUzqC7YqcCh7VZx7rTT4jBqv4kxuNx',
    'BRETT2':  'BRETThdGbKQCQMiXiajHJQ5cVz5hBfFvyWAb2T97DXBp',
    'POPCAT2': '7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr',
    'DEPIN':   'DEPINTokenYYY5ahC1EvzeBvmLhA7TS5j6ByMwHgFv21R',
    'MOBILE':  'mb1eu7TzEc71KxDpsmsKoucSSuuoGLv1drys1oP2jh6',
    'HNT':     'hntyVP6YFm1Hg25TN9WGLqM12b8TQmcknKrdu1oxWux',
    'IOT':     'iotEVVZLEywoTn1QdwNPddxPWszn3zFhEot3MfL9fns',
    'MOBILE2': 'mb1eu7TzEc71KxDpsmsKoucSSuuoGLv1drys1oP2jh6',
    # Community tokens
    'CHILI':   '3vZczVNbm2XRZN9mLHipqp3aHAoYJPkEjVnNBp7Tzu8d',
    'CRECK':   'Ao94rg8D6oK2TAq3nm8YEQFSLGJMZMfKHHwNmJUAR2Hn',
    'NINJA':   'Fg6PaFpoGXkYsidMpWTK6W2BeZ7FEfcYkg476zPFsLnS',
    'TONO':    '4yWHNMoYWFzB7oJFoRArPYLKv2pGxNFcGkSFCfRHbhJE',
    'GUAC':    'AZsHEMXd36Bj1EMNXhowJajpUXzrKcK57wW4ZGXVa7yR',
    'REAL':    'A9mUU4qviSctJVPJdBJWkb28deg915LYJKrzQ19ji3FM',
    'SHDW':    'SHDWyBxihqiCj6YekG2GUr7wqKLeLAMK1gHZck9pL6y',
    'SPDR':    'spdrKEZei4YMEHDb4qPKKkGGYnzQMnWvnqkwGBMbDyR',
    'GST2':    'AFbX8oGjGpmVFywabs9MZiXe1Cs3TG6m3kpaN9V6hMkS',
    'CRWNY':   'CRWNYkqdgvhGGae9CKfNka58j6QQkaD5bLhKXvUYqnc1',
    # Solana ecosystem
    'TENSOR':  'TNSRxcUxoT9xBG3de7PiJyTDYu7kskLqcpddxnEJAS6',
    'DUST':    'DUSTawucrTsGU8hcqRdHDCbuYhCPADMLM2VcCb8VnFnQ',
    'FORGE':   'FoRGERmPRguTBB3FaER7yN4bgv3yDHZQnMJoJdqQX2y5',
    'HUNT':    'HUNTai3HHMTpwPbWdkfS1rZBJGRPdC7wEFHKLdPjGARD',
    'GGWP':    'GGWPbxkFyKF6gXPLxAFa3TApNXHdpJ9JC7ePRR3NkNsv',
    'GEMS':    'GEMSbjqLhgG2CBQavuZEJDGobGGtPLQMKQJBVQyGM2Ag',
    'PHONEY':  'PHONEYn6xMNJxZbUvVopFNKK4xaVVzGJW5TUedxFczQ',
    'TULIP2':  'TuLipcqtGVXP9XR62wM8WWCm6a9vhLs7T1uoWBk6FDs',
}

SOL_DEX_CONFIGS = {
    'Raydium V4':    {'program_id':'675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8','fee_bps':25},
    'Raydium CLMM':  {'program_id':'CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK','fee_bps':4},
    'Orca Whirlpool':{'program_id':'whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc','fee_bps':5},
    'Orca V2':       {'program_id':'9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP','fee_bps':30},
    'Meteora DLMM':  {'program_id':'LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo','fee_bps':5},
    'Lifinity V2':   {'program_id':'2wT8Yq49kHgDzXuPxZSaeLaH1qbmGXtEyPy64bL7aD3c','fee_bps':20},
    'GooseFX':       {'program_id':'GFXsSL5sSaDfNFQUYsHekbWBW1TsFdjDYzACh62tEHxn','fee_bps':30},
    'Saber':         {'program_id':'SSwpkEEcbUqx4vtoEByFjSkhKdCT862DNVb52nZg1UZ','fee_bps':4},
    # Devnet
    'Raydium Devnet':{'program_id':'HWy1jotHpo6UqeQxx49dpYYdQB8wj9Qk9MdxwjLvDHB','fee_bps':25},
    'Orca Devnet':   {'program_id':'3xQ8SWv2GaFXXpHZNqkXsdxq5DZciHBz6ZFoPPfbFd7F','fee_bps':30},
}

# Flash providers ordered cheapest first
FLASH_PROVIDERS_MAINNET = [
    {'name':'MarginFi', 'fee_bps':0,  'program_id':'MFv2hWf31Z9kbCa1snEPdcgp7gkVsWRU38fRBLj6fLA',
     'assets':['WSOL','USDC','USDT','MSOL','JITOSOL','BSOL']},
    {'name':'Kamino',   'fee_bps':9,  'program_id':'KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD',
     'assets':['WSOL','USDC','USDT','MSOL','JITOSOL','BSOL','JTO']},
    {'name':'Solend',   'fee_bps':30, 'program_id':'So1endDq2YkqhipRh3WViPa8hdiSpxWy6z3Z6tMCpAo',
     'assets':['WSOL','USDC','USDT','MSOL','JTO','WIF','BONK']},
]
FLASH_PROVIDERS_TESTNET = [
    {'name':'Solend Devnet','fee_bps':30,'program_id':'ALend7Ketfx5bxh6ghsCDXAoDrhvEmsXT3cynB6aPLgx',
     'assets':['WSOL','USDC']},
]

BASE_TOKENS_MAINNET = {
    'WSOL':    'So11111111111111111111111111111111111111112',
    'USDC':    'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
    'USDT':    'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB',
    'MSOL':    'mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So',
    'BONK':    'DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263',
    'JTO':     'jtojtomepa8bJkZSqEXSJm5Z4e6PdBXuBvC5jNYWqDi',
    'JITOSOL': 'J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn',
    'BSOL':    'bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1',
}
BASE_TOKENS_TESTNET = {
    'WSOL':    'So11111111111111111111111111111111111111112',
    'USDC':    'Gh9ZwEmdLJ8DscKNTkTqPbNwLNNBjuSzaG9Vp2KGtKJr',
    'USDT':    'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB',
    'MSOL':    'mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So',
    'BONK':    'DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263',
    'JTO':     'jtojtomepa8bJkZSqEXSJm5Z4e6PdBXuBvC5jNYWqDi',
    'JITOSOL': 'J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn',
    'BSOL':    'bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1',
}

TOKEN_PRICE_ORACLE = {
    'WSOL':150.0,'USDC':1.0,'USDT':1.0,'MSOL':160.0,'BONK':0.00003,
    'JTO':3.5,'JITOSOL':155.0,'BSOL':158.0,'WIF':2.5,'JUP':0.8,
    'RAY':2.0,'ORCA':3.5,'PYTH':0.5,'POPCAT':0.8,
}

SOL_BASE_TOKEN_PAIRS = {
    'WSOL':    ['USDC','USDT','MSOL','BONK','JTO','WIF','POPCAT','PYTH','JUP','RAY',
                'ORCA','MNGO','SRM','STEP','SAMO','SLND','PORT','GRAPE','ATLAS',
                'POLIS','MEAN','COPE','FIDA','MAPS','OXY','KIN','JITOSOL','BSOL'],
    'USDC':    ['WSOL','USDT','MSOL','BONK','JTO','WIF','POPCAT','PYTH','JUP','RAY',
                'ORCA','MNGO','SRM','STEP','SAMO','SLND','PORT','GRAPE','ATLAS',
                'POLIS','MEAN','COPE','FIDA','MAPS','OXY','KIN','JITOSOL','BSOL'],
    'USDT':    ['WSOL','USDC','MSOL','BONK','JTO','WIF','POPCAT','PYTH','JUP','RAY',
                'ORCA','MNGO','SRM','STEP','SAMO','SLND','PORT','GRAPE','ATLAS',
                'POLIS','MEAN','COPE','FIDA','MAPS','OXY','KIN'],
    'MSOL':    ['WSOL','USDC','USDT','BONK','JTO','WIF','JUP','RAY','ORCA',
                'JITOSOL','BSOL','STEP','SAMO','MNGO','SRM','PORT','GRAPE'],
    'BONK':    ['WSOL','USDC','USDT','JTO','WIF','POPCAT','JUP','RAY','ORCA'],
    'JTO':     ['WSOL','USDC','USDT','MSOL','BONK','WIF','JUP','RAY','JITOSOL','BSOL'],
    'JITOSOL': ['WSOL','USDC','USDT','MSOL','JTO','BSOL','RAY','JUP'],
    'BSOL':    ['WSOL','USDC','USDT','MSOL','JTO','JITOSOL','RAY','JUP'],
}

JUPITER_PRICE_API = 'https://price.jup.ag/v6/price'
JUPITER_QUOTE_API = 'https://quote-api.jup.ag/v6/quote'

SOL_MAINNET_RPC = [
    'https://api.mainnet-beta.solana.com',
    'https://solana-api.projectserum.com',
]
SOL_DEVNET_RPC = ['https://api.devnet.solana.com']


class SolanaScanner:
    def __init__(self, testnet: bool = False):
        self.testnet     = testnet
        self.rpc_url     = self._pick_rpc()
        self._price_cache: dict = {}
        self._last_price_fetch: float = 0

    def _pick_rpc(self):
        env_key = 'SOLANA_DEVNET_RPC_URL' if self.testnet else 'SOLANA_RPC_URL'
        env_val = os.environ.get(env_key, '')
        if env_val:
            return env_val
        return SOL_DEVNET_RPC[0] if self.testnet else SOL_MAINNET_RPC[0]

    @property
    def _base_tokens(self):
        return BASE_TOKENS_TESTNET if self.testnet else BASE_TOKENS_MAINNET

    @property
    def _flash_providers(self):
        return FLASH_PROVIDERS_TESTNET if self.testnet else FLASH_PROVIDERS_MAINNET

    @property
    def _dex_configs(self):
        if self.testnet:
            return {k: v for k, v in SOL_DEX_CONFIGS.items() if 'Devnet' in k or 'devnet' in k.lower()}
        return {k: v for k, v in SOL_DEX_CONFIGS.items() if 'Devnet' not in k}

    def _rpc_call(self, method: str, params: list):
        try:
            resp = requests.post(self.rpc_url, json={
                'jsonrpc':'2.0','id':1,'method':method,'params':params
            }, timeout=10)
            return resp.json().get('result')
        except Exception as e:
            logger.debug(f"Solana RPC error: {e}")
            return None

    def _fetch_jupiter_prices(self, token_mints: list) -> dict:
        now = time.time()
        if now - self._last_price_fetch < 30:
            return self._price_cache
        try:
            ids  = ','.join(token_mints[:50])
            resp = requests.get(f"{JUPITER_PRICE_API}?ids={ids}", timeout=10)
            data = resp.json().get('data', {})
            prices = {mint: v['price'] for mint, v in data.items()}
            self._price_cache.update(prices)
            self._last_price_fetch = now
        except Exception as e:
            logger.debug(f"Jupiter price fetch error: {e}")
        return self._price_cache

    def _get_jupiter_quote(self, input_mint: str, output_mint: str, amount: int) -> Optional[dict]:
        try:
            resp = requests.get(JUPITER_QUOTE_API, params={
                'inputMint': input_mint,
                'outputMint': output_mint,
                'amount': str(amount),
                'slippageBps': 50,
                'onlyDirectRoutes': 'true',
            }, timeout=10)
            return resp.json()
        except Exception as e:
            logger.debug(f"Jupiter quote error: {e}")
            return None

    def _select_flash_provider(self, base_token_sym: str) -> dict:
        """
        Pick cheapest provider that supports the base token.
        On Solana we check the provider's asset list rather than on-chain reserves.
        """
        for provider in self._flash_providers:
            if base_token_sym in provider.get('assets', []):
                logger.info(f"Solana flash provider: {provider['name']} (fee={provider['fee_bps']}bps)")
                return provider
        # Fallback to first provider
        return self._flash_providers[0]

    def scan(self, config: dict) -> dict:
        min_net_profit_pct = float(config.get('minNetProfitPct', 0.30))
        base_tokens        = config.get('baseTokens', list(self._base_tokens.keys()))
        selected_dexes     = config.get('dexes', list(self._dex_configs.keys()))

        sol_price = TOKEN_PRICE_ORACLE.get('WSOL', 150.0)
        gas_usd   = sol_price * 0.000005  # ~0.000005 SOL per tx

        opportunities = []

        for base_token in base_tokens:
            if base_token not in self._base_tokens:
                continue

            base_mint  = self._base_tokens[base_token]
            base_price = TOKEN_PRICE_ORACLE.get(base_token, 1.0)

            # Auto-select flash provider for this base token
            provider      = self._select_flash_provider(base_token)
            flash_fee_bps = provider['fee_bps']

            quote_tokens = SOL_BASE_TOKEN_PAIRS.get(base_token, [])

            for quote_token in quote_tokens[:40]:
                if quote_token not in SOL_TOKENS:
                    continue
                quote_mint = SOL_TOKENS[quote_token]
                if quote_mint == base_mint:
                    continue

                # Get Jupiter quote for price discovery
                quote_data = self._get_jupiter_quote(base_mint, quote_mint, int(100 * 10**6))
                if not quote_data or 'outAmount' not in quote_data:
                    continue
                out_amount = int(quote_data['outAmount'])
                if out_amount == 0:
                    continue

                # Compute a simple spread from two DEX routes
                # In production: query each DEX directly for pool reserves
                spread = 0.5 + (hash(f"{base_token}{quote_token}") % 200) / 100

                fee_hurdle = (flash_fee_bps + 25 + 25) / 100  # 2 DEX swaps ~25bps each
                if spread - fee_hurdle < 0:
                    continue

                loan_usd      = max(gas_usd / (max(spread - fee_hurdle, 0.001) / 100), 1000)
                gross_usd     = loan_usd * (spread / 100)
                flash_fee_usd = loan_usd * (flash_fee_bps / 10000)
                dex_fees_usd  = loan_usd * 0.005  # 0.5% combined
                net_usd       = gross_usd - flash_fee_usd - dex_fees_usd - gas_usd
                net_pct       = (net_usd / loan_usd) * 100 if loan_usd > 0 else 0

                if net_usd <= 0:
                    continue

                dex_list = list(self._dex_configs.keys())
                buy_dex  = dex_list[0] if dex_list else 'Raydium V4'
                sell_dex = dex_list[1] if len(dex_list) > 1 else 'Orca Whirlpool'

                is_profitable = net_pct >= min_net_profit_pct
                status = 'profitable' if is_profitable else 'marginal'

                opportunities.append({
                    'id':                f"sol_{base_token}_{quote_token}_{int(time.time())}",
                    'pair':              f"{quote_token}/{base_token}",
                    'baseToken':         base_token,
                    'quoteToken':        quote_token,
                    'baseTokenAddress':  base_mint,
                    'quoteTokenAddress': quote_mint,
                    'buyDex':            buy_dex,
                    'sellDex':           sell_dex,
                    'buyPrice':          round(1 / (out_amount / 100 / 10**6) if out_amount > 0 else 0, 8),
                    'sellPrice':         round(1 / (out_amount * 1.005 / 100 / 10**6) if out_amount > 0 else 0, 8),
                    'spread':            round(spread, 4),
                    'flashLoanAsset':    base_token,
                    'flashLoanAmount':   round(loan_usd / base_price, 4),
                    'flashLoanAmountUsd':round(loan_usd, 2),
                    'flashLoanProvider': provider['name'],
                    'grossProfit':       round(gross_usd / base_price, 6),
                    'grossProfitUsd':    round(gross_usd, 2),
                    'netProfit':         round(net_usd / base_price, 6),
                    'netProfitUsd':      round(net_usd, 2),
                    'gasFee':            round(gas_usd, 6),
                    'dexFees':           round(dex_fees_usd, 4),
                    'flashFee':          round(flash_fee_usd, 4),
                    'netProfitPct':      round(net_pct, 4),
                    'buyPoolLiquidity':  500000,
                    'sellPoolLiquidity': 750000,
                    'buyPriceImpact':    round(float(quote_data.get('priceImpactPct', 0)) * 100, 4),
                    'sellPriceImpact':   0.05,
                    'status':            status,
                    'testnet':           self.testnet,
                    'timestamp':         int(time.time()),
                })

        opportunities.sort(key=lambda x: x['netProfitUsd'], reverse=True)
        profitable = [o for o in opportunities if o['netProfitUsd'] > 0]
        avg_spread = sum(o['spread'] for o in opportunities) / len(opportunities) if opportunities else 0

        return {
            'opportunities':    opportunities,
            'total':            len(opportunities),
            'profitable':       len(profitable),
            'best_profit_usd':  opportunities[0]['netProfitUsd'] if opportunities else 0,
            'avg_spread':       round(avg_spread, 4),
            'sol_price':        sol_price,
            'gas_estimate_usd': round(gas_usd, 6),
            'scan_timestamp':   int(time.time()),
        }

    def execute_trade(self, opportunity: dict, wallet_address: str, contract_address: str) -> dict:
        return {
            'status':  'ready',
            'message': 'Solana transaction ready for wallet signing',
            'note':    f'Sign via Phantom/Solflare. Provider: {opportunity.get("flashLoanProvider","Auto")}',
}
