"""
Solana DEX Scanner — DexScreener price-based + Jupiter quotes
8 base tokens, mainnet + devnet
"""
import os, time, logging, requests
from .dexscreener_scanner import DexScreenerScanner, fetch_token_pairs, fetch_search_pairs, parallel_fetch

logger = logging.getLogger(__name__)

JUPITER_PRICE_API = 'https://price.jup.ag/v6/price'

SOL_MAINNET_RPC = ['https://api.mainnet-beta.solana.com']
SOL_DEVNET_RPC  = ['https://api.devnet.solana.com']


class SolanaScanner(DexScreenerScanner):
    DEXSCREENER_CHAIN = 'solana'
    NETWORK_NAME      = 'Solana'

    BASE_TOKENS_MAINNET = {
        'WSOL':    'So11111111111111111111111111111111111111112',
        'USDC':    'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
        'USDT':    'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB',
        'MSOL':    'mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So',
        'BONK':    'DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263',
        'JTO':     'jtojtomepa8bJkZSqEXSJm5Z4e6PdBXuBvC5jNYWqDi',
        'JITOSOL': 'J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn',
        'BSOL':    'bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1',
        'RAY':     '4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R',
        'JUP':     'JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN',
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

    PRICE_FALLBACKS = {
        'WSOL':150.0,'USDC':1.0,'USDT':1.0,'MSOL':160.0,
        'BONK':0.00003,'JTO':3.5,'JITOSOL':155.0,'BSOL':158.0,
        'WIF':2.5,'JUP':0.8,'RAY':2.0,'ORCA':3.5,'BSOL':158.0,
    }

    DEX_ALIASES = {
        'orca':              'Orca Whirlpool',
        'orca-whirlpool':    'Orca Whirlpool',
        'raydium':           'Raydium V4',
        'raydium-clmm':      'Raydium CLMM',
        'raydium-cp':        'Raydium V4',
        'meteora':           'Meteora DLMM',
        'meteora-dlmm':      'Meteora DLMM',
        'lifinity':          'Lifinity V2',
        'lifinity-v2':       'Lifinity V2',
        'saber':             'Saber',
        'goosefx':           'GooseFX',
        'phoenix':           'Phoenix',
        'openbook':          'OpenBook',
        'jupiter':           'Jupiter',
        'aldrin':            'Aldrin',
        'crema':             'Crema',
        'invariant':         'Invariant',
        'mercurial':         'Mercurial',
        'serum':             'Serum',
        'step-finance':      'Step Finance',
        'cropper':           'Cropper',
        'sencha':            'Sencha',
        'penguin-finance':   'Penguin Finance',
        'saros':             'Saros',
    }

    FLASH_PROVIDERS_MAINNET = [
        {'name':'MarginFi', 'fee_bps':0,  'program_id':'MFv2hWf31Z9kbCa1snEPdcgp7gkVsWRU38fRBLj6fLA', 'assets':['WSOL','USDC','USDT','MSOL','JITOSOL','BSOL','JTO']},
        {'name':'Kamino',   'fee_bps':9,  'program_id':'KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD', 'assets':['WSOL','USDC','USDT','MSOL','JITOSOL','BSOL','JTO','BONK']},
        {'name':'Solend',   'fee_bps':30, 'program_id':'So1endDq2YkqhipRh3WViPa8hdiSpxWy6z3Z6tMCpAo', 'assets':['WSOL','USDC','USDT','MSOL','JTO','WIF','BONK']},
    ]
    FLASH_PROVIDERS_TESTNET = [
        {'name':'Solend Devnet','fee_bps':30,'program_id':'ALend7Ketfx5bxh6ghsCDXAoDrhvEmsXT3cynB6aPLgx','assets':['WSOL','USDC']},
    ]

    GAS_UNITS        = 220_000
    GAS_GWEI_MAINNET = 0.0
    GAS_GWEI_TESTNET = 0.0
    NATIVE_PRICE_USD = 150.0

    def _gas_usd(self) -> float:
        # Solana: ~$0.00075 per transaction
        return self.NATIVE_PRICE_USD * 0.000005

    def execute_trade(self, opportunity: dict, wallet_address: str, contract_address: str) -> dict:
        return {
            'status':  'ready',
            'message': 'Solana transaction ready for wallet signing',
            'note':    f"Sign via Phantom/Solflare. Provider: {opportunity.get('flashLoanProvider','Auto')}",
        }
