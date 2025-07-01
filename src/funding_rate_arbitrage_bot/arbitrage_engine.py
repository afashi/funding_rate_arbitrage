import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple

import pandas as pd

# 假设这些模块已经存在并且可以导入
from .config_manager import AppConfig
from .data_fetcher import DataFetcher


@dataclass
class ArbitrageDecision:
    """
    封装一个完整的开仓决策，供 ExecutionEngine 使用。
    """
    symbol: str  # 交易对，例如 'BTC/USDT'
    direction: str  # 'SHORT' 或 'LONG'
    decision_reason: str  # 决策原因

    # 策略和风险参数
    leverage: float
    capital_to_use: float  # 本次交易计划使用的USDT数量

    # 市场数据
    estimated_funding_rate: float
    spot_ask_price: float  # 现货买一价
    spot_bid_price: float  # 现货卖一价
    swap_ask_price: float  # 合约买一价
    swap_bid_price: float  # 合约卖一价

    # 流动性分析结果
    avg_spot_price: float  # 预估的现货平均成交价
    avg_swap_price: float  # 预估的合约平均成交价
    spot_slippage: float  # 现货滑点
    swap_slippage: float  # 合约滑点

    # 成本和收益计算
    net_apr: float  # 最终净年化收益率
    trade_fee_cost: float
    slippage_cost: float

    # 现货赚币 (可选)
    spot_earning_rate: Optional[float] = None

    # 负费率借贷成本 (可选)
    borrow_interest_rate: Optional[float] = None


