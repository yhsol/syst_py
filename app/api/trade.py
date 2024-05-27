# app/api/trade.py
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.services.bithumb_service import BithumbService
from app.services.bithumb_service import BithumbPrivateService
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


@router.get(f"{ROOT}/run", dependencies=[Depends(verify_api_key)])
async def runtrade(
    background_tasks: BackgroundTasks,
    symbols: Optional[List[str]] = Query(None),
    timeframe: str = "1h",
):
    if symbols is not None:
        symbols = [symbol.upper() for symbol in symbols]

    print(
        f"Endpoint runtrade Receive: trade: Symbols: {symbols}, Timeframe: {timeframe}"
    )
    background_tasks.add_task(trading_bot.run, symbols=symbols, timeframe=timeframe)
    return {"status": "trading started"}


@router.get(f"{ROOT}/stop-all", dependencies=[Depends(verify_api_key)])
async def stop_all():
    await trading_bot.stop_all()
    return {"status": "trading stopped"}


@router.get(f"{ROOT}/stop-symbol", dependencies=[Depends(verify_api_key)])
async def stop_symbol(symbol: str):
    symbol = symbol.upper()
    await trading_bot.stop_symbol(symbol)
    return {"status": f"{symbol} trading stopped"}


@router.get(f"{ROOT}/status", dependencies=[Depends(verify_api_key)])
async def status():
    return trading_bot.get_status()


@router.get(f"{ROOT}/set-available-krw", dependencies=[Depends(verify_api_key)])
async def set_available_krw(krw: float):
    trading_bot.available_krw_to_each_trade = krw
    return {"status": f"available_krw_to_each_trade is set to {krw}"}


@router.get(f"{ROOT}/add-holding", dependencies=[Depends(verify_api_key)])
async def add_holding(
    background_tasks: BackgroundTasks,
    symbol: str,
    units: float,
    buy_price: float,
):
    symbol = symbol.upper()

    await trading_bot.add_holding_coin(symbol, units, buy_price)
    await trading_bot.add_active_symbols([symbol])
    background_tasks.add_task(
        trading_bot.trade, symbol, timeframe=trading_bot.current_timeframe
    )
    return {
        "status": f"{symbol} add to holding coin and active symbols and started trading"
    }


@router.get(f"{ROOT}/remove-holding", dependencies=[Depends(verify_api_key)])
async def remove_holding(symbol: str):
    symbol = symbol.upper()
    if symbol not in trading_bot.holding_coins:
        return {"status": f"{symbol} is not in holding coins"}

    await trading_bot.remove_holding_coin(symbol)
    await trading_bot.remove_active_symbols([symbol])

    return {"status": f"{symbol} removed from holding coins"}


@router.get(f"{ROOT}/add-active-symbol", dependencies=[Depends(verify_api_key)])
async def add_active_symbol(
    background_tasks: BackgroundTasks, symbols: Optional[List[str]] = Query(None)
):
    if symbols is None:
        return {"status": "No symbols to add"}

    symbols = [symbol.upper() for symbol in symbols]

    for symbol in symbols:
        if symbol not in trading_bot.active_symbols:
            await trading_bot.add_active_symbols(symbols)
            background_tasks.add_task(trading_bot.trade, symbol)
            return {"status": f"{symbol} added to active symbols and started trading"}
        return {"status": f"{symbol} is already in active symbols"}


@router.get(f"{ROOT}/reselect", dependencies=[Depends(verify_api_key)])
async def reselect(background_tasks: BackgroundTasks):
    background_tasks.add_task(trading_bot.reselect_and_trade)
    return {
        "status": "active symbols refreshed and started trading",
        "holding_coins": list(trading_bot.holding_coins),
    }


@router.get(f"{ROOT}/set-profit-target", dependencies=[Depends(verify_api_key)])
async def set_profit_target(
    profit: Optional[float] = None, amount: Optional[float] = None
):
    await trading_bot.set_profit_target(profit, amount)
    return {
        "status": "profit target set successfully",
        "profit": profit,
        "amount": amount,
    }


@router.get(f"{ROOT}/buy", dependencies=[Depends(verify_api_key)])
async def buy(symbol: str, reason: str = "user request"):
    await trading_bot.buy(symbol, reason)
    return {"status": f"buy {symbol} success"}


@router.get(f"{ROOT}/sell", dependencies=[Depends(verify_api_key)])
async def sell(symbol: str, amount=1.0, reason: str = "user request"):
    await trading_bot.sell(symbol, amount, reason)
    return {"status": f"sell {symbol} success"}


@router.get(f"{ROOT}/api-test", dependencies=[Depends(verify_api_key)])
async def apitest():
    result = "add api for test"
    return result
