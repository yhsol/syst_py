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
    ):
        self.bithumb = bithumb_service
        self.strategy = strategy_service
        self.trading_history: List[Dict[str, Union[str, float]]] = []
        self.last_actions: Dict[str, str] = {}  # 마지막 액션을 저장할 딕셔너리
        self.holding_coins: Dict[str, Dict] = {}
        self.trailing_stop_percent = 0.01
        self.stop_loss_percent = 0.02

    async def backtest(
        self,
        symbols: Optional[List[str]],
        start_date: Optional[str],
        end_date: Optional[str],
        timeframe: str = "1h",
    ):
        # 초기화
        self.trading_history = []
        self.last_actions = {}
        self.holding_coins = {}

        candidate_symbols = []

        if symbols:
            candidate_symbols = symbols
        else:
            all_coins = await self.bithumb.get_current_price("KRW")
            filtered_by_value = await self.bithumb.filter_coins_by_value(all_coins, 10)
            candidate_symbols = filtered_by_value

        start_datetime = (
            datetime.strptime(start_date, "%Y-%m-%d") if start_date else None
        )
        end_datetime = datetime.strptime(end_date, "%Y-%m-%d") if end_date else None

        for symbol in candidate_symbols:
            # 과거 데이터를 가져옵니다.
            historical_data = await self.bithumb.get_candlestick_data(
                symbol, "KRW", timeframe
            )
            if historical_data["status"] != "0000":
                continue  # 데이터가 유효하지 않으면 건너뜁니다.

            for data_point in historical_data["data"]:
                timestamp, _, _, _, close_price, _ = data_point
                date = datetime.fromtimestamp(timestamp / 1000)
                if (start_datetime and date < start_datetime) or (
                    end_datetime and date > end_datetime
                ):
                    continue  # 날짜가 범위를 벗어나면 건너뜁니다

                date_str = date.strftime("%Y-%m-%d %H:%M:%S")
                close_price = float(close_price)

                # 해당 시점의 시그널을 분석합니다.
                analysis = self.analyze_currency_by_turtle(
                    symbol, historical_data["data"], timestamp
                )

                # 매수 및 매도 조건을 체크합니다.
                await self.check_trading_conditions(
                    symbol, close_price, analysis, date_str
                )

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
        self, symbol: str, current_price: float, analysis: dict, date: str
    ):
        latest_signal = analysis.get("type_latest_signal", "")
        last_signal = analysis.get("type_last_true_signal", "")
        last_action_for_symbol = self.last_actions.get(symbol)

        # 트레일링 스탑과 스톱 로스 조건
        if symbol in self.holding_coins:
            holding_coin = self.holding_coins[symbol]
            highest_price = holding_coin["highest_price"]
            trailing_stop_price = highest_price * 0.99
            stop_loss_price = holding_coin["buy_price"] * (1 - self.stop_loss_percent)

            # 트레일링 스탑 조건
            if current_price <= trailing_stop_price:
                print("Trailing stop condition met")
                self.trading_history.append(
                    {
                        "symbol": symbol,
                        "action": "sell",
                        "price": current_price,
                        "date": date,
                        "profit": (current_price - holding_coin["buy_price"])
                        / holding_coin["buy_price"]
                        * 100,  # 수익률 추가
                    }
                )
                del self.holding_coins[symbol]
                self.last_actions[symbol] = "sell"  # 마지막 액션 업데이트
                return

            # 스톱 로스 조건
            if current_price <= stop_loss_price:
                print("Stop loss condition met")
                self.trading_history.append(
                    {
                        "symbol": symbol,
                        "action": "sell",
                        "price": current_price,
                        "date": date,
                        "profit": (current_price - holding_coin["buy_price"])
                        / holding_coin["buy_price"]
                        * 100,  # 수익률 추가
                    }
                )
                del self.holding_coins[symbol]
                self.last_actions[symbol] = "sell"  # 마지막 액션 업데이트
                return

        # 현재 액션과 마지막 액션이 반대인지 확인
        if last_action_for_symbol != "buy" and await check_entry_condition(
            symbol, latest_signal, self.trading_history, is_test=True
        ):
            print("Buy condition met")
            self.holding_coins[symbol] = {
                "units": 1.0,  # 백테스팅에서는 1 단위로 가정합니다.
                "buy_price": current_price,
                "stop_loss_price": current_price * (1 - self.stop_loss_percent),
                "order_id": None,
                "profit": 0,
                "reason": "backtest",
                "highest_price": current_price,
                "trailing_stop_price": current_price * (1 - self.trailing_stop_percent),
                "split_sell_count": 0,
            }
            self.trading_history.append(
                {
                    "symbol": symbol,
                    "action": "buy",
                    "price": current_price,
                    "date": date,
                }
            )
            self.last_actions[symbol] = "buy"  # 마지막 액션 업데이트

        if last_action_for_symbol == "buy" and await check_exit_condition(
            symbol, last_signal, self.trading_history, is_test=True
        ):
            print("Sell condition met")
            if symbol in self.holding_coins:
                buy_price = self.holding_coins[symbol]["buy_price"]
                profit = (current_price - buy_price) / buy_price * 100  # 수익률 계산
                self.trading_history.append(
                    {
                        "symbol": symbol,
                        "action": "sell",
                        "price": current_price,
                        "date": date,
                        "profit": profit,  # 수익률 추가
                    }
                )
                del self.holding_coins[symbol]
                self.last_actions[symbol] = "sell"  # 마지막 액션 업데이트

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

        with pd.ExcelWriter("backtest_results.xlsx", mode="w") as writer:
            df.to_excel(writer, index=False, sheet_name="Trades")
            summary.to_excel(writer, index=False, sheet_name="Summary")

        logger.info("Backtest results saved to backtest_results.xlsx")
