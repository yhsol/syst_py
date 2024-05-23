import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import pandas as pd
import websockets

from app.services.bithumb_service import BithumbPrivateService, BithumbService
from app.services.stratege_service import StrategyService

import logging

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
        self.in_trading_process_coins: List = []

    async def handle_trade(self, symbol, signal):
        if await self.check_entry_condition(signal):
            await self.execute_trade("buy", symbol)
        elif await self.check_exit_condition(signal):
            await self.execute_trade("sell", symbol)
            await self.disconnect(symbol)

    async def check_entry_condition(self, signal):
        if ("short_exit" in signal) or ("long_entry" in signal):
            return True
        return False

    async def check_exit_condition(self, signal):
        if ("long_exit" in signal) or ("short_entry" in signal):
            return True
        return False

    async def get_available_buy_units(self, symbol):
        # 주문 가능 수량 조회
        balance = await self.bithumb_private.get_balance(symbol)
        available_krw = balance["data"]["available_krw"]

        # 매수 가능 금액을 10000원으로 제한
        available_krw = 8000

        # 매수 금액을 어떻게 정할지는 좀 더 고민해봐야할 듯.
        # available_krw 의 몇 % 로 할 수도 있고.
        # 특정 금액을 기준으로 할 수도 있고.
        # 자산관리 전략에 따라 조정할 수 있도록 해야할 듯.

        orderbook = await self.bithumb.get_orderbook(symbol)
        ask_price = orderbook["data"]["asks"][0]["price"]

        # 수수료 0.28% 라고 가정. 정화하지 않긴 한데, bithumb page 에서 책정하는게 정확히 어떤건지 알 수 없어서 안전한 수량으로 계산
        fee = 0.0028
        units = float(available_krw) / float(ask_price) * (1 - fee)

        return units

    async def get_available_sell_units(self, symbol):
        # 주문 가능 수량 조회
        balance = await self.bithumb_private.get_balance(symbol)
        coin_balance = balance["data"][f"available_{symbol.lower()}"]

        return coin_balance

    async def execute_trade(self, action, symbol):
        # 매수 또는 매도 주문 실행
        logger.info("Executing start %s on %s", action, symbol)
        try:
            if action == "buy":
                # 매수 주문 실행
                buy_units = await self.get_available_buy_units(symbol)
                logger.info("Available buy units: %f", buy_units)

                # 전체 unit 의 70% 만큼만 매수. bithumb 에서 제한하는 듯?
                # https://github.com/sharebook-kr/pybithumb/issues/26
                # 소수점 8자리까지만 가능
                # 그런데 전체 자산의 70% 이상을 매수할 일은 없을 확률이 높으니 고려하지 않아도 될 듯.
                # available_units = round(buy_units * 0.7, 8)

                available_units = round(buy_units, 8)
                logger.info("Available units: %f", available_units)

                result = await self.bithumb_private.market_buy(
                    units=available_units,
                    order_currency=symbol,
                    payment_currency="KRW",
                )
                logger.info("Buy result: %s", result)

                # 매수 주문이 성공하면 매수한 코인을 holding_coins 에 추가
                # result 에 order_id 가 있으면 주문이 성공한 것으로 간주
                # holding_coins 에는 매수한 코인의 정보를 저장. order_id 도 추가.
                if result and result["status"] == "0000" and "order_id" in result:
                    order_detail = await self.bithumb_private.get_order_detail(
                        order_id=result["order_id"],
                        order_currency=symbol,
                        payment_currency="KRW",
                    )
                    logger.info("Order detail: %s", order_detail)

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
                            logger.info(
                                "Buy Success and Holding coins: %s", self.holding_coins
                            )
                        else:
                            logger.error(
                                "No contract information available for order_id: %s",
                                result["order_id"],
                            )
                    else:
                        logger.error(
                            "Failed to retrieve order details for order_id: %s",
                            result["order_id"],
                        )

                return result

            if action == "sell":
                # 매도 주문 실행
                sell_units = await self.get_available_sell_units(symbol)
                result = await self.bithumb_private.market_sell(
                    units=sell_units,
                    order_currency=symbol,
                    payment_currency="KRW",
                )
                logger.info("Sell result: %s", result)

                # 매도 주문이 성공하면 holding_coins 에서 해당 코인 제거
                if result and result["status"] == "0000":
                    self.holding_coins.pop(symbol)
                    logger.info(
                        "Sell Success and Holding coins: %s", self.holding_coins
                    )
                return result
        except Exception as e:
            logger.error(
                "An error occurred while executing %s on %s: %s", action, symbol, e
            )

        logger.info("Executing done %s on %s", action, symbol)

    async def connect(self, symbol):
        logger.info("Add Active Symbols: %s", symbol)
        self.active_symbols.add(symbol)

    async def disconnect(self, symbol):
        # WebSocket 연결 해제
        logger.info("Remove Active Symbols: %s", symbol)
        self.active_symbols.remove(symbol)

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
            logger.info("Selecting coins in all coins...")
            all_coins = await self.bithumb.get_current_price("KRW")
            filtered_by_value = await self.bithumb.filter_coins_by_value(all_coins, 100)
            candidate_symbols = filtered_by_value

        logger.info("Check is in uptrend: %s", candidate_symbols)
        available_and_uptrend_symbols = [
            symbol
            for symbol in candidate_symbols
            if symbol not in self.active_symbols and await self.is_in_uptrend(symbol)
        ]

        logger.info("Calculate score: %s", available_and_uptrend_symbols)
        coin_scores: Dict[str, float] = {}
        for symbol in available_and_uptrend_symbols:
            score = await self.calculate_score(symbol)
            coin_scores[symbol] = score

        sorted_symbols = sorted(
            coin_scores, key=lambda symbol: coin_scores[symbol], reverse=True
        )

        selected = sorted_symbols[:10] if len(sorted_symbols) >= 10 else sorted_symbols
        logger.info("Selected coins: %s", selected)
        return selected

    async def trade(self, symbol: str, timeframe: str = "1h"):
        logger.info("Trading %s on %s timeframe", symbol, timeframe)
        await self.initialize_candlestick_data(symbol, timeframe)
        await self.subscribe_to_websocket(symbol, timeframe)

    async def subscribe_to_websocket(
        self,
        symbol: str,
        timeframe: str,
    ):
        logger.info(
            "Subscribing to WebSocket for %s_KRW on %s timeframe",
            symbol.upper(),
            timeframe,
        )
        async with websockets.connect("wss://pubwss.bithumb.com/pub/ws") as websocket:
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
                    logger.info("Received message from socket: %s", data)
                    if "content" in data:
                        self.update_candlestick_data(symbol, data["content"])
                        await self.analyze_and_trade(symbol, timeframe)
                except websockets.ConnectionClosed as e:
                    logger.error("WebSocket connection closed: %s", e)
                    break
                except Exception as e:
                    logger.error("An error occurred: %s", e)
                await asyncio.sleep(1)

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
            logger.info("Updating candlestick data for %s", symbol)
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
                logger.info("Last timestamp in DataFrame: %s", df.iloc[-1]["timestamp"])
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

    async def analyze_and_trade(
        self,
        symbol: str,
        timeframe: str,
    ):
        try:
            logger.info("Analyzing and trading %s on %s timeframe", symbol, timeframe)

            if symbol in self.in_trading_process_coins:
                logger.info("Already in trading process: %s", symbol)
                return

            if symbol not in self.candlestick_data:
                logger.info("Symbol %s not found in candlestick data", symbol)
                return

            df = self.candlestick_data[symbol]
            signals = self.strategy.compute_signals(df)
            signal_columns = ["long_entry", "short_entry", "long_exit", "short_exit"]

            filtered_signals = signals[["timestamp"] + signal_columns]
            filtered_signals = filtered_signals.sort_values(
                by="timestamp", ascending=False
            )

            signal_status = self.strategy.determine_signal_status(
                filtered_signals, signal_columns
            )

            signal = {
                "ticker": symbol,
                "status": "success",
                "type_latest_signal": signal_status["latest"],
                "type_last_true_signal": signal_status["last_true"],
                "type_last_true_timestamp": signal_status["last_true_timestamp"],
                "data": filtered_signals.head(20).to_dict(orient="records"),
            }

            latest_signal = signal["type_latest_signal"]

            average_buy_price = (
                self.holding_coins[symbol]["buy_price"]
                if symbol in self.holding_coins
                else None
            )
            stop_loss_price = (
                self.holding_coins[symbol]["stop_loss_price"]
                if symbol in self.holding_coins
                else None
            )

            logger.info("log=> Current symbols: %s", symbol)
            logger.info(
                "log=> Latest signal for %s: %s",
                symbol,
                (
                    "💡 detected" + latest_signal
                    if latest_signal != "No active signal."
                    else latest_signal
                ),
            )
            logger.info("log=> Active symbols: %s", self.active_symbols)
            logger.info("log=> Holding coins: %s", self.holding_coins)
            logger.info("log=> Average buy price: %s", average_buy_price)
            logger.info("log=> Stop loss price: %s", stop_loss_price)

            if (
                len(self.holding_coins) < 2
                and symbol not in self.holding_coins
                and await self.check_entry_condition(latest_signal)
            ):
                self.in_trading_process_coins.append(symbol)
                result = await self.execute_trade("buy", symbol)
                if result and result["status"] == "0000":
                    buy_price = float(result["data"]["price"])
                    buy_units = float(result["data"]["units"])
                    if average_buy_price is None:
                        average_buy_price = buy_price
                    else:
                        average_buy_price = (
                            average_buy_price * buy_units + buy_price * buy_units
                        ) / (buy_units + buy_units)
                    stop_loss_price = average_buy_price * 0.98  # -2% 손절가
                self.in_trading_process_coins.remove(symbol)

            elif (
                symbol in self.holding_coins
                and await self.check_exit_condition(latest_signal)
                or (
                    average_buy_price is not None
                    and latest_signal["close"] < stop_loss_price
                )
            ):
                self.in_trading_process_coins.append(symbol)
                await self.execute_trade("sell", symbol)
                await self.disconnect(symbol)
                self.in_trading_process_coins.remove(symbol)
        except Exception as e:
            logger.error("An error occurred while analyzing and trading: %s", e)
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

    async def run(self, symbols: Optional[List[str]] = None, timeframe: str = "1h"):
        logger.info(
            "Running trading bot with symbols: %s and timeframe: %s", symbols, timeframe
        )

        trade_symbols = []

        if symbols:
            trade_symbols = symbols
        else:
            selected_coins = await self.select_coin()
            trade_symbols = selected_coins

        # trade_symbols 에 stx 가 있으면 제거.
        if "STX" in trade_symbols:
            trade_symbols.remove("STX")

        # active_symbols 에 trade_symbols 를 추가하고, 길이는 2개로 제한
        new_symbols = [
            symbol for symbol in trade_symbols if symbol not in self.active_symbols
        ]
        slots_available = 10 - len(self.active_symbols)
        logger.info("New symbols: %s", new_symbols[:slots_available])
        self.active_symbols.update(new_symbols[:slots_available])

        logger.info("Updated active symbols: %s", self.active_symbols)
        # self.active_symbols.update(trade_symbols)
        # self.active_symbols = set(list(self.active_symbols)[:10])

        # trade_symbols 에 대해 trade 실행
        # for symbol in trade_symbols:
        #     await self.trade(symbol, timeframe)
        tasks = [self.trade(symbol, timeframe) for symbol in trade_symbols]
        await asyncio.gather(*tasks)