class ArbitrageEngine:
    """
    决策分析引擎。
    负责根据市场数据、配置参数和风险模型，分析并找出有利可图的套利机会。
    """

    def __init__(self, config: AppConfig, logger: logging.Logger, data_fetcher: DataFetcher):
        self.config = config
        self.logger = logger
        self.data_fetcher = data_fetcher

    async def find_opportunities(self) -> List[ArbitrageDecision]:
        """
        发现套利机会的主函数。

        Returns:
            一个包含所有有效开仓决策的列表。
        """
        self.logger.info("开始扫描市场寻找套利机会...")
        decisions = []

        # 1. 获取所有必要的数据
        funding_rates = await self.data_fetcher.fetch_funding_rates()
        if funding_rates.empty:
            self.logger.warning("未能获取到任何资金费率数据，跳过本轮扫描。")
            return []

        # 获取账户总余额，用于计算单笔交易金额
        total_balance = await self.data_fetcher.fetch_total_equity_usd()
        if total_balance == 0:
            self.logger.warning("账户总余额为0，无法进行交易。")
            return []

        capital_per_trade = total_balance * self.config.strategy.capital_per_trade_ratio

        # 2. 遍历所有资金费率，寻找机会
        for index, row in funding_rates.iterrows():
            symbol = row['symbol']
            funding_rate = row['rate']

            # 评估正费率机会 (做空合约，买入现货)
            if funding_rate > 0:
                decision = await self._evaluate_opportunity(
                    symbol, funding_rate, 'SHORT', capital_per_trade
                )
                if decision:
                    decisions.append(decision)

            # 评估负费率机会 (做多合约，卖出现货)
            if funding_rate < 0 and self.config.strategy.enable_negative_rate_strategy:
                decision = await self._evaluate_opportunity(
                    symbol, funding_rate, 'LONG', capital_per_trade
                )
                if decision:
                    decisions.append(decision)

        self.logger.info(f"扫描完成，发现 {len(decisions)} 个潜在套利机会。")
        return decisions

    async def _evaluate_opportunity(
            self, symbol: str, funding_rate: float, direction: str, capital_to_use: float
    ) -> Optional[ArbitrageDecision]:
        """
        对单个交易对进行详细的评估。
        """
        # 1. 获取该交易对的L2订单簿
        order_book = await self.data_fetcher.fetch_l2_order_book(symbol)
        if not order_book or not order_book.get('spot') or not order_book.get('swap'):
            self.logger.warning(f"[{symbol}] 无法获取完整的现货和合约订单簿数据，跳过评估。")
            return None

        # 2. 分析流动性并计算预期滑点
        try:
            # 正费率：买现货(看asks), 空合约(看bids)
            # 负费率：卖现货(看bids), 多合约(看asks)
            spot_side = 'asks' if direction == 'SHORT' else 'bids'
            swap_side = 'bids' if direction == 'SHORT' else 'asks'

            avg_spot_price, spot_slippage = self._analyze_liquidity_and_slippage(
                order_book['spot'][spot_side], capital_to_use
            )
            avg_swap_price, swap_slippage = self._analyze_liquidity_and_slippage(
                order_book['swap'][swap_side], capital_to_use
            )
        except ValueError as e:
            self.logger.warning(f"[{symbol}] {e}")
            return None

        # 检查滑点是否在容忍范围内
        max_slippage = self.config.risk.max_allowed_slippage
        if spot_slippage > max_slippage or swap_slippage > max_slippage:
            self.logger.warning(
                f"[{symbol}] 滑点过高，放弃机会。现货滑点: {spot_slippage:.4%}, "
                f"合约滑点: {swap_slippage:.4%}, 允许最大滑点: {max_slippage:.4%}"
            )
            return None

        # 3. 计算综合成本与收益
        # 3.1 滑点成本
        # 滑点成本百分比 = (合约滑点 + 现货滑点)
        slippage_cost_pct = spot_slippage + swap_slippage

        # 3.2 交易手续费成本 (吃单)
        # 假设开仓和平仓各承担一次taker fee, 总共是4次
        spot_taker_fee = self.data_fetcher.get_fee_rate(symbol, 'spot', 'taker')
        swap_taker_fee = self.data_fetcher.get_fee_rate(symbol, 'swap', 'taker')
        total_taker_fee_pct = spot_taker_fee + swap_taker_fee  # 单次开仓的费用

        # 3.3 (可选) 现货赚币收益
        spot_earning_rate = 0.0
        if direction == 'SHORT' and self.config.strategy.enable_spot_earning:
            base_currency = symbol.split('/')[0]
            earn_rates = await self.data_fetcher.fetch_earn_rates()
            if base_currency in earn_rates:
                spot_earning_rate = earn_rates[base_currency]

        # 3.4 (可选) 现货借贷成本
        borrow_interest_rate = 0.0
        # TODO: 集成借币利息获取逻辑

        # 4. 计算最终净APR
        # 资金费率每天收取3次，一年365天
        funding_apr = abs(funding_rate) * 3 * 365

        # 总成本 = 开仓手续费 + 平仓手续费 + 开仓滑点 + 平仓滑点(保守估计，与开仓相同)
        total_cost_apr = (total_taker_fee_pct * 2 + slippage_cost_pct * 2)

        net_apr = funding_apr + spot_earning_rate - total_cost_apr - borrow_interest_rate

        # 5. 最终决策
        min_return = self.config.strategy.min_annualized_return
        if net_apr > min_return:
            decision_reason = (
                f"净APR {net_apr:.4%} > 阈值 {min_return:.4%}. "
                f"构成: 资金费APR {funding_apr:.4%} + 赚币APR {spot_earning_rate:.4%} - "
                f"总成本APR {total_cost_apr:.4%}"
            )
            self.logger.info(f"[{symbol}] 发现符合条件的套利机会 ({direction})。{decision_reason}")

            spot_book_asks = order_book['spot']['asks']
            spot_book_bids = order_book['spot']['bids']
            swap_book_asks = order_book['swap']['asks']
            swap_book_bids = order_book['swap']['bids']

            return ArbitrageDecision(
                symbol=symbol,
                direction=direction,
                decision_reason=decision_reason,
                leverage=self.config.risk.leverage,
                capital_to_use=capital_to_use,
                estimated_funding_rate=funding_rate,
                spot_ask_price=spot_book_asks[0][0] if spot_book_asks else 0,
                spot_bid_price=spot_book_bids[0][0] if spot_book_bids else 0,
                swap_ask_price=swap_book_asks[0][0] if swap_book_asks else 0,
                swap_bid_price=swap_book_bids[0][0] if swap_book_bids else 0,
                avg_spot_price=avg_spot_price,
                avg_swap_price=avg_swap_price,
                spot_slippage=spot_slippage,
                swap_slippage=swap_slippage,
                net_apr=net_apr,
                trade_fee_cost=total_taker_fee_pct,
                slippage_cost=slippage_cost_pct,
                spot_earning_rate=spot_earning_rate,
                borrow_interest_rate=borrow_interest_rate,
            )

        return None

    def _analyze_liquidity_and_slippage(
            self, order_book_side: List[Tuple[float, float]], capital: float
    ) -> Tuple[float, float]:
        """
        分析订单簿一侧的流动性，计算市价单的加权平均成交价和滑点。

        Args:
            order_book_side: 订单簿的一侧，asks或bids的列表 [(price, amount), ...]
            capital: 计划用于交易的资本 (以USDT计价)。

        Returns:
            一个元组 (加权平均成交价, 滑点百分比)。

        Raises:
            ValueError: 如果流动性不足。
        """
        if not order_book_side:
            raise ValueError("订单簿为空，无法分析流动性。")

        first_price = order_book_side[0][0]
        total_cost = 0.0
        total_amount = 0.0
        capital_remaining = capital

        for price, amount in order_book_side:
            order_value = price * amount

            if capital_remaining <= order_value:
                # 这一层足以消耗所有资本
                amount_to_take = capital_remaining / price
                total_cost += amount_to_take * price
                total_amount += amount_to_take
                capital_remaining = 0
                break
            else:
                # 吃掉这一整层
                total_cost += order_value
                total_amount += amount
                capital_remaining -= order_value

        if capital_remaining > 0:
            raise ValueError(f"市场流动性不足，无法满足 {capital:.2f} USDT 的交易量。")

        if total_amount == 0:
            return 0, 0

        avg_price = total_cost / total_amount
        # 滑点计算公式: (实际成交均价 - 盘口第一档价) / 盘口第一档价
        slippage = abs((avg_price - first_price) / first_price)

        return avg_price, slippage