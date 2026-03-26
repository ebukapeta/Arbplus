// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title ArbPulse Flash Loan Arbitrage — BSC
 * @notice Executes atomic cross-DEX arbitrage using Aave V3 flash loans on BNB Chain.
 *         Flow: flash borrow base token → buy quote on DEX A → sell quote on DEX B → repay loan → keep profit
 * @dev    Deploy this contract, fund it with a small BNB for gas, then set its address in the UI.
 */

interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

interface IUniswapV2Router {
    function swapExactTokensForTokens(
        uint256 amountIn,
        uint256 amountOutMin,
        address[] calldata path,
        address to,
        uint256 deadline
    ) external returns (uint256[] memory amounts);

    function getAmountsOut(uint256 amountIn, address[] calldata path)
        external view returns (uint256[] memory amounts);
}

interface IPool {
    function flashLoanSimple(
        address receiverAddress,
        address asset,
        uint256 amount,
        bytes calldata params,
        uint16 referralCode
    ) external;
}

interface IFlashLoanSimpleReceiver {
    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,
        address initiator,
        bytes calldata params
    ) external returns (bool);
}

contract ArbPulseFlashArb is IFlashLoanSimpleReceiver {

    // ─── State ────────────────────────────────────────────────────────────────
    address public owner;
    address public constant AAVE_V3_POOL = 0x6807dc923806fE8Fd134338EABCA509979a7e0cB; // BSC Mainnet

    // Safety: minimum net profit required (in wei of the flash loan asset)
    uint256 public minNetProfitBps = 10; // 0.10% minimum

    bool private _locked;

    // ─── Events ───────────────────────────────────────────────────────────────
    event ArbitrageExecuted(
        address indexed token,
        uint256 loanAmount,
        uint256 grossProfit,
        uint256 netProfit,
        address buyDex,
        address sellDex
    );
    event ProfitWithdrawn(address token, uint256 amount, address to);
    event EmergencyWithdraw(address token, uint256 amount);

    // ─── Modifiers ────────────────────────────────────────────────────────────
    modifier onlyOwner() {
        require(msg.sender == owner, "ArbPulse: not owner");
        _;
    }

    modifier nonReentrant() {
        require(!_locked, "ArbPulse: reentrant call");
        _locked = true;
        _;
        _locked = false;
    }

    // ─── Constructor ──────────────────────────────────────────────────────────
    constructor() {
        owner = msg.sender;
    }

    receive() external payable {}

    // ─── Main Entry ───────────────────────────────────────────────────────────

    /**
     * @notice Initiate flash loan arbitrage.
     * @param _flashLoanAsset     Token to borrow (WBNB, USDT, BTCB, USDC).
     * @param _flashLoanAmount    Amount to borrow (in token decimals).
     * @param _buyDex             Router address of the cheaper DEX (buy here).
     * @param _sellDex            Router address of the more expensive DEX (sell here).
     * @param _buyPath            Swap path: [flashLoanAsset, quoteToken].
     * @param _sellPath           Swap path: [quoteToken, flashLoanAsset].
     * @param _minProfit          Minimum acceptable net profit (reverts if not met).
     * @param _deadline           Unix timestamp deadline for swaps.
     */
    function executeArbitrage(
        address _flashLoanAsset,
        uint256 _flashLoanAmount,
        address _buyDex,
        address _sellDex,
        address[] calldata _buyPath,
        address[] calldata _sellPath,
        uint256 _minProfit,
        uint256 _deadline
    ) external onlyOwner nonReentrant {
        require(_buyPath.length >= 2, "ArbPulse: invalid buy path");
        require(_sellPath.length >= 2, "ArbPulse: invalid sell path");
        require(_flashLoanAmount > 0, "ArbPulse: zero loan amount");

        // Encode params to pass through flash loan callback
        bytes memory params = abi.encode(
            _buyDex, _sellDex, _buyPath, _sellPath, _minProfit, _deadline
        );

        // Request flash loan from Aave V3
        IPool(AAVE_V3_POOL).flashLoanSimple(
            address(this),
            _flashLoanAsset,
            _flashLoanAmount,
            params,
            0
        );
    }

    // ─── Aave Flash Loan Callback ─────────────────────────────────────────────

    /**
     * @notice Called by Aave pool after flash loan is disbursed.
     *         Must repay amount + premium by end of function or the tx reverts.
     */
    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,
        address initiator,
        bytes calldata params
    ) external override returns (bool) {
        require(msg.sender == AAVE_V3_POOL, "ArbPulse: caller not Aave pool");
        require(initiator == address(this), "ArbPulse: invalid initiator");

        (
            address buyDex,
            address sellDex,
            address[] memory buyPath,
            address[] memory sellPath,
            uint256 minProfit,
            uint256 deadline
        ) = abi.decode(params, (address, address, address[], address[], uint256, uint256));

        uint256 totalDebt = amount + premium;

        // ── Step 1: Approve buy DEX to spend flash loan asset ──
        IERC20(asset).approve(buyDex, amount);

        // ── Step 2: Buy quote token on cheaper DEX ──
        uint256[] memory buyAmounts = IUniswapV2Router(buyDex).swapExactTokensForTokens(
            amount,
            0,           // accept any amount (slippage checked by minProfit at end)
            buyPath,
            address(this),
            deadline
        );
        uint256 quoteReceived = buyAmounts[buyAmounts.length - 1];

        // ── Step 3: Approve sell DEX to spend quote token ──
        address quoteToken = buyPath[buyPath.length - 1];
        IERC20(quoteToken).approve(sellDex, quoteReceived);

        // ── Step 4: Sell quote token on more expensive DEX ──
        uint256[] memory sellAmounts = IUniswapV2Router(sellDex).swapExactTokensForTokens(
            quoteReceived,
            totalDebt,   // must receive at least enough to repay
            sellPath,
            address(this),
            deadline
        );
        uint256 baseReceived = sellAmounts[sellAmounts.length - 1];

        // ── Step 5: Verify profit ──
        require(baseReceived > totalDebt, "ArbPulse: no profit after repayment");
        uint256 netProfit = baseReceived - totalDebt;
        require(netProfit >= minProfit, "ArbPulse: profit below minimum");

        // ── Step 6: Repay Aave (approve pool to pull totalDebt) ──
        IERC20(asset).approve(AAVE_V3_POOL, totalDebt);

        uint256 grossProfit = baseReceived - amount;
        emit ArbitrageExecuted(asset, amount, grossProfit, netProfit, buyDex, sellDex);

        return true;
    }

    // ─── Owner Utilities ──────────────────────────────────────────────────────

    /**
     * @notice Withdraw accumulated profit tokens to owner wallet.
     */
    function withdrawToken(address token, uint256 amount) external onlyOwner {
        uint256 bal = IERC20(token).balanceOf(address(this));
        uint256 withdrawAmount = amount == 0 ? bal : amount;
        require(withdrawAmount <= bal, "ArbPulse: insufficient balance");
        IERC20(token).transfer(owner, withdrawAmount);
        emit ProfitWithdrawn(token, withdrawAmount, owner);
    }

    /**
     * @notice Withdraw BNB from contract.
     */
    function withdrawBNB(uint256 amount) external onlyOwner {
        uint256 bal = address(this).balance;
        uint256 withdrawAmount = amount == 0 ? bal : amount;
        require(withdrawAmount <= bal, "ArbPulse: insufficient BNB");
        payable(owner).transfer(withdrawAmount);
    }

    /**
     * @notice Emergency: withdraw any token (in case funds get stuck).
     */
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

    /**
     * @notice Update minimum profit requirement.
     */
    function setMinNetProfitBps(uint256 bps) external onlyOwner {
        minNetProfitBps = bps;
    }

    /**
     * @notice Transfer ownership.
     */
    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "ArbPulse: zero address");
        owner = newOwner;
    }

    /**
     * @notice Get contract balance for a given token.
     */
    function getBalance(address token) external view returns (uint256) {
        return IERC20(token).balanceOf(address(this));
    }
}
