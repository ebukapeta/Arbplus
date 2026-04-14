// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title  ArbPulse Flash Loan Arbitrage — EVM (ETH / Arbitrum / Base)
 * @notice Supports Aave V3 and Balancer V2 flash loans.
 *
 * ─── COMPILE SETTINGS (Remix) ────────────────────────────────────────────────
 *   Compiler:      0.8.20
 *   Optimisation:  ON (runs: 200)
 *   IMPORTANT:     Open "Advanced Configurations" and tick the
 *                  "Enable viaIR" checkbox — this is required to
 *                  avoid the "Stack too deep" compiler error.
 * ─────────────────────────────────────────────────────────────────────────────
 *
 * Constructor arguments by network:
 *
 *   Ethereum Mainnet
 *     _aavePool      0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2
 *     _balancerVault 0xBA12222222228d8Ba445958a75a0704d566BF2C8
 *
 *   Arbitrum One
 *     _aavePool      0x794a61358D6845594F94dc1DB02A252b5b4814aD
 *     _balancerVault 0xBA12222222228d8Ba445958a75a0704d566BF2C8
 *
 *   Base Mainnet
 *     _aavePool      0xA238Dd80C259a72e81d7e4664a9801593F98d1c5
 *     _balancerVault 0xBA12222222228d8Ba445958a75a0704d566BF2C8
 *
 *   Sepolia (ETH testnet)
 *     _aavePool      0x6Ae43d3271ff6888e7Fc43Fd7321a503ff738951
 *     _balancerVault 0x0000000000000000000000000000000000000000
 *
 *   Arb Sepolia
 *     _aavePool      0xBfC91D59fdAA134A4ED45f7B584cAf96D7792Eff
 *     _balancerVault 0x0000000000000000000000000000000000000000
 *
 *   Base Sepolia
 *     _aavePool      0x6Ae43d3271ff6888e7Fc43Fd7321a503ff738951
 *     _balancerVault 0x0000000000000000000000000000000000000000
 */

interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

interface IUniswapV2Router {
    function swapExactTokensForTokens(
        uint256          amountIn,
        uint256          amountOutMin,
        address[] calldata path,
        address          to,
        uint256          deadline
    ) external returns (uint256[] memory amounts);
}

interface IAavePool {
    function flashLoanSimple(
        address receiverAddress,
        address asset,
        uint256 amount,
        bytes calldata params,
        uint16 referralCode
    ) external;
}

interface IAaveFlashReceiver {
    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,
        address initiator,
        bytes calldata params
    ) external returns (bool);
}

interface IBalancerVault {
    function flashLoan(
        address          recipient,
        address[] calldata tokens,
        uint256[] calldata amounts,
        bytes calldata   userData
    ) external;
}

interface IBalancerFlashReceiver {
    function receiveFlashLoan(
        address[] calldata tokens,
        uint256[] calldata amounts,
        uint256[] calldata feeAmounts,
        bytes calldata   userData
    ) external;
}

