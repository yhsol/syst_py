# app/api/signal.py
from typing import List, Optional
from fastapi import APIRouter, Query

from app.services.bithumb_service import BithumbService
from app.services.bithumb_service import BithumbPrivateService
from app.services.stratege_service import StrategyService
from app.services.trading import TradingBot

router = APIRouter()
ROOT = "/signal"

bithumb_service = BithumbService()
bithumb_private_service = BithumbPrivateService()
strategy_service = StrategyService(
    strategy="Turtle Trading", bithumb_service=bithumb_service
)
trading_bot = TradingBot(
    bithumb_service=bithumb_service,
    bithumb_private_service=bithumb_private_service,
    strategy_service=strategy_service,
)


@router.get(f"{ROOT}/turtle")
async def get_turtle_signals(ticker: str, interval: str = "1h"):
    result = await strategy_service.analyze_currency_by_turtle(
        ticker.upper(), chart_intervals=interval
    )
    return result


@router.get(f"{ROOT}/turtle/long")
async def get_turtle_entry_signals(interval: str = "1h"):
    all_coins = await bithumb_service.get_current_price("KRW")
    filtered_by_value = await bithumb_service.filter_coins_by_value(all_coins)

    long_entry_coins = []
    for coin in filtered_by_value:
        result = await strategy_service.analyze_currency_by_turtle(
            coin, chart_intervals=interval
        )
        if (
            "long_entry" in result["type_last_true_signal"]
            or "short_exit" in result["type_last_true_signal"]
        ):
            long_entry_coins.append(coin)

    return long_entry_coins


@router.get(f"{ROOT}/info")
async def get_info():
    result = await bithumb_private_service.get_account_info("STX")
    return result


@router.get(f"{ROOT}/socket")
async def get_socket():
    # await bithumb_service.bithumb_ws_client(
    #     "ticker",
    #     [
    #         # "BTC_KRW", "ETH_KRW"
    #         "PEPE_KRW"
    #     ],
    #     ["30M"],
    # )
    await trading_bot.subscribe_to_websocket("BTC", "1h")


@router.get(f"{ROOT}/trade")
async def trade(
    symbols: Optional[List[str]] = Query(None),
    timeframe: str = "1h",
):
    print(f"Endpoint Receive: trade: Symbols: {symbols}, Timeframe: {timeframe}")
    return await trading_bot.run(symbols=symbols, timeframe=timeframe)


@router.get(f"{ROOT}/select")
async def select():
    return await trading_bot.select_coin()


@router.get(f"{ROOT}/candlestick")
async def get_candlestick_data(ticker: str, interval: str = "1h"):
    return await bithumb_service.get_candlestick_data(ticker.upper(), "KRW", interval)
