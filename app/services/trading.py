import asyncio
import json
import logging
import re
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

from fastapi import Query
import pandas as pd
import websockets

from app.services.bithumb_service import BithumbPrivateService, BithumbService
from app.services.stratege_service import StrategyService
from app.telegram.telegram_client import send_telegram_message

# Logging 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("trading_bot.log"), logging.StreamHandler()],
)

logger = logging.getLogger(__name__)


class TradingBot:
    def __init__(
        self,
        bithumb_service: BithumbService,
        bithumb_private_service: BithumbPrivateService,
        strategy_service: StrategyService,
    ):
        self.connections: List = []
        self.bithumb = bithumb_service
        self.bithumb_private = bithumb_private_service
        self.strategy = strategy_service
        self.active_symbols: Set[str] = set()
        self.weights = {"volume": 0.3, "rsi": 0.2, "price_change": 0.2, "vwma": 0.3}
        self.candlestick_data: Dict = {}  # 캔들스틱 데이터를 저장할 딕셔너리
        self.holding_coins: Dict = {}
        self.trading_history: Dict = {}
        self.in_trading_process_coins: List = []
        self.interest_symbols: Set[str] = set()
        self.running_tasks: Dict[str, asyncio.Task] = (
            {}
        )  # 실행 중인 태스크를 저장할 딕셔너리
        self.websocket_connections: Dict[str, websockets.WebSocketClientProtocol] = {}
        self.available_krw_to_each_trade: float = 10000
        self.current_timeframe = "10m"
        self.timeframe_intervals = {
            "1m": timedelta(minutes=1),
            "5m": timedelta(minutes=5),
            "10m": timedelta(minutes=10),
            "15m": timedelta(minutes=15),
            "30m": timedelta(minutes=30),
            "1h": timedelta(hours=1),
            "4h": timedelta(hours=4),
            "6h": timedelta(hours=6),
            "12h": timedelta(hours=12),
            "24h": timedelta(hours=24),
        }
        self.last_analysis_time: Dict[str, datetime] = {}

    def format_trading_history(self, trading_history):
        print("log=> Trading history: ", trading_history)
        try:
            formatted_entries = []
            for symbol, entries in trading_history.items():
                formatted_entries.append(f"{symbol}:")
                for entry in entries:
                    if "action" in entry and "price" in entry:
                        entry_str = (
                            f"  - {entry['action'].capitalize()} at {entry['price']} on {entry['entry_time']}"
                            if entry["action"] == "buy"
                            else f"  - {entry['action'].capitalize()} at {entry['price']} on {entry['exit_time']}"
                        )
                        formatted_entries.append(entry_str)
            print("log=> Formatted entries: ", formatted_entries)
            return "\n".join(formatted_entries) + "\n\n"
        except Exception as e:
            logger.error("An error occurred while formatting trading history: %s", e)
            logger.error("Traceback: %s", traceback.format_exc())
            return str(trading_history)

    async def check_entry_condition(self, symbol, signal):
        if ("short_exit" in signal) or ("long_entry" in signal):
            # 매수 시그널
            await send_telegram_message(
                (
                    f"🚀 {symbol} 매수 시그널 발생! 🚀\n\n"
                    f"{self.format_trading_history(self.trading_history)}"
                ),
                term_type="short-term",
            )
            return True
        return False

    async def check_exit_condition(self, symbol, signal):
        if ("long_exit" in signal) or ("short_entry" in signal):
            # 매도 시그널
            await send_telegram_message(
                (
                    f"🚀 {symbol} 매도 시그널 발생!\n\n"
                    f"{self.format_trading_history(self.trading_history)}"
                    "🚀"
                ),
                term_type="short-term",
            )
            return True
        return False

    async def check_stop_loss_condition(self, symbol, current_price):
        if symbol in self.holding_coins:
            stop_loss_price = self.holding_coins[symbol]["stop_loss_price"]
            if current_price < stop_loss_price:
                return True
        return False

    async def get_profit_percentage(self, symbol, current_price):
        if symbol in self.holding_coins:
            average_buy_price = self.holding_coins[symbol]["buy_price"]
            profit_percentage = (
                (current_price - average_buy_price) / average_buy_price * 100
                if average_buy_price
                else None
            )
            return profit_percentage
        return None

    async def get_signal(self, symbol):
        df = self.candlestick_data[symbol]
        signals = self.strategy.compute_signals(df)
        signal_columns = ["long_entry", "short_entry", "long_exit", "short_exit"]

        filtered_signals = signals[["timestamp"] + signal_columns]
        filtered_signals = filtered_signals.sort_values(by="timestamp", ascending=False)

        signal_status = self.strategy.determine_signal_status(
            filtered_signals, signal_columns
        )

        signal = {
            "ticker": symbol,
            "status": "0000",
            "type_latest_signal": signal_status["latest"],
            "type_last_true_signal": signal_status["last_true"],
            "type_last_true_timestamp": signal_status["last_true_timestamp"],
            "data": filtered_signals.head(20).to_dict(orient="records"),
        }

        return signal

    async def get_available_buy_units(self, symbol):
        # 주문 가능 수량 조회
        balance = await self.bithumb_private.get_balance(symbol)
        available_krw = balance["data"]["available_krw"]
        available_krw = float(available_krw)

        # 매수 가능 금액을 10000원으로 제한
        available_krw = min(available_krw, self.available_krw_to_each_trade)

        # 매수 금액을 어떻게 정할지는 좀 더 고민해봐야할 듯.
        # available_krw 의 몇 % 로 할 수도 있고.
        # 특정 금액을 기준으로 할 수도 있고.
        # 자산관리 전략에 따라 조정할 수 있도록 해야할 듯.

        orderbook = await self.bithumb.get_orderbook(symbol)
        ask_price = orderbook["data"]["asks"][0]["price"]
        ask_price = float(ask_price)

        # 수수료 0.28% 라고 가정. 정화하지 않긴 한데, bithumb page 에서 책정하는게 정확히 어떤건지 알 수 없어서 안전한 수량으로 계산
        fee = 0.0028
        units = available_krw / ask_price * (1 - fee)

        return units

    async def get_available_sell_units(self, symbol):
        # 주문 가능 수량 조회
        balance = await self.bithumb_private.get_balance(symbol)
        coin_balance = balance["data"][f"available_{symbol.lower()}"]
        logger.info("%s: Available balance: %s", symbol, coin_balance)

        return coin_balance

    async def buy(self, symbol):
        logger.info("Execute to buy %s", symbol)
        try:
            # 매수 주문 실행
            buy_units = await self.get_available_buy_units(symbol)

            available_units = round(buy_units, 8)

            result = await self.bithumb_private.market_buy(
                units=available_units,
                order_currency=symbol,
                payment_currency="KRW",
            )
            logger.info("Buy result: %s", result)

            if result and result["status"] == "0000" and "order_id" in result:
                order_detail = await self.bithumb_private.get_order_detail(
                    order_id=result["order_id"],
                    order_currency=symbol,
                    payment_currency="KRW",
                )
                logger.info("Buy Order detail: %s", order_detail)

                # 주문 상세 정보가 성공적으로 조회되었는지 확인
                if order_detail and order_detail["status"] == "0000":
                    data = order_detail.get("data", {})
                    contracts = data.get("contract", [])
                    if contracts:
                        contract = contracts[0]
                        buy_price = float(contract.get("price", 0))
                        stop_loss_price = buy_price * 0.98

                        self.holding_coins[symbol] = {
                            "units": available_units,
                            "buy_price": buy_price,
                            "stop_loss_price": stop_loss_price,
                            "order_id": result["order_id"],
                        }
                        # 매수 체결 메시지
                        await send_telegram_message(
                            (
                                f"🟢 {symbol} 매수 체결! 🟢\n\n"
                                f"💰 매수 가격: {buy_price}\n"
                                f"📉 손절가: {stop_loss_price}\n\n"
                                f"📊 Holding coins: {list(self.holding_coins.keys())}\n\n"
                            ),
                            term_type="short-term",
                        )
                        logger.info(
                            "Buy Success and Holding coins: %s", self.holding_coins
                        )
                    else:
                        logger.error(
                            "No contract information available for order_id: %s",
                            result["order_id"],
                        )
                        logger.error("Traceback: %s", traceback.format_exc())
                else:
                    logger.error(
                        "Failed to retrieve order details for order_id: %s",
                        result["order_id"],
                    )
                    logger.error("Traceback: %s", traceback.format_exc())
            return {
                "status": "0000",
                "message": f"Successfully buy {available_units} {symbol}",
            }
        except Exception as e:
            logger.error("An error occurred while buying %s: %s", symbol, e)
            logger.error("Traceback: %s", traceback.format_exc())
            return {"status": "error", "message": str(e)}

    async def sell(self, symbol, amount=1.0):
        try:
            logger.info("Execute to sell %s", symbol)
            sell_units = await self.get_available_sell_units(symbol)
            sell_units = float(sell_units)

            if amount < 1.0:
                sell_units = round(sell_units * amount, 8)

            logger.info("%s: Available sell units: %s", symbol, sell_units)
            result = await self.bithumb_private.market_sell(
                units=sell_units,
                order_currency=symbol,
                payment_currency="KRW",
            )
            logger.info("Sell result: %s", result)

            # 매도 주문이 성공하면 holding_coins 에서 해당 코인 제거
            if result and result["status"] == "0000" and "order_id" in result:
                order_detail = await self.bithumb_private.get_order_detail(
                    order_id=result["order_id"],
                    order_currency=symbol,
                    payment_currency="KRW",
                )
                logger.info("Sell Order detail: %s", order_detail)

                # 주문 상세 정보가 성공적으로 조회되었는지 확인
                if order_detail and order_detail["status"] == "0000":
                    data = order_detail.get("data", {})
                    contracts = data.get("contract", [])
                    if contracts:
                        contract = contracts[0]
                        current_price = float(contract.get("price", 0))
                        profit = current_price - self.holding_coins[symbol]["buy_price"]
                        # 매도 체결 메시지
                        await send_telegram_message(
                            (
                                f"🔴 {symbol} 매도 체결! 🔴\n\n"
                                f"💰 매도 가격: {current_price}\n\n"
                                f"📈 수익: {profit}\n\n"
                                f"📊 Holding coins: {list(self.holding_coins.keys())}\n\n"
                            ),
                            term_type="short-term",
                        )
                if symbol in self.holding_coins:
                    self.remove_holding_coin(symbol)

                logger.info("Sell Success and Holding coins: %s", self.holding_coins)

            return {
                "status": "0000",
                "message": f"Successfully sold {sell_units} {symbol}",
            }
        except Exception as e:
            logger.error("An error occurred while selling %s: %s", symbol, e)
            logger.error("Traceback: %s", traceback.format_exc())
            return {"status": "error", "message": str(e)}

    async def execute_trade(self, action, symbol, amount=1.0):
        try:
            if action == "buy":
                # 매수 주문 실행
                result = await self.buy(symbol)
                return result

            if action == "sell":
                # 매도 주문 실행
                result = await self.sell(symbol, amount)
                return result

        except Exception as e:
            logger.error(
                "An error occurred while executing %s on %s: %s", action, symbol, e
            )
            logger.error("Traceback: %s", traceback.format_exc())
            return {"status": "error", "message": str(e)}

    async def calculate_rsi(self, close_prices: List[float], period: int = 14) -> float:
        gains = [
            close_prices[i + 1] - close_prices[i]
            for i in range(len(close_prices) - 1)
            if close_prices[i + 1] > close_prices[i]
        ]
        losses = [
            close_prices[i] - close_prices[i + 1]
            for i in range(len(close_prices) - 1)
            if close_prices[i + 1] < close_prices[i]
        ]
        average_gain = sum(gains) / period
        average_loss = sum(losses) / period
        if average_loss == 0:
            return 100
        rs = average_gain / average_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    async def calculate_moving_average(
        self, close_prices: List[float], period: int
    ) -> float:
        return sum(close_prices[-period:]) / period

    async def is_in_uptrend(self, symbol: str) -> bool:
        one_day_analysis = await self.strategy.analyze_currency_by_turtle(
            order_currency=symbol,
            payment_currency="KRW",
            chart_intervals="24h",
        )
        one_day_type_last_true_signal = one_day_analysis.get(
            "type_last_true_signal", ""
        )

        # if not long signal, return False
        if "long_entry" not in one_day_type_last_true_signal:
            return False

        six_hour_analysis = await self.strategy.analyze_currency_by_turtle(
            order_currency=symbol,
            payment_currency="KRW",
            chart_intervals="6h",
        )
        six_hour_type_last_true_signal = six_hour_analysis.get(
            "type_last_true_signal", ""
        )

        if (
            "long_entry" not in six_hour_type_last_true_signal
            and "short_exit" not in six_hour_type_last_true_signal
        ):
            return False

        one_hoour_analysis = await self.strategy.analyze_currency_by_turtle(
            order_currency=symbol,
            payment_currency="KRW",
            chart_intervals="1h",
        )
        one_hour_type_last_true_signal = one_hoour_analysis.get(
            "type_last_true_signal", ""
        )
        if (
            "long_entry" not in one_hour_type_last_true_signal
            and "short_exit" not in one_hour_type_last_true_signal
        ):
            return False

        return True

    async def calculate_score(self, symbol: str, chart_intervals: str = "1h") -> float:
        candlestick_data = await self.bithumb.get_candlestick_data(
            symbol, "KRW", chart_intervals
        )
        if candlestick_data["status"] != "0000":
            return 0  # 데이터가 유효하지 않은 경우 0점 반환

        close_prices = [
            float(candle[2]) for candle in candlestick_data["data"]
        ]  # 종가 리스트
        volume = sum(
            [float(candle[5]) for candle in candlestick_data["data"]]
        )  # 거래량 합계

        # RSI 계산
        rsi = await self.calculate_rsi(close_prices)

        # 가격 변화율 계산 (최근 종가 - 시가) / 시가
        opening_price = float(candlestick_data["data"][0][1])
        closing_price = close_prices[-1]
        price_change = abs(closing_price - opening_price) / opening_price

        # VWMA 계산
        vwma_df = await self.strategy.vwma(
            symbol, "KRW", length=20, chart_intervals=chart_intervals
        )
        vwma_value = vwma_df["VWMA"].iloc[-1]

        # VWMA와 현재 가격 비교
        above_vwma = closing_price > vwma_value

        # 각 요소에 가중치를 적용하여 점수 계산
        score = (
            self.weights["volume"] * volume
            + self.weights["rsi"] * (100 - rsi if rsi > 70 else rsi)
            + self.weights["price_change"] * price_change
            + self.weights["vwma"]
            * (1 if above_vwma else 0)  # VWMA 위에 있으면 가중치 추가
        )
        return score

    async def select_coin(self, symbols: Optional[List[str]] = None):
        candidate_symbols = []

        if symbols:
            candidate_symbols = symbols
        else:
            all_coins = await self.bithumb.get_current_price("KRW")
            filtered_by_value = await self.bithumb.filter_coins_by_value(all_coins, 100)
            candidate_symbols = filtered_by_value

        available_and_uptrend_symbols = [
            symbol
            for symbol in candidate_symbols
            if symbol not in self.active_symbols and await self.is_in_uptrend(symbol)
        ]

        coin_scores: Dict[str, float] = {}
        for symbol in available_and_uptrend_symbols:
            score = await self.calculate_score(symbol)
            coin_scores[symbol] = score

        sorted_symbols = sorted(
            coin_scores, key=lambda symbol: coin_scores[symbol], reverse=True
        )

        selected = sorted_symbols[:10] if len(sorted_symbols) >= 10 else sorted_symbols
        return selected

    async def add_active_symbols(self, symbols: Optional[List[str]] = Query(None)):
        if symbols:
            for symbol in symbols:
                if symbol not in self.active_symbols:
                    self.active_symbols.add(symbol)

    async def remove_active_symbols(self, symbols: Optional[List[str]] = Query(None)):
        if symbols:
            for symbol in symbols:
                if symbol in self.active_symbols:
                    self.active_symbols.remove(symbol)

    async def add_holding_coin(self, symbol: str, units: float, buy_price: float):
        stop_loss_price = buy_price * 0.98
        self.holding_coins[symbol] = {
            "units": units,
            "buy_price": buy_price,
            "stop_loss_price": stop_loss_price,
            "order_id": None,
        }

    async def remove_holding_coin(self, symbol: str):
        if symbol in self.holding_coins:
            self.holding_coins.pop(symbol)

    async def trade(self, symbol: str, timeframe: str = "1h"):
        await self.initialize_candlestick_data(symbol, timeframe)
        await self.connect_to_websocket(symbol, timeframe)

    async def connect_to_websocket(
        self,
        symbol: str,
        timeframe: str,
    ):
        async with websockets.connect("wss://pubwss.bithumb.com/pub/ws") as websocket:
            self.websocket_connections[symbol] = websocket
            subscribe_message = json.dumps(
                {
                    "type": "ticker",
                    "symbols": [f"{symbol.upper()}_KRW"],
                    "tickTypes": ["1H"],  # ["30M", "1H", "12H", "24H", "MID"],
                }
            )
            await websocket.send(subscribe_message)

            while symbol in self.active_symbols:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)
                    if "content" in data:
                        self.update_candlestick_data(symbol, data["content"])
                        await self.analyze_and_trade(symbol, timeframe)
                except websockets.ConnectionClosed as e:
                    logger.error("WebSocket connection closed: %s", e)
                    logger.error("Traceback: %s", traceback.format_exc())
                    break
                except Exception as e:
                    logger.error("An error occurred: %s", e)
                    logger.error("Traceback: %s", traceback.format_exc())
                await asyncio.sleep(1)

    async def disconnect(self, symbol):
        # WebSocket 연결 해제
        if symbol in self.websocket_connections:
            websocket = self.websocket_connections.pop(symbol)
            await websocket.close()

        if symbol in self.active_symbols:
            self.remove_active_symbols([symbol])

        if symbol in self.running_tasks:
            task = self.running_tasks.pop(symbol)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.info("Task for %s has been cancelled", symbol)

    def update_candlestick_data(self, symbol: str, content: dict):
        """
        실시간 데이터를 받아와서 캔들스틱 데이터를 업데이트
        content 데이터 예시:
        {
            'symbol': 'BTC_KRW',
            'tickType': '1M',
            'date': '20230519',
            'time': '123456',
            'openPrice': '50000',
            'closePrice': '51000',
            'lowPrice': '49500',
            'highPrice': '51500',
            'value': '0.1234'
        }
        """
        try:
            # 필요한 데이터 추출
            timestamp = datetime.strptime(
                content["date"] + content["time"], "%Y%m%d%H%M%S"
            )
            open_price = float(content["openPrice"])
            close_price = float(content["closePrice"])
            low_price = float(content["lowPrice"])
            high_price = float(content["highPrice"])
            volume = float(content["value"])

            # 타임프레임에 따라 기존 캔들 업데이트 또는 새로운 캔들 생성
            if symbol not in self.candlestick_data:
                self.candlestick_data[symbol] = pd.DataFrame(
                    columns=["timestamp", "open", "close", "high", "low", "volume"]
                )

            df = self.candlestick_data[symbol]

            # Ensure 'timestamp' is a datetime object
            if not df.empty:
                if df.index.name == "timestamp":
                    df = df.reset_index()  # 인덱스를 열로 변환
                if isinstance(df.iloc[-1]["timestamp"], str):
                    df["timestamp"] = pd.to_datetime(df["timestamp"])

            # 타임프레임에 맞춰 새로운 캔들을 생성
            if not df.empty and df.iloc[-1]["timestamp"] == timestamp:
                # 같은 분의 데이터는 마지막 캔들 업데이트
                df.at[df.index[-1], "close"] = close_price
                df.at[df.index[-1], "high"] = max(df.iloc[-1]["high"], high_price)
                df.at[df.index[-1], "low"] = min(df.iloc[-1]["low"], low_price)
                df.at[df.index[-1], "volume"] += volume
            else:
                # 새로운 캔들 생성
                new_candle = pd.DataFrame(
                    [
                        {
                            "timestamp": timestamp,
                            "open": open_price,
                            "close": close_price,
                            "high": high_price,
                            "low": low_price,
                            "volume": volume,
                        }
                    ]
                )
                self.candlestick_data[symbol] = pd.concat(
                    [df, new_candle], ignore_index=True
                )
        except Exception as e:
            logger.error("An error occurred while updating candlestick data: %s", e)
            logger.error("Traceback: %s", traceback.format_exc())

    async def analyze_and_trade(
        self,
        symbol: str,
        timeframe: str,
    ):
        try:
            current_time = datetime.now()
            match = re.match(r"(\d+)([a-zA-Z]+)", self.current_timeframe)
            if match:
                default_minutes = int(match.group(1))
            else:
                default_minutes = 10

            interval = self.timeframe_intervals.get(
                timeframe, timedelta(minutes=default_minutes)
            )

            df = self.candlestick_data[symbol]
            current_price = df.iloc[-1]["close"]
            is_stop_loss = await self.check_stop_loss_condition(symbol, current_price)
            profit_percentage = await self.get_profit_percentage(symbol, current_price)

            print("log=> analyze_and_trade: 진입", symbol, timeframe, interval)
            if (
                current_time - self.last_analysis_time[symbol] < interval
                and not is_stop_loss
            ):
                return

            print("log=> analyze_and_trade: 진행", symbol, timeframe, interval)

            self.last_analysis_time[symbol] = current_time

            print(
                "log=> Analyzing and trading %s on %s timeframe with holding coins: %s",
                symbol,
                timeframe,
                list(self.holding_coins.keys()),
            )

            if symbol in self.in_trading_process_coins:
                logger.info("Already in trading process: %s", symbol)
                return

            if symbol not in self.candlestick_data:
                logger.info("Symbol %s not found in candlestick data", symbol)
                return

            signal = await self.get_signal(symbol)
            latest_signal = signal["type_latest_signal"]

            # 거래량 가중 이평을 돌파하는지, 혹은 반대로 돌파하는지 확인
            # 거래량 가중 이평을 돌파하는 경우 매수 시그널
            # 거래량 가중 이평을 돌파하지 않는 경우 매도 시그널 -> 절반 매도.

            # 매수
            if await self.check_entry_condition(symbol, latest_signal):
                if symbol in self.holding_coins:
                    return  # 이미 보유한 코인인 경우 추가 매수하지 않음

                if len(self.holding_coins) >= 3:
                    return  # 이미 3개 이상의 코인을 보유하고 있으면 추가 매수하지 않음

                if symbol in self.in_trading_process_coins:
                    return  # 이미 매수 진행 중인 경우 추가 매수하지 않음

                self.in_trading_process_coins.append(symbol)

                buy_result = await self.execute_trade("buy", symbol)
                if buy_result and buy_result["status"] == "0000":
                    self.trading_history.setdefault(symbol, []).append(
                        {
                            "action": "buy",
                            "entry_signal": latest_signal,
                            "price": current_price,
                            "entry_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        }
                    )

                self.in_trading_process_coins.remove(symbol)
                return

            # 매도
            if await self.check_exit_condition(symbol, latest_signal) or is_stop_loss:
                if symbol not in self.holding_coins:
                    return  # 보유한 코인이 아닌 경우 매도하지 않음

                if symbol in self.in_trading_process_coins:
                    return  # 이미 매도 진행 중인 경우 추가 매도하지 않음

                self.in_trading_process_coins.append(symbol)

                sell_result = await self.execute_trade("sell", symbol)
                if sell_result and sell_result["status"] == "0000":
                    self.trading_history.setdefault(symbol, []).append(
                        {
                            "action": "sell",
                            "exit_signal": latest_signal,
                            "price": current_price,
                            "exit_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        }
                    )
                    await self.disconnect(symbol)

                self.in_trading_process_coins.remove(symbol)

                return

            # profit percentage 를 계속해서 history 쌓듯이 쌓다가, 최고치보다 일정 수준 떨어졌을 때도 매도하는거 추가해야겠다.
            if profit_percentage is not None and profit_percentage > 5:
                if symbol in self.in_trading_process_coins:
                    return  # 이미 매도 진행 중인 경우 추가 매도하지 않음

                self.in_trading_process_coins.append(symbol)
                if symbol in self.trading_history:
                    self.trading_history[symbol].append(
                        {
                            "action": "sell",
                            "exit_signal": latest_signal,
                            "price": current_price,
                            "exit_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        }
                    )
                else:
                    self.trading_history[symbol] = [
                        {
                            "action": "sell",
                            "exit_signal": latest_signal,
                            "price": current_price,
                            "exit_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        }
                    ]

                sell_by_profit = await self.execute_trade("sell", symbol, amount=0.5)
                if sell_by_profit and sell_by_profit["status"] == "0000":
                    # await self.disconnect(symbol)
                    pass  # 일단은 일정 물량만 매도만 하고, 종목을 제거하지 않음.

                self.in_trading_process_coins.remove(symbol)

                return

            # print("log=> Trading history: ", self.trading_history)
        except Exception as e:
            logger.error("An error occurred while analyzing and trading: %s", e)
            logger.error("Traceback: %s", traceback.format_exc())
            if symbol in self.in_trading_process_coins:
                self.in_trading_process_coins.remove(symbol)

    async def initialize_candlestick_data(self, symbol: str, timeframe: str):
        # 초기 캔들스틱 데이터를 조회하여 candlestick_data에 저장
        candlestick_data = await self.bithumb.get_candlestick_data(
            symbol, "KRW", timeframe
        )
        if candlestick_data["status"] == "0000":
            self.candlestick_data[symbol] = pd.DataFrame(
                candlestick_data["data"],
                columns=["timestamp", "open", "close", "high", "low", "volume"],
            )
            self.candlestick_data[symbol]["timestamp"] = pd.to_datetime(
                self.candlestick_data[symbol]["timestamp"], unit="ms"
            )
            self.candlestick_data[symbol].set_index("timestamp", inplace=True)
        # self.last_analysis_time[symbol] = datetime.now()
        self.last_analysis_time[symbol] = datetime.now() - self.timeframe_intervals.get(
            timeframe, timedelta(minutes=10)
        )

    async def reselect_and_trade(self):
        for symbol in list(self.running_tasks.keys()):
            if symbol not in self.holding_coins:
                await self.disconnect(symbol)

        # 선택된 코인들을 active_symbols 에 추가
        selected_coins = await self.select_coin()
        limit = 10
        slots_available = limit - len(self.active_symbols)
        self.active_symbols.update(selected_coins[:slots_available])
        self.active_symbols.update(self.interest_symbols)

        # trading 시작
        await send_telegram_message(
            f"🚀 Trading started with reselected symbols:\n\n{self.active_symbols} 🚀",
            term_type="short-term",
        )
        logger.info(
            "Running trading bot with reselected symbols: %s", self.active_symbols
        )

        tasks = []
        for symbol in self.active_symbols:
            task = asyncio.create_task(self.trade(symbol))
            self.running_tasks[symbol] = task
            tasks.append(task)

        await asyncio.gather(*tasks)

    async def run(self, symbols: Optional[List[str]] = None, timeframe: str = "1h"):
        # 선택된 코인들을 active_symbols 에 추가
        selected_coins = await self.select_coin()
        limit = 10
        slots_available = limit - len(self.active_symbols)
        self.active_symbols.update(selected_coins[:slots_available])

        # 관심 종목 업데이트
        if symbols:
            self.interest_symbols.update(symbols)

        # 관심 종목을 active_symbols 에 추가
        self.active_symbols.update(self.interest_symbols)

        # trading 시작
        await send_telegram_message(
            f"🚀 Trading started with symbols:\n\n{self.active_symbols}\n\nand\n\ntimeframe: {timeframe} 🚀",
            term_type="short-term",
        )
        logger.info(
            "Running trading bot with symbols: %s and timeframe: %s",
            self.active_symbols,
            timeframe,
        )

        tasks = []
        for symbol in self.active_symbols:
            task = asyncio.create_task(self.trade(symbol, timeframe))
            self.running_tasks[symbol] = task
            tasks.append(task)

        await asyncio.gather(*tasks)

    async def stop_all(self):
        for symbol in list(self.running_tasks.keys()):
            await self.disconnect(symbol)
        self.running_tasks.clear()
        self.active_symbols.clear()

    async def stop_symbol(self, symbol: str):
        if symbol in self.running_tasks:
            await self.disconnect(symbol)
            self.running_tasks.pop(symbol)
            self.active_symbols.remove(symbol)

    def get_status(self):
        return {
            "active_symbols": list(self.active_symbols),
            "holding_coins": self.holding_coins,
            "available_krw_to_each_trade": self.available_krw_to_each_trade,
            "in_trading_process_coins": self.in_trading_process_coins,
            "running_tasks": list(self.running_tasks.keys()),
            "websocket_connections": list(self.websocket_connections.keys()),
            "interest_symbols": list(self.interest_symbols),
            "trading_history": self.trading_history,
        }


# trading history 에 best profit 을 추가해서, best profit 이후에 일정 수준 떨어지면 일정 물량 매도하는 로직 추가.
