"""
DEX Arbitrage Scanner - Backend API
Flask server that scans DEXes for cross-exchange arbitrage opportunities
and manages flash loan execution.
"""

import os
import json
import time
import logging
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from scanner.bsc_scanner import BSCScanner
from scanner.solana_scanner import SolanaScanner

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

# Initialize scanners
bsc_scanner = BSCScanner()
sol_scanner = SolanaScanner()

# In-memory trade history (use Redis/DB in production)
trade_history = []


@app.route('/')
def index():
    return send_from_directory('../frontend', 'index.html')


@app.route('/api/scan', methods=['POST'])
def scan():
    """Scan DEXes for arbitrage opportunities."""
    try:
        data = request.json or {}
        network = data.get('network', 'bsc')
        config = data.get('config', {})

        start_time = time.time()
        logger.info(f"Starting {network} scan with config: {config}")

        if network == 'bsc':
            results = bsc_scanner.scan(config)
        else:
            results = sol_scanner.scan(config)

        elapsed = round(time.time() - start_time, 2)
        results['scan_time'] = elapsed
        logger.info(f"Scan completed in {elapsed}s — {results.get('total', 0)} opportunities found")
        return jsonify(results)

    except Exception as e:
        logger.error(f"Scan error: {e}", exc_info=True)
        return jsonify({'error': str(e), 'opportunities': [], 'total': 0}), 500


@app.route('/api/execute', methods=['POST'])
def execute():
    """
    Execute a flash loan arbitrage trade.
    In production this calls the deployed smart contract via Web3.
    """
    try:
        data = request.json or {}
        network = data.get('network', 'bsc')
        opportunity = data.get('opportunity', {})
        wallet = data.get('wallet', '')
        contract_address = data.get('contractAddress', '')

        if not contract_address:
            return jsonify({'error': 'Smart contract address not configured'}), 400

        if network == 'bsc':
            result = bsc_scanner.execute_trade(opportunity, wallet, contract_address)
        else:
            result = sol_scanner.execute_trade(opportunity, wallet, contract_address)

        # Log to history
        history_entry = {
            'id': len(trade_history) + 1,
            'timestamp': int(time.time()),
            'network': network,
            'pair': opportunity.get('pair', ''),
            'buyDex': opportunity.get('buyDex', ''),
            'sellDex': opportunity.get('sellDex', ''),
            'buyPrice': opportunity.get('buyPrice', 0),
            'sellPrice': opportunity.get('sellPrice', 0),
            'flashLoanAmount': opportunity.get('flashLoanAmount', 0),
            'flashLoanAsset': opportunity.get('flashLoanAsset', ''),
            'grossProfit': opportunity.get('grossProfit', 0),
            'netProfit': opportunity.get('netProfit', 0),
            'netProfitUsd': opportunity.get('netProfitUsd', 0),
            'gasFee': opportunity.get('gasFee', 0),
            'dexFees': opportunity.get('dexFees', 0),
            'spread': opportunity.get('spread', 0),
            'txHash': result.get('txHash', ''),
            'status': result.get('status', 'pending'),
            'blockNumber': result.get('blockNumber', 0),
        }
        trade_history.insert(0, history_entry)
        if len(trade_history) > 500:
            trade_history.pop()

        return jsonify(result)

    except Exception as e:
        logger.error(f"Execute error: {e}", exc_info=True)
        return jsonify({'error': str(e), 'status': 'failed'}), 500


@app.route('/api/history', methods=['GET'])
def get_history():
    """Return trade history."""
    limit = int(request.args.get('limit', 100))
    return jsonify({'history': trade_history[:limit]})


@app.route('/api/history', methods=['DELETE'])
def clear_history():
    """Clear trade history."""
    trade_history.clear()
    return jsonify({'message': 'History cleared'})


@app.route('/api/status', methods=['GET'])
def status():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'bsc_rpc': bool(os.environ.get('BSC_RPC_URL')),
        'solana_rpc': bool(os.environ.get('SOLANA_RPC_URL')),
        'contract_bsc': os.environ.get('BSC_CONTRACT_ADDRESS', ''),
        'contract_solana': os.environ.get('SOLANA_CONTRACT_ADDRESS', ''),
    })


@app.route('/api/config', methods=['GET'])
def get_config():
    """Return environment-driven config to frontend."""
    return jsonify({
        'bscContractAddress': os.environ.get('BSC_CONTRACT_ADDRESS', ''),
        'solanaContractAddress': os.environ.get('SOLANA_CONTRACT_ADDRESS', ''),
        'bscRpcConfigured': bool(os.environ.get('BSC_RPC_URL')),
        'solanaRpcConfigured': bool(os.environ.get('SOLANA_RPC_URL')),
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV', 'production') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
