from typing import List

from app.services.bithumb_service import BithumbPrivateService, BithumbService
from app.services.stratege_service import StrategyService


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

    async def handle_trade(self, symbol, signal):
        # 데이터를 트래킹하고 터틀 전략에 따라 매수/매도
        if self.check_entry_condition(signal):
            await self.execute_trade("buy", symbol)
        elif self.check_exit_condition(signal):
            await self.execute_trade("sell", symbol)
            await self.disconnect(symbol)

    async def check_entry_condition(self, signal):
        # 매수 조건 로직
        if ("short_exit" in signal) or ("long_entry" in signal):
            return True

    async def check_exit_condition(self, signal):
        # 매도 조건 로직
        if ("long_exit" in signal) or ("short_entry" in signal):
            return True

    async def get_available_buy_units(self, symbol):
        # 주문 가능 수량 조회
        balance = await self.bithumb_private.get_balance(symbol)
        available_krw = balance["data"]["available_krw"]

        # 매수 가능 금액을 10000원으로 제한
        available_krw = 10000

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

        if action == "buy":
            # 매수 주문 실행
            buy_units = await self.get_available_buy_units(symbol)

            # 전체 unit 의 70% 만큼만 매수. bithumb 에서 제한하는 듯?
            # https://github.com/sharebook-kr/pybithumb/issues/26
            # 소수점 8자리까지만 가능
            # 그런데 전체 자산의 70% 이상을 매수할 일은 없을 확률이 높으니 고려하지 않아도 될 듯.
            # available_units = round(buy_units * 0.7, 8)

            available_units = round(buy_units, 8)

            result = await self.bithumb_private.market_buy(
                units=available_units,
                order_currency=symbol,
                payment_currency="KRW",
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
            return result

        print(f"Executing {action} on {symbol}")

    async def disconnect(self, symbol):
        # WebSocket 연결 해제
        print(f"Disconnecting {symbol}")

    async def run(self, symbol):
        analyze = self.strategy.analyze_currency_by_turtle(symbol)
        latest_signal = analyze["type_latest_signal"]
        self.handle_trade(symbol, latest_signal)
