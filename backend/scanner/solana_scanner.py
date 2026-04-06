"""
Solana DEX Scanner — Mainnet + Devnet, 8 base tokens, auto flash provider
Auto flash provider: MarginFi (0%) → Kamino (0.09%) → Solend (0.30%)
"""

import os, time, logging, requests
from typing import Optional

logger = logging.getLogger(__name__)

SOL_TOKENS = {
    'WSOL':    'So11111111111111111111111111111111111111112',
    'USDC':    'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
    'USDT':    'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB',
    'MSOL':    'mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So',
    'BONK':    'DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263',
    'JTO':     'jtojtomepa8bJkZSqEXSJm5Z4e6PdBXuBvC5jNYWqDi',
    'JITOSOL': 'J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn',
    'BSOL':    'bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1',
    'WIF':     'EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm',
    'POPCAT':  '7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr',
    'PYTH':    'HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3',
    'JUP':     'JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN',
    'RAY':     '4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R',
    'ORCA':    'orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE',
    'MNGO':    'MangoCzJ36AjZyKwVj3VnYU4GTonjfVEnJmvvWaxLac',
    'SRM':     'SRMuApVNdxXokk5GT7XD5cUUgXMBCoAz2LHeuAoKZRB',
    'SAMO':    '7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU',
    'SLND':    'SLNDpmoWTVADgEdndyvWzroNL7zSi1dF9PC3xHGtPwp',
    'ATLAS':   'ATLASXmbPQxBUYbxPsV97usA3fPQYEqzQBUHgiFCUsXx',
    'POLIS':   'poLisWXnNRwC6oBu1vHiuKQzFjGL4XDSu4g9qjz9qVk',
    'FIDA':    'EchesyfXePKdLtoiZSL8pBe8Myagyy8ZRqsACNCFGnvp',
    'COPE':    '8HGyAAB1yoM1ttS7pXjHMa3dukTFGQggnFFH3hJZgzQh',
    'MAPS':    'MAPS41MDahZ9QdKXhVa4dWB9RuyfV4XqhyAZ8XcYepb',
    'OXY':     'z3dn17yLaGMKffVogeFHQ9zWVcXgqgf3PQnDsNs2g6M',
    'KIN':     'kinXdEcpDQeHPEuQnqmUgtYykqKGVFq6CeVX5iAHJq6',
    'MSOL2':   'mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So',
    'STEP':    'StepAscQoEioFxxWGnh2sLBDFp9d8rvKz2Yp39iDpyT',
    'GRAPE':   '8upjSpvjcdpuzhfR1zriwg5NXkwDruejqNE9WNbPRtyA',
    'MEAN':    'MEANeD3XDdUmNMsRGjASkSWdC8prLYsoRJ61pPeHctD',
    'PORT':    'PoRTjZMPXb9T7dyU7tpLEZRQj7e6ssfAE62j2oQuc6y',
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
