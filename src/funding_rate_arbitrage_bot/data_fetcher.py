import asyncio
import ccxt.pro as ccxt  # 使用 ccxt.pro 支持异步操作
import logging
from typing import Dict, List, Any, Union

# 获取日志记录器实例，假设日志配置已由 logger_config.py 处理
logger = logging.getLogger(__name__)


class DataFetcher:
    """
    数据采集模块，负责从OKX交易所异步获取所有必要的市场数据和账户数据。
    """

    def __init__(self, exchange: ccxt.Exchange):
        """
        初始化 DataFetcher。

        Args:
            exchange: 一个已配置的 ccxt 交易所实例（例如 OKX），应为异步版本。
        """
        self.exchange = exchange
        logger.info("DataFetcher initialized with exchange: %s", exchange.id)

    async def fetch_funding_rates(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有永续合约的当前和预测资金费率。

        Returns:
            一个字典，键为交易对符号（例如 'BTC/USDT:USDT'），值为包含资金费率信息的字典。
            示例：{'BTC/USDT:USDT': {'current_rate': 0.0001, 'next_rate': 0.0001, 'next_funding_timestamp': '2023-01-01T08:00:00.000Z'}}
        """
        try:
            # ccxt 的 fetch_funding_rates 返回一个以 market ID 为键的字典
            all_funding_rates = await self.exchange.fetch_funding_rates()
            funding_rates_map = {}
            for market_id, data in all_funding_rates.items():
                market = self.exchange.markets_by_id.get(market_id)
                # 过滤出永续合约 (通常 ccxt 会返回 contract=True 和 swap=True 的市场)
                if market and market.get('contract') and market.get('swap'):
                    symbol = market['symbol']
                    funding_rates_map[symbol] = {
                        'current_rate': data.get('fundingRate'),
                        'next_rate': data.get('nextFundingRate'),
                        'next_funding_timestamp': data.get('nextFundingTime')  # 下次资金费收取时间戳
                    }
            logger.info("Fetched funding rates for %d markets.", len(funding_rates_map))
            return funding_rates_map
        except Exception as e:
            logger.error("Error fetching funding rates: %s", e, exc_info=True)
            return {}

    async def fetch_l2_order_book(self, symbol: str, limit: int = 20) -> Dict[str, List[List[float]]]:
        """
        获取指定交易对的 L2 深度订单簿数据（买单和卖单）。

        Args:
            symbol: 交易对符号 (例如 'BTC/USDT' 用于现货, 'BTC/USDT:USDT' 用于永续合约)。
            limit: 订单簿的深度限制（即获取多少档位的数据）。

        Returns:
            一个字典，包含买单(bids)和卖单(asks)列表。
            示例：{'bids': [[price, amount], ...], 'asks': [[price, amount], ...]}
        """
        try:
            order_book = await self.exchange.fetch_order_book(symbol, limit=limit)
            logger.info("Fetched L2 order book for %s: %d bids, %d asks.",
                        symbol, len(order_book.get('bids', [])), len(order_book.get('asks', [])))
            return {
                'bids': order_book.get('bids', []),
                'asks': order_book.get('asks', [])
            }
        except Exception as e:
            logger.error("Error fetching L2 order book for %s: %s", symbol, e, exc_info=True)
            return {'bids': [], 'asks': []}

    async def fetch_earn_rates(self) -> Dict[str, Any]:
        """
        获取 OKX Simple Earn 各币种的活期年化收益率。
        注意：ccxt 库目前可能不直接支持所有交易所的“赚币”产品 API。
        此函数目前为占位符实现，可能需要根据 OKX 的具体 API 文档
        或使用 OKX 官方 SDK 进行直接 API 调用。

        Returns:
            一个字典，键为币种，值为其活期年化收益率。
            示例：{'USDT': 0.05, 'BTC': 0.01}
        """
        logger.warning("fetch_earn_rates: ccxt might not directly support OKX Simple Earn products. "
                       "This function is a placeholder and may require direct OKX API integration for accurate data.")
        # 这是一个模拟数据，实际应用中需要调用 OKX Simple Earn 相关的 API
        try:
            # 假设一个 hipotetical ccxt 方法，或者更可能的是直接调用 OKX 的 REST API
            # 例如: OKX v5 API: GET /api/v5/asset/deposit-interest
            # earn_products = await self.exchange.publicGetAssetDepositInterest() # 假设的 ccxt wrapper
            # return {item['ccy']: float(item['apy']) for item in earn_products['data']}

            # 暂时返回模拟数据
            return {
                'USDT': 0.05,  # 示例：5% USDT 活期年化收益
                'BTC': 0.01,  # 示例：1% BTC 活期年化收益
                'ETH': 0.015  # 示例：1.5% ETH 活期年化收益
            }
        except Exception as e:
            logger.error("Error fetching earn rates: %s", e, exc_info=True)
            return {}

    async def fetch_account_balance(self) -> Dict[str, Dict[str, float]]:
        """
        获取账户所有币种的资产信息。

        Returns:
            一个字典，键为币种，值为包含 total（总额）、free（可用）和 used（占用）余额的字典。
            示例：{'USDT': {'total': 1000.0, 'free': 900.0, 'used': 100.0}}
        """
        try:
            balance = await self.exchange.fetch_balance()
            formatted_balance = {}
            for currency, data in balance['total'].items():
                # 只包含总余额不为零的币种
                if data > 0:
                    formatted_balance[currency] = {
                        'total': balance['total'].get(currency, 0.0),
                        'free': balance['free'].get(currency, 0.0),
                        'used': balance['used'].get(currency, 0.0)
                    }
            logger.info("Fetched account balance for %d currencies.", len(formatted_balance))
            return formatted_balance
        except Exception as e:
            logger.error("Error fetching account balance: %s", e, exc_info=True)
            return {}

    async def fetch_positions(self) -> List[Dict[str, Any]]:
        """
        获取当前合约持仓信息。

        Returns:
            一个列表，每个元素代表一个合约持仓的详细信息。
            示例：[{'symbol': 'BTC/USDT:USDT', 'side': 'long', 'amount': 0.1, 'entryPrice': 60000, ...}]
        """
        try:
            # fetch_positions 可以返回现货杠杆和合约的持仓
            # 我们只关心永续合约持仓 (contract=True, swap=True)
            all_positions = await self.exchange.fetch_positions()
            swap_positions = []
            for position in all_positions:
                market = self.exchange.markets.get(position['symbol'])
                if market and market.get('contract') and market.get('swap'):
                    swap_positions.append({
                        'symbol': position.get('symbol'),
                        'side': position.get('side'),  # 'long' 或 'short'
                        'amount': position.get('contracts'),  # 合约数量，有些交易所用 'amount'
                        'entryPrice': position.get('entryPrice'),
                        'liquidationPrice': position.get('liquidationPrice'),
                        'marginRatio': position.get('initialMarginPercentage'),  # 或 'marginRatio'，取决于 ccxt 返回字段
                        'unrealizedPnl': position.get('unrealizedPnl'),
                        'timestamp': position.get('timestamp')
                    })
            logger.info("Fetched %d swap positions.", len(swap_positions))
            return swap_positions
        except Exception as e:
            logger.error("Error fetching positions: %s", e, exc_info=True)
            return []

    async def fetch_all(self) -> Dict[str, Any]:
        """
        并发获取所有核心市场和账户数据。
        (注意：L2 订单簿通常在决策引擎需要时按需获取，因此不包含在此处。)

        Returns:
            一个字典，包含所有并发获取到的数据。
        """
        logger.info("Fetching all market and account data concurrently...")
        # 使用 asyncio.gather 并发执行所有数据获取任务
        funding_rates, account_balance, positions, earn_rates = await asyncio.gather(
            self.fetch_funding_rates(),
            self.fetch_account_balance(),
            self.fetch_positions(),
            self.fetch_earn_rates()
        )

        return {
            'funding_rates': funding_rates,
            'account_balance': account_balance,
            'positions': positions,
            'earn_rates': earn_rates
        }


# --- 以下是用于独立测试的示例代码，不应在生产环境中直接运行 ---
async def main():
    # ⚠️ 请将 'YOUR_API_KEY', 'YOUR_SECRET', 'YOUR_PASSWORD' 替换为你的 OKX API 密钥
    # 并且根据 config.yml 中的 sandbox_mode 设置 'sandbox' 参数
    okx_config = {
        'apiKey': 'YOUR_API_KEY',
        'secret': 'YOUR_SECRET',
        'password': 'YOUR_PASSWORD',
        'options': {
            'defaultType': 'swap',  # 明确指定默认交易类型为永续合约
        },
        'sandbox': True  # 设置为 True 使用模拟盘，False 使用实盘
    }

    # 初始化 ccxt OKX 交易所实例
    exchange = ccxt.okx(okx_config)

    # 启用限速，以避免频繁请求被交易所限制
    exchange.enableRateLimit = True

    fetcher = DataFetcher(exchange)

    # 打印所有并发获取的数据
    print("--- 正在获取所有数据 ---")
    all_data = await fetcher.fetch_all()
    import json
    print(json.dumps(all_data, indent=4))

    # 示例：获取特定交易对的 L2 订单簿
    print("\n--- 获取 BTC/USDT:USDT 永续合约 L2 订单簿 (限 20 档) ---")
    btc_usdt_swap_symbol = 'BTC/USDT:USDT'  # OKX 永续合约的常见符号格式
    l2_order_book = await fetcher.fetch_l2_order_book(btc_usdt_swap_symbol)
    print(json.dumps(l2_order_book, indent=4))

    # 关闭 ccxt 连接
    await exchange.close()


if __name__ == "__main__":
    # 为独立测试配置基本的日志输出
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    asyncio.run(main())