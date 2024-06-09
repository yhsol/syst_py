from datetime import datetime
import logging
from typing import Dict, List, Optional, Union
import pandas as pd

from app.services.bithumb_service import BithumbService
from app.services.stratege_service import StrategyService
from app.utils.trading_helpers import check_entry_condition, check_exit_condition

# Logging 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("backtesting.log"), logging.StreamHandler()],
)

logger = logging.getLogger(__name__)


class Backtest:
    def __init__(
        self,
        bithumb_service: BithumbService,
        strategy_service: StrategyService,
        trading_bot,
    ):
        self.bithumb = bithumb_service
        self.strategy = strategy_service
        self.trading_bot = trading_bot
        self.trading_history: List[Dict[str, Union[str, float]]] = []

    async def backtest(
        self,
        symbols: Optional[List[str]],
        start_date: Optional[str],
        end_date: Optional[str],
        timeframe: str = "1h",
    ):
        candidate_symbols = []

        if symbols:
            candidate_symbols = symbols
        else:
            all_coins = await self.bithumb.get_current_price("KRW")
            filtered_by_value = await self.bithumb.filter_coins_by_value(all_coins, 100)
            candidate_symbols = filtered_by_value

        for symbol in candidate_symbols:
            # 과거 데이터를 가져옵니다.
            historical_data = await self.bithumb.get_candlestick_data(
                symbol, "KRW", timeframe
            )
            if historical_data["status"] != "0000":
                continue  # 데이터가 유효하지 않으면 건너뜁니다.

            for data_point in historical_data["data"]:
                timestamp, open_price, high_price, low_price, close_price, volume = (
                    data_point
                )
                date = datetime.fromtimestamp(timestamp / 1000).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                print(f"date: {date}")
                close_price = float(close_price)

                # 해당 시점의 시그널을 분석합니다.
                analysis = self.analyze_currency_by_turtle(
                    symbol, historical_data["data"], timestamp
                )

                # 매수 및 매도 조건을 체크합니다.
                await self.check_trading_conditions(symbol, close_price, analysis)

        self.save_results_to_excel()

    def analyze_currency_by_turtle(
        self, symbol: str, historical_data: list, current_timestamp: int
    ):
        df = pd.DataFrame(
            historical_data,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

        # 해당 시점까지의 데이터를 필터링
        df = df[df["timestamp"] <= pd.to_datetime(current_timestamp, unit="ms")]

        signals = self.strategy.compute_signals(df)
        signal_columns = ["long_entry", "short_entry", "long_exit", "short_exit"]

        filtered_signals = signals[["timestamp"] + signal_columns]
        filtered_signals = filtered_signals.sort_values(by="timestamp", ascending=False)

        signal_status = self.strategy.determine_signal_status(
            filtered_signals, signal_columns
        )

        return {
            "ticker": symbol,
            "status": "success",
            "type_latest_signal": signal_status["latest"],
            "type_last_true_signal": signal_status["last_true"],
            "type_last_true_timestamp": signal_status["last_true_timestamp"],
            "data": filtered_signals.head(20).to_dict(orient="records"),
        }

    async def check_trading_conditions(
        self, symbol: str, current_price: float, analysis: dict
    ):
        latest_signal = analysis.get("type_latest_signal", "")
        last_signal = analysis.get("type_last_true_signal", "")

        if await check_entry_condition(
            symbol, latest_signal, self.trading_bot.trading_history, is_test=True
        ):
            print("Buy condition met")
            self.trading_bot.holding_coins[symbol] = {
                "units": 1.0,  # 백테스팅에서는 1 단위로 가정합니다.
                "buy_price": current_price,
                "stop_loss_price": current_price * 0.98,
                "order_id": None,
                "profit": 0,
                "reason": "backtest",
                "highest_price": current_price,
                "trailing_stop_price": current_price
                * (1 - self.trading_bot.trailing_stop_percent),
                "split_sell_count": 0,
            }
            self.trading_history.append(
                {
                    "symbol": symbol,
                    "action": "buy",
                    "price": current_price,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

        if await check_exit_condition(
            symbol, last_signal, self.trading_bot.trading_history, is_test=True
        ):
            print("Sell condition met")
            if symbol in self.trading_bot.holding_coins:
                buy_price = self.trading_bot.holding_coins[symbol]["buy_price"]
                profit = (current_price - buy_price) / buy_price * 100  # 수익률 계산
                self.trading_history.append(
                    {
                        "symbol": symbol,
                        "action": "sell",
                        "price": current_price,
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "profit": profit,  # 수익률 추가
                    }
                )
                del self.trading_bot.holding_coins[symbol]

    def save_results_to_excel(self):
        df = pd.DataFrame(self.trading_history)

        # 수익률 관련 통계 계산
        profits = df[df["action"] == "sell"]["profit"]
        final_profit = profits.sum()
        max_profit = profits.max()
        min_profit = profits.min()
        avg_profit = profits.mean()
        avg_loss = profits[profits < 0].mean()

        # 통계 데이터를 추가합니다.
        summary = pd.DataFrame(
            {
                "Metric": [
                    "Final Profit",
                    "Max Profit",
                    "Min Profit",
                    "Average Profit",
                    "Average Loss",
                ],
                "Value": [
                    final_profit,
                    max_profit,
                    min_profit,
                    avg_profit,
                    avg_loss,
                ],
            }
        )

        with pd.ExcelWriter("backtest_results.xlsx") as writer:
            df.to_excel(writer, index=False, sheet_name="Trades")
            summary.to_excel(writer, index=False, sheet_name="Summary")

        logger.info("Backtest results saved to backtest_results.xlsx")
