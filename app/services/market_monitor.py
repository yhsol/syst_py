import asyncio
import json
import logging
from typing import Dict, Optional

import websockets

from app.telegram.telegram_client import send_telegram_message

# Logging 설정
logger = logging.getLogger(__name__)


class MarketMonitor:
    def __init__(self, trading_bot, bithumb_service):
        self.trading_bot = trading_bot
        self.bithumb = bithumb_service
        self.price_change_threshold = 0.05
        self.volume_change_threshold = 3.0
        self.previous_prices: Dict[str, float] = {}
        self.previous_volumes: Dict[str, float] = {}
        self.websocket_connections: Dict[str, websockets.WebSocketClientProtocol] = {}

    async def monitor_market(self, symbol: str):
        async with websockets.connect("wss://pubwss.bithumb.com/pub/ws") as websocket:
            self.websocket_connections[symbol] = websocket
            subscribe_message = json.dumps(
                {
                    "type": "ticker",
                    "symbols": [f"{symbol.upper()}_KRW"],
                    "tickTypes": ["MID"],
                }
            )
            await websocket.send(subscribe_message)

            while symbol in self.websocket_connections:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)
                    self.process_market_data(data)
                except websockets.ConnectionClosed as e:
                    logger.error("Connection closed: %s", e)
                    break
                except Exception as e:
                    logger.error("An error occurred: %s", e)
                    await asyncio.sleep(1)  # 재연결 시도를 위해 잠시 대기

    def process_market_data(self, data):
        if "content" in data:
            symbol = data["content"]["symbol"]
            close_price = float(data["content"]["closePrice"])
            volume = float(data["content"]["volume"])
            print(f"Processing data for {symbol}")

            if self.detect_sudden_change(symbol, close_price, volume):
                print(f"Detected sudden change in {symbol}")
                self.send_alert(symbol, close_price, volume)
                return True
        return False

    def detect_sudden_change(
        self, symbol: str, close_price: float, volume: float
    ) -> bool:
        prev_price = self.previous_prices.get(symbol, close_price)
        prev_volume = self.previous_volumes.get(symbol, volume)

        price_change = abs((close_price - prev_price) / prev_price)
        volume_change = volume / prev_volume

        self.previous_prices[symbol] = close_price
        self.previous_volumes[symbol] = volume

        return (
            price_change >= self.price_change_threshold
            and volume_change >= self.volume_change_threshold
        )

    def send_alert(self, symbol: str, close_price: float, volume: float):
        logger.info(
            "Alert! %s has surged. Price: %s, Volume: %s", symbol, close_price, volume
        )
        print(
            f"🚨 Alert! {symbol} has surged. 🚨\n\n💰 Price: {close_price}\n📈 Volume: {volume}"
        )
        # 여기서 매수
        # self.trading_bot.buy(symbol, "sudden surge")
        asyncio.create_task(
            send_telegram_message(
                f"🚨 Alert! {symbol} has surged. 🚨\n\n💰 Price: {close_price}\n📈 Volume: {volume}",
                "short-term",
            )
        )

    async def disconnect_to_websocket(self, symbol):
        if symbol in self.websocket_connections:
            websocket = self.websocket_connections.pop(symbol)
            await websocket.close()
        return {
            "status": f"Successfully disconnected to {symbol} WebSocket and current connections: {list(self.websocket_connections.keys())}"
        }

    async def stop(self):
        await asyncio.gather(
            *[
                self.disconnect_to_websocket(symbol)
                for symbol in self.websocket_connections
            ]
        )

    async def run(self):
        all_coins = await self.bithumb.get_current_price("KRW")
        filtered_by_value = await self.bithumb.filter_coins_by_value(all_coins, 100)

        await asyncio.gather(
            *[self.monitor_market(symbol) for symbol in filtered_by_value]
        )