contract ArbPulseFlashArbEVM is IAaveFlashReceiver, IBalancerFlashReceiver {

    // ─── Struct: packs all arb params — this is the key fix for stack-too-deep ─
    struct ArbParams {
        address   buyDex;
        address   sellDex;
        address[] buyPath;
        address[] sellPath;
        uint256   minProfit;
        uint256   deadline;
        uint8     provider;   // 0 = Aave V3  |  1 = Balancer V2
    }

    // ─── State ────────────────────────────────────────────────────────────────
    address public         owner;
    address public immutable aavePool;
    address public immutable balancerVault;
    uint256 public         minNetProfitBps = 5;   // 0.05 %
    bool    private        _locked;

    // ─── Events ───────────────────────────────────────────────────────────────
    event ArbitrageExecuted(
        address indexed token,
        uint256         loanAmount,
        uint256         netProfit,
        address         buyDex,
        address         sellDex,
        string          provider
    );
    event EmergencyWithdraw(address token, uint256 amount);
    event ProfitWithdrawn(address token, uint256 amount);

    // ─── Modifiers ────────────────────────────────────────────────────────────
    modifier onlyOwner() {
        require(msg.sender == owner, "ArbPulse: not owner");
        _;
    }

    modifier nonReentrant() {
        require(!_locked, "ArbPulse: reentrant");
        _locked = true;
        _;
        _locked = false;
    }

    // ─── Constructor ──────────────────────────────────────────────────────────
    constructor(address _aavePool, address _balancerVault) {
        owner         = msg.sender;
        aavePool      = _aavePool;
        balancerVault = _balancerVault;
    }

    receive() external payable {}

    // ─── Main entry point ─────────────────────────────────────────────────────

    /**
     * @param _flashLoanAsset   Token to borrow (WETH / USDC / USDT / etc.)
     * @param _flashLoanAmount  Amount in token's native decimals
     * @param _buyDex           UniswapV2-compatible router — the cheaper DEX
     * @param _sellDex          UniswapV2-compatible router — the more expensive DEX
     * @param _buyPath          [flashLoanAsset, quoteToken]
     * @param _sellPath         [quoteToken, flashLoanAsset]
     * @param _minProfit        Minimum acceptable net profit. TX reverts if not met.
     * @param _deadline         Unix timestamp — swaps revert after this time
     * @param _provider         0 = Aave V3,  1 = Balancer V2
     */
    function executeArbitrage(
        address            _flashLoanAsset,
        uint256            _flashLoanAmount,
        address            _buyDex,
        address            _sellDex,
        address[] calldata _buyPath,
        address[] calldata _sellPath,
        uint256            _minProfit,
        uint256            _deadline,
        uint8              _provider
    ) external onlyOwner nonReentrant {
        require(_buyPath.length  >= 2, "ArbPulse: bad buy path");
        require(_sellPath.length >= 2, "ArbPulse: bad sell path");
        require(_flashLoanAmount  > 0, "ArbPulse: zero amount");

        bytes memory encoded = abi.encode(ArbParams({
            buyDex:    _buyDex,
            sellDex:   _sellDex,
            buyPath:   _buyPath,
            sellPath:  _sellPath,
            minProfit: _minProfit,
            deadline:  _deadline,
            provider:  _provider
        }));

        if (_provider == 1 && balancerVault != address(0)) {
            address[] memory tokens  = new address[](1);
            uint256[] memory amounts = new uint256[](1);
            tokens[0]  = _flashLoanAsset;
            amounts[0] = _flashLoanAmount;
            IBalancerVault(balancerVault).flashLoan(
                address(this), tokens, amounts, encoded
            );
        } else {
            // Default: Aave V3
            IAavePool(aavePool).flashLoanSimple(
                address(this), _flashLoanAsset, _flashLoanAmount, encoded, 0
            );
        }
    }

    // ─── Aave V3 callback ─────────────────────────────────────────────────────

    function executeOperation(
        address        asset,
        uint256        amount,
        uint256        premium,
        address        initiator,
        bytes calldata params
    ) external override returns (bool) {
        require(msg.sender == aavePool,      "ArbPulse: not Aave pool");
        require(initiator  == address(this), "ArbPulse: bad initiator");

        _performSwaps(asset, amount, amount + premium, params, "Aave V3");

        // Approve Aave pool to pull debt repayment
        IERC20(asset).approve(aavePool, amount + premium);
        return true;
    }

    // ─── Balancer V2 callback ─────────────────────────────────────────────────

    function receiveFlashLoan(
        address[] calldata tokens,
        uint256[] calldata amounts,
        uint256[] calldata feeAmounts,
        bytes calldata     userData
    ) external override {
        require(msg.sender == balancerVault, "ArbPulse: not Balancer");
        require(tokens.length == 1,          "ArbPulse: single token only");

        uint256 totalDebt = amounts[0] + feeAmounts[0];
        _performSwaps(tokens[0], amounts[0], totalDebt, userData, "Balancer V2");

        // Balancer requires the tokens to be transferred back directly
        IERC20(tokens[0]).transfer(balancerVault, totalDebt);
    }

    // ─── Core swap logic (internal) ───────────────────────────────────────────

    function _performSwaps(
        address      asset,
        uint256      borrowed,
        uint256      totalDebt,
        bytes memory encoded,
        string memory providerName
    ) internal {
        ArbParams memory p = abi.decode(encoded, (ArbParams));

        // Buy: flash loan asset → quote token on cheaper DEX
        IERC20(asset).approve(p.buyDex, borrowed);
        uint256[] memory buyAmounts = IUniswapV2Router(p.buyDex)
            .swapExactTokensForTokens(borrowed, 0, p.buyPath, address(this), p.deadline);

        // Sell: quote token → flash loan asset on more expensive DEX
        address quoteToken    = p.buyPath[p.buyPath.length - 1];
        uint256 quoteReceived = buyAmounts[buyAmounts.length - 1];

        IERC20(quoteToken).approve(p.sellDex, quoteReceived);
        uint256[] memory sellAmounts = IUniswapV2Router(p.sellDex)
            .swapExactTokensForTokens(quoteReceived, totalDebt, p.sellPath, address(this), p.deadline);

        uint256 baseBack = sellAmounts[sellAmounts.length - 1];

        // Verify profit
        require(baseBack > totalDebt,  "ArbPulse: no profit after repayment");
        uint256 netProfit = baseBack - totalDebt;
        require(netProfit >= p.minProfit, "ArbPulse: profit below minimum");

        emit ArbitrageExecuted(
            asset, borrowed, netProfit, p.buyDex, p.sellDex, providerName
        );
    }

    // ─── Owner utilities ──────────────────────────────────────────────────────

    /// @notice Withdraw profit tokens to owner wallet.
    function withdrawToken(address token, uint256 amount) external onlyOwner {
        uint256 bal = IERC20(token).balanceOf(address(this));
        uint256 out = (amount == 0) ? bal : amount;
        require(out <= bal, "ArbPulse: insufficient balance");
        IERC20(token).transfer(owner, out);
        emit ProfitWithdrawn(token, out);
    }

    /// @notice Withdraw native ETH from the contract.
    function withdrawETH(uint256 amount) external onlyOwner {
        uint256 bal = address(this).balance;
        uint256 out = (amount == 0) ? bal : amount;
        require(out <= bal, "ArbPulse: insufficient ETH");
        payable(owner).transfer(out);
    }

    /// @notice Emergency: pull all funds to owner.
    function emergencyWithdraw(address token) external onlyOwner {
        uint256 bal = IERC20(token).balanceOf(address(this));
        if (bal > 0) {
            IERC20(token).transfer(owner, bal);
            emit EmergencyWithdraw(token, bal);
        }
        if (address(this).balance > 0) {
            payable(owner).transfer(address(this).balance);
        }
    }

    function setMinNetProfitBps(uint256 bps)  external onlyOwner { minNetProfitBps = bps; }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "ArbPulse: zero address");
        owner = newOwner;
    }

    function getBalance(address token) external view returns (uint256) {
        return IERC20(token).balanceOf(address(this));
    }
}
