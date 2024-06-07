import asyncio
import json
import logging
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, TypedDict
from collections import defaultdict

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
    split_sell_count: Optional[int]  # 매도 횟수


Reason = {
    "entrySignalConditionMet": "entrySignalConditionMet",
    "eixtSignalConditionMet": "eixtSignalConditionMet",
    "trailingStop": "trailingStop",
    "stopLoss": "stopLoss",
    "profitTarget": "profitTarget",
}


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

        self._running = False
        self.websocket_connections: Dict[str, websockets.WebSocketClientProtocol] = {}
        self.interest_symbols: Set[str] = set()
        self.holding_coins: defaultdict[str, HoldingCoin] = defaultdict(
            lambda: {
                "units": 0.0,
                "buy_price": 0.0,
                "stop_loss_price": 0.0,
                "order_id": "",
                "profit": 0.0,
                "reason": "",
                "highest_price": 0.0,
                "trailing_stop_price": 0.0,
                "split_sell_count": 0,
            }
        )
        self.in_trading_process_coins: List = []
        self.in_analysis_process_coins: List = []
        self.trading_history: Dict = {}
        self.candlestick_data: Dict = {}  # 캔들스틱 데이터를 저장할 딕셔너리
        self.available_krw_to_each_trade: float = 10000
        self.profit_target = {"profit": 10, "amount": 0.5}
        self.trailing_stop_percent = 0.02  # 예: 2% 트레일링 스탑
        self.trailing_stop_amount = float(1)  # 이익 실현 시 매도할 양
        self.current_timeframe = "30m"
        self.last_analysis_time: Dict[str, datetime] = {}
        self.weights = {
            "volume": 0.2,  # 거래량
            "rsi": 0.15,  # 상대 강도 지수
            "price_change": 0.15,  # 가격 변화율
            "vwma": 0.2,  # 거래량 가중 이동 평균
            "atr": 0.2,  # 평균 진폭 범위
            "previous_day_price_change": 0.2,  # 전일 가격 변화
            "moving_average": 0.1,  # 이동 평균
            "volume_growth_rate": 0.2,  # 거래량 증가율
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
        self.trade_coin_limmit = 20
        self.holding_coin_limmit = 5
        # uptrend 를 판단하기 위한 timeframes
        self.timeframes_for_check_uptrend = ["1h", "6h", "24h"]
        self.available_split_sell_count = 1

    def get_status(self):
        return {
            "available_krw_to_each_trade": self.available_krw_to_each_trade,
            "current_timeframe": self.current_timeframe,
            "profit_target": self.profit_target,
            "holding_coins": self.holding_coins,
            "in_trading_process_coins": self.in_trading_process_coins,
            "websocket_connections": list(self.websocket_connections.keys()),
            "interest_symbols": list(self.interest_symbols),
            "trading_history": self.trading_history,
        }

    def set_trade_coin_limit(self, limmit: int):
        self.trade_coin_limmit = limmit
        return {"status": f"Trade coin limmit set to {limmit}"}

    def set_timeframe(self, timeframe: str):
        self.current_timeframe = timeframe

    def set_trailing_stop_percent(self, percent: float):
        self.trailing_stop_percent = percent
        return {"status": f"Trailing stop percent set to {percent*100}%"}

    def set_trailing_stop_amount(self, amount: float):
        self.trailing_stop_amount = amount
        return {"status": f"Trailing stop amount set to {amount}"}

    def set_available_split_sell_count(self, count: int):
        self.available_split_sell_count = count
        return {"status": f"Available split sell count set to {count}"}

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
            highest_price = self.holding_coins[symbol]["highest_price"]

            if highest_price is not None and current_price > highest_price:
                self.holding_coins[symbol]["highest_price"] = current_price
                self.holding_coins[symbol]["trailing_stop_price"] = current_price * (
                    1 - self.trailing_stop_percent
                )
                return

    async def is_in_uptrend(self, symbol: str) -> bool:
        for timeframe in self.timeframes_for_check_uptrend:
            logger.info("Check uptrend for %s with %s", symbol, timeframe)
            analysis = await self.strategy.analyze_currency_by_turtle(
                order_currency=symbol,
                payment_currency="KRW",
                chart_intervals=timeframe,
            )
            last_true_signal = analysis.get("type_last_true_signal", "")
            if (
                "long_entry" not in last_true_signal
                and "short_exit" not in last_true_signal
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
            symbol for symbol in candidate_symbols if await self.is_in_uptrend(symbol)
        ]

        coin_scores: Dict[str, float] = {}
        for symbol in available_and_uptrend_symbols:
            score = await self.calculate_score(symbol)
            coin_scores[symbol] = score

        sorted_symbols = sorted(
            coin_scores, key=lambda symbol: coin_scores[symbol], reverse=True
        )

        return sorted_symbols

    async def add_holding_coin(
        self, symbol: str, units: float, buy_price: float, split_sell_count: int = 0
    ):
        stop_loss_price = buy_price * 0.98
        self.holding_coins[symbol] = {
            "units": units,
            "buy_price": buy_price,
            "stop_loss_price": stop_loss_price,
            "order_id": None,
            "profit": 0,
            "reason": "addByUser",
            "highest_price": buy_price,
            "trailing_stop_price": buy_price * (1 - self.trailing_stop_percent),
            "split_sell_count": split_sell_count,
        }

    async def remove_holding_coin(self, symbol: str):
        if symbol in self.holding_coins:
            self.holding_coins.pop(symbol)
            logger.info("Remove holding coin: %s", symbol)
            return {
                "status": f"Successfully removed {symbol} from holding coins and current holding coins: {list(self.holding_coins.keys())}"
            }
        return {"status": f"{symbol} is not in holding coins"}

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
        logger.info("Execute to buy %s by %s", symbol, reason)

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
                self.holding_coins[symbol] = {
                    "units": available_units,
                    "reason": reason,
                    "buy_price": 0,
                    "stop_loss_price": 0,
                    "order_id": result["order_id"],
                    "profit": 0,
                    "highest_price": 0,
                    "trailing_stop_price": 0,
                }

                # 매수 체결 메시지
                await send_telegram_message(
                    (f"🟢 {symbol} 매수 체결! 🟢\n\n" f"📝 Reason: {reason}\n\n"),
                    term_type="short-term",
                )
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

                        # 비동기적으로 소켓 연결
                        asyncio.create_task(self.connect_to_websocket(symbol))
                        # 매수 체결 상세 메시지
                        await send_telegram_message(
                            (
                                f"🟢 {symbol} 매수 체결 상세! 🟢\n\n"
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
            logger.info("Execute to sell %s by %s", symbol, reason)
            immediate_sell_reasons = [
                Reason["stopLoss"],
                Reason["eixtSignalConditionMet"],
            ]
            split_sell_count = self.holding_coins[symbol].get("split_sell_count", 0)
            if (
                reason not in immediate_sell_reasons
            ) and split_sell_count > self.available_split_sell_count:
                return {
                    "status": "passed",
                    "message": f"Split sell count is over the limit: {split_sell_count}",
                }

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
                buy_price = self.holding_coins[symbol]["buy_price"]

                if amount < 1.0:
                    self.holding_coins[symbol]["split_sell_count"] += 1

                if amount >= 1.0:
                    logger.info("Remove holding coin while sell: %s", symbol)
                    await self.remove_holding_coin(symbol)
                    await self.disconnect_to_websocket(symbol)

                await send_telegram_message(
                    (f"🔴 {symbol} 매도 체결! 🔴\n\n" f"📝 Reason: {reason}\n\n"),
                    term_type="short-term",
                )

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
                        if current_price and buy_price:
                            profit_percentage = (
                                (current_price - buy_price) / buy_price * 100
                            )
                        else:
                            profit_percentage = 0

                        await send_telegram_message(
                            (
                                f"🔴 {symbol} 매도 체결 상세! 🔴\n\n"
                                f"📝 Reason: {reason}\n\n"
                                f"💰 매도 가격: {current_price}\n\n"
                                f"📈 수익: {profit_percentage}\n\n"
                                f"📊 Holding coins: {list(self.holding_coins.keys())}\n\n"
                            ),
                            term_type="short-term",
                        )

                logger.info("Sell Success and Holding coins: %s", self.holding_coins)

            return {
                "status": "0000",
                "message": f"Successfully sold {sell_units} {symbol}",
            }
        except Exception as e:
            logger.error("An error occurred while selling %s: %s", symbol, e)
            logger.error("Traceback: %s", traceback.format_exc())
            return {"status": "error", "message": str(e)}

    async def connect_to_websocket(
        self,
        symbol: str,
    ):
        async with websockets.connect(
            "wss://pubwss.bithumb.com/pub/ws", ping_interval=20, ping_timeout=20
        ) as websocket:
            self.websocket_connections[symbol] = websocket
            subscribe_message = json.dumps(
                {
                    "type": "ticker",
                    "symbols": [f"{symbol.upper()}_KRW"],
                    "tickTypes": ["1H"],  # ["30M", "1H", "12H", "24H", "MID"],
                }
            )
            await websocket.send(subscribe_message)

            while symbol in self.websocket_connections:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)
                    if "content" in data:
                        current_price = float(data["content"]["closePrice"])
                        print(f"Current price for {symbol}: {current_price}")
                        await self.analyze_and_trade_by_immediate(symbol, current_price)
                except websockets.ConnectionClosed as e:
                    logger.error("WebSocket connection closed: %s", e)
                    logger.error("Traceback: %s", traceback.format_exc())
                    break
                except Exception as e:
                    logger.error("An error occurred: %s", e)
                    logger.error("Traceback: %s", traceback.format_exc())
                await asyncio.sleep(1)

    async def disconnect_to_websocket(self, symbol):
        # WebSocket 연결 해제
        if symbol in self.websocket_connections:
            websocket = self.websocket_connections.pop(symbol)
            await websocket.close()
        return {
            "status": f"Successfully disconnected to {symbol} WebSocket and current connections: {list(self.websocket_connections.keys())}"
        }

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
        trailing_stop_price = self.holding_coins[symbol]["trailing_stop_price"] or 0
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

            sell_result = await self.sell(
                symbol, amount=self.trailing_stop_amount, reason=Reason["trailingStop"]
            )
            if sell_result and sell_result["status"] == "0000":
                self.trading_history.setdefault(symbol, []).append(
                    {
                        "action": "sell",
                        "reason": "trailingStopConditionMet",
                        "exit_signal": "reach_trailing_stop",
                        "price": current_price,
                        "exit_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )

            self.in_trading_process_coins.remove(symbol)

            return

        # 손절가 도달 시 매도
        if is_stop_loss_condition_met:
            if symbol in self.in_trading_process_coins:
                return  # 이미 매도 진행 중인 경우 추가 매도하지 않음

            self.in_trading_process_coins.append(symbol)

            sell_result = await self.sell(symbol, reason=Reason["stopLoss"])
            if sell_result and sell_result["status"] == "0000":
                self.trading_history.setdefault(symbol, []).append(
                    {
                        "action": "sell",
                        "reason": "stopLossConditionMet",
                        "exit_signal": "reach_stop_loss",
                        "price": current_price,
                        "exit_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )

            self.in_trading_process_coins.remove(symbol)

            return

        # 이익률에 따른 매도
        # profit percentage 를 계속해서 history 쌓듯이 쌓다가, 최고치보다 일정 수준 떨어졌을 때도 매도하는거 추가해야겠다.
        if is_profit_target_condition_met:
            if symbol in self.in_trading_process_coins:
                return  # 이미 매도 진행 중인 경우 추가 매도하지 않음

            self.in_trading_process_coins.append(symbol)

            sell_result = await self.sell(
                symbol,
                amount=self.profit_target.get("amount", self.profit_target["amount"]),
                reason=Reason["profitTarget"],
            )
            if sell_result and sell_result["status"] == "0000":
                self.trading_history.setdefault(symbol, []).append(
                    {
                        "action": "sell",
                        "reason": "profitTargetConditionMet",
                        "exit_signal": "reach_profit",
                        "price": current_price,
                        "exit_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )

            self.in_trading_process_coins.remove(symbol)

            return

    async def analyze_and_trade_by_interval(
        self, symbols: Optional[List[str]] = None, timeframe: str = "1h"
    ):
        self.set_timeframe(timeframe)

        selected_coins = await self.select_coin()
        selected_coins_set = set(selected_coins)

        # 관심 종목 업데이트
        if symbols:
            self.interest_symbols.update(symbols)

        # 추가되어야 하는 코인들을 추가
        selected_coins_set.update(self.interest_symbols)
        selected_coins_set.update(self.holding_coins.keys())

        # trading 시작
        await send_telegram_message(
            (
                f"🚀 Analyze and Trade with 🚀"
                f"\n\nSymbols: {len(selected_coins_set)} and timeframe: {timeframe}"
                f"\n\n📊 Holding coins: {list(self.holding_coins.keys())}"
                f"\n\n🔗 WebSocket connections: {list(self.websocket_connections.keys())}"
            ),
            term_type="short-term",
        )
        logger.info(
            "Running trading bot with symbols: %s and timeframe: %s",
            selected_coins_set,
            timeframe,
        )

        for symbol in selected_coins_set:
            analysis = await self.strategy.analyze_currency_by_turtle(
                order_currency=symbol,
                payment_currency="KRW",
                chart_intervals=self.current_timeframe,
            )

            # 매수는 latest signal 을 기준으로, 매도는 last signal 을 기준으로
            latest_signal = analysis.get("type_latest_signal", "")
            last_signal = analysis.get("type_last_true_signal", "")

            if await check_entry_condition(symbol, latest_signal, self.trading_history):
                if symbol in self.holding_coins:
                    continue  # 이미 보유한 코인인 경우 추가 매수하지 않음

                if len(self.holding_coins) >= self.holding_coin_limmit:
                    continue  # 이미 holing coin limit 이상의 코인을 보유하고 있으면 추가 매수하지 않음

                if symbol in self.in_trading_process_coins:
                    continue

                self.in_trading_process_coins.append(symbol)

                buy_result = await self.buy(
                    symbol, reason=Reason["entrySignalConditionMet"]
                )
                if buy_result and buy_result["status"] == "0000":
                    pass

                self.in_trading_process_coins.remove(symbol)

            if await check_exit_condition(symbol, last_signal, self.trading_history):
                if symbol not in self.holding_coins:
                    continue

                if symbol in self.in_trading_process_coins:
                    continue

                self.in_trading_process_coins.append(symbol)

                sell_result = await self.sell(
                    symbol, reason=Reason["eixtSignalConditionMet"]
                )
                if sell_result and sell_result["status"] == "0000":
                    pass

                self.in_trading_process_coins.remove(symbol)

    async def stop_all(self):
        self._running = False

    async def run(self, symbols: Optional[List[str]] = None, timeframe: str = "1h"):
        self._running = True
        self.set_timeframe(timeframe)
        self.trading_history = {}  # 추후에 database 에 저장하도록 변경해야함.

        while self._running:
            await send_telegram_message(
                "🚀 Trading bot started by interval.", term_type="short-term"
            )
            await self.analyze_and_trade_by_interval(symbols, timeframe)
            interval = self.timeframe_intervals.get(timeframe, timedelta(minutes=1))
            await asyncio.sleep(interval.total_seconds())

        logger.info("Trading bot stopped.")
        await send_telegram_message("⛔️ Trading bot stopped.", term_type="short-term")


# trading history 에 best profit 을 추가해서, best profit 이후에 일정 수준 떨어지면 일정 물량 매도하는 로직 추가.
