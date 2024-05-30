# app/api/trade.py
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.services.bithumb_service import BithumbService, BithumbPrivateService
from app.services.stratege_service import StrategyService
from app.services.trading import TradingBot
from app.dependencies.auth import verify_api_key

router = APIRouter()
ROOT = "/trade"

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


@router.get(f"{ROOT}/api-test", dependencies=[Depends(verify_api_key)])
async def apitest():
    result = "add api for test"
    return result


@router.get(f"{ROOT}/run", dependencies=[Depends(verify_api_key)])
async def runtrade(
    background_tasks: BackgroundTasks,
    symbols: Optional[List[str]] = Query(None),
    timeframe: str = "1h",
) -> dict:
    if symbols is not None:
        symbols = [symbol.upper() for symbol in symbols]

    print(
        f"Endpoint runtrade Receive: trade: Symbols: {symbols}, Timeframe: {timeframe}"
    )
    background_tasks.add_task(trading_bot.run, symbols=symbols, timeframe=timeframe)
    return {"status": "trading started"}


@router.get(f"{ROOT}/stop-all", dependencies=[Depends(verify_api_key)])
async def stop_all() -> dict:
    await trading_bot.stop_all()
    return {"status": "trading stopped"}


@router.get(f"{ROOT}/status", dependencies=[Depends(verify_api_key)])
async def status() -> dict:
    return trading_bot.get_status()


@router.get(f"{ROOT}/set-available-krw", dependencies=[Depends(verify_api_key)])
async def set_available_krw(krw: float) -> dict:
    trading_bot.available_krw_to_each_trade = krw
    return {"status": f"available_krw_to_each_trade is set to {krw}"}


@router.get(f"{ROOT}/add-holding", dependencies=[Depends(verify_api_key)])
async def add_holding(
    background_tasks: BackgroundTasks,
    symbol: str,
    units: float,
    buy_price: float,
) -> dict:
    symbol = symbol.upper()

    await trading_bot.add_holding_coin(symbol, units, buy_price)
    background_tasks.add_task(trading_bot.connect_to_websocket, symbol)
    return {
        "status": f"{symbol} add to holding coin and active symbols and started trading"
    }


@router.get(f"{ROOT}/remove-holding", dependencies=[Depends(verify_api_key)])
async def remove_holding(symbol: str) -> dict:
    symbol = symbol.upper()
    if symbol not in trading_bot.holding_coins:
        return {"status": f"{symbol} is not in holding coins"}

    await trading_bot.remove_holding_coin(symbol)
    await trading_bot.disconnect_to_websocket(symbol)

    return {"status": f"{symbol} removed from holding coins"}


@router.get(f"{ROOT}/set-profit-target", dependencies=[Depends(verify_api_key)])
async def set_profit_target(
    profit: Optional[float] = None, amount: Optional[float] = None
) -> dict:
    await trading_bot.set_profit_target(profit, amount)
    return {
        "status": "profit target set successfully",
        "profit": profit,
        "amount": amount,
    }


@router.get(f"{ROOT}/buy", dependencies=[Depends(verify_api_key)])
async def buy(symbol: str, reason: str = "user request") -> dict:
    symbol = symbol.upper()
    await trading_bot.buy(symbol, reason)
    return {"status": f"buy {symbol} success"}


@router.get(f"{ROOT}/sell", dependencies=[Depends(verify_api_key)])
async def sell(symbol: str, amount: float = 1.0, reason: str = "user request") -> dict:
    symbol = symbol.upper()
    await trading_bot.sell(symbol, amount, reason)
    return {"status": f"sell {symbol} success"}


@router.get(f"{ROOT}/set-timeframe", dependencies=[Depends(verify_api_key)])
async def set_timeframe(timeframe: str) -> dict:
    trading_bot.set_timeframe(timeframe)
    return {"status": f"current timeframe is set to {timeframe}"}


@router.get(f"{ROOT}/set-trailing-stop", dependencies=[Depends(verify_api_key)])
async def set_trailing_stop(symbol: str, trailing_stop_percent: float) -> dict:
    symbol = symbol.upper()
    response = await trading_bot.set_trailing_stop(symbol, trailing_stop_percent)
    return response


@router.get(f"{ROOT}/set-trailing-stop-percent", dependencies=[Depends(verify_api_key)])
async def set_trailing_stop_percent(trailing_stop_percent: float) -> dict:
    response = trading_bot.set_trailing_stop_percent(trailing_stop_percent)
    return response


@router.get(f"{ROOT}/set-trailing-stop-amount", dependencies=[Depends(verify_api_key)])
async def set_trailing_stop_amount(trailing_stop_amount: float) -> dict:
    response = trading_bot.set_trailing_stop_amount(trailing_stop_amount)
    return response


@router.get(f"{ROOT}/set-trade-coin-limit", dependencies=[Depends(verify_api_key)])
async def set_trade_coin_limit(trade_coin_limit: int) -> dict:
    response = trading_bot.set_trade_coin_limit(trade_coin_limit)
    return response


@router.get(f"{ROOT}/get-candlestick-data", dependencies=[Depends(verify_api_key)])
async def get_candlestick_data(symbol: str, timeframe: str) -> dict:
    symbol = symbol.upper()
    return await bithumb_service.get_candlestick_data(symbol, "KRW", timeframe)
