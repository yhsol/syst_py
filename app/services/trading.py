import asyncio
import json
import logging
import re
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, TypedDict

from fastapi import Query
import pandas as pd
import websockets

from app.services.bithumb_service import BithumbPrivateService, BithumbService
from app.services.stratege_service import StrategyService
from app.telegram.telegram_client import send_telegram_message
from app.utils.trading_helpers import (
    calculate_atr,
    calculate_moving_average,
    calculate_previous_day_price_change,
    calculate_rsi,
    calculate_volume_growth_rate,
    check_entry_condition,
    check_exit_condition,
    check_stop_loss_condition,
    get_profit_percentage,
)

# Logging 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("trading_bot.log"), logging.StreamHandler()],
)

logger = logging.getLogger(__name__)


class HoldingCoin(TypedDict):
    units: Optional[float]
    buy_price: Optional[float]
    stop_loss_price: Optional[float]
    order_id: Optional[str]
    profit: Optional[float]
    reason: Optional[str]
    highest_price: Optional[float]
    trailing_stop_price: Optional[float]  # 트레일링 스탑 가격


class TradingBot:
    def __init__(
        self,
        bithumb_service: BithumbService,
        bithumb_private_service: BithumbPrivateService,
        strategy_service: StrategyService,
    ):
        print("Trading Service initialized")
        self.bithumb = bithumb_service
        self.bithumb_private = bithumb_private_service
        self.strategy = strategy_service
        self.websocket_connections: Dict[str, websockets.WebSocketClientProtocol] = {}
        self.interest_symbols: Set[str] = set()
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.active_symbols: Set[str] = set()
        self.holding_coins: Dict[str, HoldingCoin] = {}
        self.in_trading_process_coins: List = []
        self.trading_history: Dict = {}
        self.candlestick_data: Dict = {}  # 캔들스틱 데이터를 저장할 딕셔너리
        self.available_krw_to_each_trade: float = 10000
        self.profit_target = {"profit": 5, "amount": 0.5}
        self.trailing_stop_percent = 0.02  # 예: 2% 트레일링 스탑
        self.trailing_stop_amount = 0.5  # 이익 실현 시 매도할 양
        self.current_timeframe = "10m"
        self.last_analysis_time: Dict[str, datetime] = {}
        self.weights = {
            "volume": 0.2,  # 거래량
            "rsi": 0.15,  # 상대 강도 지수
            "price_change": 0.15,  # 가격 변화율
            "vwma": 0.2,  # 거래량 가중 이동 평균
            "atr": 0.1,  # 평균 진폭 범위
            "previous_day_price_change": 0.1,  # 전일 가격 변화
            "moving_average": 0.1,  # 이동 평균
            "volume_growth_rate": 0.1,  # 거래량 증가율
        }
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

    def get_status(self):
        return {
            "available_krw_to_each_trade": self.available_krw_to_each_trade,
            "current_timeframe": self.current_timeframe,
            "profit_target": self.profit_target,
            "running_tasks": list(self.running_tasks.keys()),
            "active_symbols": list(self.active_symbols),
            "holding_coins": self.holding_coins,
            "in_trading_process_coins": self.in_trading_process_coins,
            "websocket_connections": list(self.websocket_connections.keys()),
            "interest_symbols": list(self.interest_symbols),
            "trading_history": self.trading_history,
        }

    async def get_signal(self, symbol):
        if symbol not in self.candlestick_data:
            return None

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

    def set_timeframe(self, timeframe: str):
        self.current_timeframe = timeframe

    def set_trailing_stop_percent(self, percent: float):
        self.trailing_stop_percent = percent
        return {"status": f"Trailing stop percent set to {percent*100}%"}

    def set_trailing_stop_amount(self, amount: float):
        self.trailing_stop_amount = amount
        return {"status": f"Trailing stop amount set to {amount}"}

    async def set_trailing_stop(self, symbol: str, percent: float):
        self.trailing_stop_percent = percent
        if symbol in self.holding_coins:
            buy_price = self.holding_coins[symbol]["buy_price"] or 0

            self.holding_coins[symbol]["highest_price"] = buy_price
            self.holding_coins[symbol]["trailing_stop_price"] = buy_price * (
                1 - percent
            )
        return {"status": f"Trailing stop set to {percent*100}% for {symbol}"}

    async def update_trailing_stop(self, symbol: str, current_price: float):
        if symbol in self.holding_coins:
            highest_price = self.holding_coins[symbol].get("highest_price", 0) or 0

            if current_price > highest_price:
                self.holding_coins[symbol]["highest_price"] = current_price
                self.holding_coins[symbol]["trailing_stop_price"] = current_price * (
                    1 - self.trailing_stop_percent
                )
                return

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
        rsi = await calculate_rsi(close_prices)

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

        # ATR 계산
        atr = await calculate_atr(candlestick_data["data"])

        # 전일 상승폭 계산
        previous_day_price_change = await calculate_previous_day_price_change(
            candlestick_data["data"]
        )

        # MA 계산
        moving_average = await calculate_moving_average(close_prices, period=20)

        # 트레이딩 볼륨 증가율 계산
        volume_growth_rate = await calculate_volume_growth_rate(
            candlestick_data["data"]
        )

        # 각 요소에 가중치를 적용하여 점수 계산
        score = (
            self.weights["volume"] * volume
            + self.weights["rsi"] * (100 - rsi if rsi > 70 else rsi)
            + self.weights["price_change"] * price_change
            + self.weights["vwma"]
            * (1 if above_vwma else 0)  # VWMA 위에 있으면 가중치 추가
            + self.weights["atr"] * atr  # ATR에 대한 가중치 추가
            + self.weights["previous_day_price_change"]
            * previous_day_price_change  # 전일 상승폭에 대한 가중치 추가
            + self.weights["moving_average"]
            * moving_average  # 이동 평균에 대한 가중치 추가
            + self.weights["volume_growth_rate"]
            * volume_growth_rate  # 거래량 증가율에 대한 가중치 추가
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
            "profit": 0,
            "reason": "add by user",
            "highest_price": buy_price,
            "trailing_stop_price": buy_price * (1 - self.trailing_stop_percent),
        }

    async def remove_holding_coin(self, symbol: str):
        if symbol in self.holding_coins:
            self.holding_coins.pop(symbol)

    async def set_profit_target(
        self, profit: Optional[float] = 5, amount: Optional[float] = 0.5
    ):
        self.profit_target = {
            "profit": profit if profit else self.profit_target.get("profit", 5),
            "amount": amount if amount else self.profit_target.get("amount", 0.5),
        }

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

    async def buy(self, symbol, reason=""):
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
                            "reason": reason,
                            "buy_price": buy_price,
                            "stop_loss_price": stop_loss_price,
                            "order_id": result["order_id"],
                            "profit": 0,
                            "highest_price": buy_price,
                            "trailing_stop_price": buy_price
                            * (1 - self.trailing_stop_percent),
                        }

                        if symbol not in self.active_symbols:
                            await self.add_active_symbols([symbol])

                        # 매수 체결 메시지
                        await send_telegram_message(
                            (
                                f"🟢 {symbol} 매수 체결! 🟢\n\n"
                                f"📝 Reason: {reason}\n\n"
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

    async def sell(self, symbol, amount=1.0, reason=""):
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
                                f"📝 Reason: {reason}\n\n"
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

    async def execute_trade(self, action, symbol, amount=1.0, reason=""):
        try:
            if action == "buy":
                # 매수 주문 실행
                result = await self.buy(symbol, reason=reason)
                return result

            if action == "sell":
                # 매도 주문 실행
                result = await self.sell(symbol, amount, reason=reason)
                return result

        except Exception as e:
            logger.error(
                "An error occurred while executing %s on %s: %s", action, symbol, e
            )
            logger.error("Traceback: %s", traceback.format_exc())
            return {"status": "error", "message": str(e)}

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
            await self.remove_active_symbols([symbol])

        if symbol in self.running_tasks:
            task = self.running_tasks.pop(symbol)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.info("Task for %s has been cancelled", symbol)

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

    async def analyze_and_trade_by_immediate(self, symbol: str, current_price: float):
        if symbol not in self.holding_coins:
            return

        logger.info("Analyzing and trading for %s by immediate", symbol)

        profit_percentage = await get_profit_percentage(
            symbol, current_price, self.holding_coins
        )

        # update data
        self.holding_coins[symbol]["profit"] = profit_percentage
        await self.update_trailing_stop(symbol, current_price)

        # 트레일링 스탑 가격 도달 시 매도
        trailing_stop_price = self.holding_coins[symbol].get("trailing_stop_price") or 0
        is_trailing_stop_condition_met = (
            current_price <= trailing_stop_price
            and profit_percentage > 1  # 이익이 1% 미만이라면 매도하지 않고 기다림.
        )
        is_stop_loss_condition_met = await check_stop_loss_condition(
            symbol, current_price, self.holding_coins
        )
        is_profit_target_condition_met = profit_percentage > self.profit_target.get(
            "profit", 5
        )

        if is_trailing_stop_condition_met:
            if symbol in self.in_trading_process_coins:
                return  # 이미 매도 진행 중인 경우 추가 매도하지 않음

            self.in_trading_process_coins.append(symbol)

            sell_result = await self.execute_trade(
                "sell", symbol, amount=self.trailing_stop_amount, reason="trailing_stop"
            )
            if sell_result and sell_result["status"] == "0000":
                self.trading_history.setdefault(symbol, []).append(
                    {
                        "action": "sell",
                        "reason": "trailing_stop_condition_met",
                        "exit_signal": "reach_trailing_stop",
                        "price": current_price,
                        "exit_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )
                await self.disconnect(symbol)

            self.in_trading_process_coins.remove(symbol)

            return

        # 손절가 도달 시 매도
        if is_stop_loss_condition_met:
            if symbol in self.in_trading_process_coins:
                return  # 이미 매도 진행 중인 경우 추가 매도하지 않음

            self.in_trading_process_coins.append(symbol)

            sell_result = await self.execute_trade("sell", symbol, reason="stop_loss")
            if sell_result and sell_result["status"] == "0000":
                self.trading_history.setdefault(symbol, []).append(
                    {
                        "action": "sell",
                        "reason": "stop_loss_condition_met",
                        "exit_signal": "reach_stop_loss",
                        "price": current_price,
                        "exit_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )
                await self.disconnect(symbol)

            self.in_trading_process_coins.remove(symbol)

            return

        # 이익률에 따른 매도
        # profit percentage 를 계속해서 history 쌓듯이 쌓다가, 최고치보다 일정 수준 떨어졌을 때도 매도하는거 추가해야겠다.
        if is_profit_target_condition_met:
            if symbol in self.in_trading_process_coins:
                return  # 이미 매도 진행 중인 경우 추가 매도하지 않음

            self.in_trading_process_coins.append(symbol)

            sell_by_profit = await self.execute_trade(
                "sell",
                symbol,
                amount=self.profit_target.get("amount", 0.5),
                reason="profit_target",
            )
            if sell_by_profit and sell_by_profit["status"] == "0000":
                self.trading_history.setdefault(symbol, []).append(
                    {
                        "action": "sell",
                        "reason": "profit_target_condition_met",
                        "exit_signal": "reach_profit",
                        "price": current_price,
                        "exit_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )

            self.in_trading_process_coins.remove(symbol)

            return

    async def analyze_and_trade_by_interval(
        self, symbol: str, timeframe: str, current_price: float
    ):
        current_time = datetime.now()
        interval = self.timeframe_intervals.get(timeframe, timedelta(minutes=10))

        # 일정 시간 간격으로 분석을 진행하기 위한 로직
        if current_time - self.last_analysis_time[symbol] < interval:
            return

        self.last_analysis_time[symbol] = current_time
        signal = await self.get_signal(symbol)

        if signal is None:
            return

        latest_signal = signal["type_latest_signal"]

        logger.info("Latest signal for %s: %s", symbol, latest_signal)

        if await check_entry_condition(symbol, latest_signal, self.trading_history):
            if symbol in self.holding_coins:
                return  # 이미 보유한 코인인 경우 추가 매수하지 않음

            if len(self.holding_coins) >= 3:
                return  # 이미 3개 이상의 코인을 보유하고 있으면 추가 매수하지 않음

            if symbol in self.in_trading_process_coins:
                return

            self.in_trading_process_coins.append(symbol)

            buy_result = await self.execute_trade(
                "buy", symbol, reason="entry_signal_condition_met"
            )
            if buy_result and buy_result["status"] == "0000":
                self.trading_history.setdefault(symbol, []).append(
                    {
                        "action": "buy",
                        "reason": "entry_signal_condition_met",
                        "entry_signal": latest_signal,
                        "price": current_price,
                        "entry_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )

            self.in_trading_process_coins.remove(symbol)
            return

        if await check_exit_condition(symbol, latest_signal, self.trading_history):
            if symbol not in self.holding_coins:
                return

            if symbol in self.in_trading_process_coins:
                return

            self.in_trading_process_coins.append(symbol)

            sell_result = await self.execute_trade(
                "sell", symbol, reason="exit_signal_condition_met"
            )
            if sell_result and sell_result["status"] == "0000":
                self.trading_history.setdefault(symbol, []).append(
                    {
                        "action": "sell",
                        "reason": "exit_signal_condition_met",
                        "exit_signal": latest_signal,
                        "price": current_price,
                        "exit_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )
                await self.disconnect(symbol)

            self.in_trading_process_coins.remove(symbol)
            return

    async def analyze_and_trade(
        self,
        symbol: str,
        timeframe: str,
    ):
        try:
            df = self.candlestick_data[symbol]
            current_price = df.iloc[-1]["close"]

            await self.analyze_and_trade_by_immediate(symbol, current_price)
            await self.analyze_and_trade_by_interval(symbol, timeframe, current_price)
        except Exception as e:
            logger.error("An error occurred while analyzing and trading: %s", e)
            logger.error("Traceback: %s", traceback.format_exc())
            if symbol in self.in_trading_process_coins:
                self.in_trading_process_coins.remove(symbol)

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

    async def trade(self, symbol: str, timeframe: str = "1h"):
        await self.initialize_candlestick_data(symbol, timeframe)
        await self.connect_to_websocket(symbol, timeframe)

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

    async def run(self, symbols: Optional[List[str]] = None, timeframe: str = "1h"):
        # 선택된 코인들을 active_symbols 에 추가
        selected_coins = await self.select_coin()
        limit = 10
        slots_available = limit - len(self.active_symbols)
        self.active_symbols.update(selected_coins[:slots_available])
        self.set_timeframe(timeframe)

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


# trading history 에 best profit 을 추가해서, best profit 이후에 일정 수준 떨어지면 일정 물량 매도하는 로직 추가.
