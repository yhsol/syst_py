# app/api/trade.py
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Query

from app.services.bithumb_service import BithumbService
from app.services.bithumb_service import BithumbPrivateService
from app.services.stratege_service import StrategyService
from app.services.trading import TradingBot

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


@router.get(f"{ROOT}/run")
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


@router.get(f"{ROOT}/stop")
async def stoptrade():
    await trading_bot.stop_all()
    return {"status": "trading stopped"}


@router.get(f"{ROOT}/stopsymbol")
async def stopsymbol(symbol: str):
    symbol = symbol.upper()
    await trading_bot.stop_symbol(symbol)
    return {"status": f"{symbol} trading stopped"}


@router.get(f"{ROOT}/status")
async def status():
    return trading_bot.get_status()


@router.get(f"{ROOT}/addsymbol")
async def addsymbol(
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


@router.get(f"{ROOT}/addholding")
async def add_holding(
    background_tasks: BackgroundTasks,
    symbol: str,
    units: float,
    buy_price: float,
    force: bool = False,
):
    symbol = symbol.upper()
    if symbol in trading_bot.holding_coins and not force:
        return {"status": f"{symbol} is already in holding coins"}

    await trading_bot.add_holding_coin(symbol, units, buy_price)
    await trading_bot.add_active_symbols([symbol])
    background_tasks.add_task(
        trading_bot.trade, symbol, timeframe=trading_bot.current_timeframe
    )
    return {
        "status": f"{symbol} add to holding coin and active symbols and started trading"
    }


@router.get(f"{ROOT}/removeholding")
async def remove_holding(symbol: str):
    symbol = symbol.upper()
    if symbol not in trading_bot.holding_coins:
        return {"status": f"{symbol} is not in holding coins"}

    await trading_bot.remove_holding_coin(symbol)
    await trading_bot.remove_active_symbols([symbol])

    return {"status": f"{symbol} removed from holding coins"}


@router.get(f"{ROOT}/reselect")
async def reselect(background_tasks: BackgroundTasks):
    trading_bot.active_symbols = set()
    selected_symbols = await trading_bot.select_coin()
    new_symbols = [
        symbol
        for symbol in selected_symbols
        if symbol not in trading_bot.active_symbols
    ]
    slots_available = 10 - len(trading_bot.active_symbols)
    trading_bot.active_symbols.update(new_symbols[:slots_available])

    # 새로운 심볼에 대해 trade 시작
    for symbol in new_symbols[:slots_available]:
        background_tasks.add_task(trading_bot.trade, symbol)

    return {
        "status": "active symbols refreshed and started trading",
        "active_symbols": list(trading_bot.active_symbols),
    }


async def set_available_krw_to_each_trade(krw: float):
    trading_bot.available_krw_to_each_trade = krw
    return {"status": f"available_krw_to_each_trade is set to {krw}"}


@router.get(f"{ROOT}/apitest")
async def apitest():
    result = "add api for test"
    return result
