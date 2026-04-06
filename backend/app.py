"""
ArbPulse — Backend API
Flask server supporting BSC, Ethereum, Arbitrum, Base, Solana
on both mainnet and testnet.
"""

import os, json, time, logging
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from scanner.bsc_scanner      import BSCScanner
from scanner.eth_scanner      import ETHScanner
from scanner.arbitrum_scanner import ArbitrumScanner
from scanner.base_scanner     import BaseScanner
from scanner.solana_scanner   import SolanaScanner

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

# ── Scanner registry  (mainnet + testnet) ──────────────────────────────────
_scanners = {
    ('bsc',    False): BSCScanner(testnet=False),
    ('bsc',    True):  BSCScanner(testnet=True),
    ('eth',    False): ETHScanner(testnet=False),
    ('eth',    True):  ETHScanner(testnet=True),
    ('arb',    False): ArbitrumScanner(testnet=False),
    ('arb',    True):  ArbitrumScanner(testnet=True),
    ('base',   False): BaseScanner(testnet=False),
    ('base',   True):  BaseScanner(testnet=True),
    ('solana', False): SolanaScanner(testnet=False),
    ('solana', True):  SolanaScanner(testnet=True),
}

trade_history = []


def _get_scanner(network: str, testnet: bool):
    key = (network, testnet)
    if key not in _scanners:
        logger.warning(f"No scanner for {key}, falling back to bsc mainnet")
        return _scanners[('bsc', False)]
    return _scanners[key]


@app.route('/')
def index():
    return send_from_directory('../frontend', 'index.html')


@app.route('/api/scan', methods=['POST'])
def scan():
    try:
        data    = request.json or {}
        network = data.get('network', 'bsc')
        testnet = bool(data.get('testnet', False))
        config  = data.get('config', {})

        start = time.time()
        logger.info(f"Scan: network={network} testnet={testnet} config={config}")

        scanner = _get_scanner(network, testnet)
        results = scanner.scan(config)
        results['scan_time'] = round(time.time() - start, 2)
        results['testnet']   = testnet
        logger.info(f"Scan done in {results['scan_time']}s — {results.get('total',0)} opps")
        return jsonify(results)

    except Exception as e:
        logger.error(f"Scan error: {e}", exc_info=True)
        return jsonify({'error': str(e), 'opportunities': [], 'total': 0}), 500


@app.route('/api/execute', methods=['POST'])
def execute():
    try:
        data            = request.json or {}
        network         = data.get('network', 'bsc')
        testnet         = bool(data.get('testnet', False))
        opportunity     = data.get('opportunity', {})
        wallet          = data.get('wallet', '')
        contract_address= data.get('contractAddress', '')

        if not contract_address:
            return jsonify({'error': 'Smart contract address not configured'}), 400

        scanner = _get_scanner(network, testnet)
        result  = scanner.execute_trade(opportunity, wallet, contract_address)

        entry = {
            'id':               len(trade_history) + 1,
            'timestamp':        int(time.time()),
            'network':          network,
            'testnet':          testnet,
            'pair':             opportunity.get('pair', ''),
            'buyDex':           opportunity.get('buyDex', ''),
            'sellDex':          opportunity.get('sellDex', ''),
            'buyPrice':         opportunity.get('buyPrice', 0),
            'sellPrice':        opportunity.get('sellPrice', 0),
            'flashLoanAmount':  opportunity.get('flashLoanAmount', 0),
            'flashLoanAsset':   opportunity.get('flashLoanAsset', ''),
            'flashLoanProvider':opportunity.get('flashLoanProvider', ''),
            'grossProfitUsd':   opportunity.get('grossProfitUsd', 0),
            'netProfitUsd':     opportunity.get('netProfitUsd', 0),
            'gasFee':           opportunity.get('gasFee', 0),
            'dexFees':          opportunity.get('dexFees', 0),
            'spread':           opportunity.get('spread', 0),
            'txHash':           result.get('txHash', ''),
            'status':           result.get('status', 'pending'),
        }
        trade_history.insert(0, entry)
        if len(trade_history) > 500:
            trade_history.pop()

        return jsonify(result)

    except Exception as e:
        logger.error(f"Execute error: {e}", exc_info=True)
        return jsonify({'error': str(e), 'status': 'failed'}), 500


@app.route('/api/history', methods=['GET'])
def get_history():
    limit = int(request.args.get('limit', 100))
    return jsonify({'history': trade_history[:limit]})


@app.route('/api/history', methods=['DELETE'])
def clear_history():
    trade_history.clear()
    return jsonify({'message': 'History cleared'})


@app.route('/api/status', methods=['GET'])
def status():
    return jsonify({
        'status': 'ok',
        'networks': ['bsc', 'eth', 'arb', 'base', 'solana'],
        'bsc_rpc':    bool(os.environ.get('BSC_RPC_URL')),
        'eth_rpc':    bool(os.environ.get('ETH_RPC_URL')),
        'arb_rpc':    bool(os.environ.get('ARB_RPC_URL')),
        'base_rpc':   bool(os.environ.get('BASE_RPC_URL')),
        'solana_rpc': bool(os.environ.get('SOLANA_RPC_URL')),
    })


@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify({
        'bscContractAddress':     os.environ.get('BSC_CONTRACT_ADDRESS',     ''),
        'ethContractAddress':     os.environ.get('ETH_CONTRACT_ADDRESS',     ''),
        'arbContractAddress':     os.environ.get('ARB_CONTRACT_ADDRESS',     ''),
        'baseContractAddress':    os.environ.get('BASE_CONTRACT_ADDRESS',    ''),
        'solanaContractAddress':  os.environ.get('SOLANA_CONTRACT_ADDRESS',  ''),
        'bscRpcConfigured':       bool(os.environ.get('BSC_RPC_URL')),
        'ethRpcConfigured':       bool(os.environ.get('ETH_RPC_URL')),
        'arbRpcConfigured':       bool(os.environ.get('ARB_RPC_URL')),
        'baseRpcConfigured':      bool(os.environ.get('BASE_RPC_URL')),
        'solanaRpcConfigured':    bool(os.environ.get('SOLANA_RPC_URL')),
    })


if __name__ == '__main__':
    port  = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV', 'production') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
