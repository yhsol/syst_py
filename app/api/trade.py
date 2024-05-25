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
    print(
        f"Endpoint runtrade Receive: trade: Symbols: {symbols}, Timeframe: {timeframe}"
    )
    background_tasks.add_task(trading_bot.run, symbols=symbols, timeframe=timeframe)
    return {"status": "trading started"}


@router.get(f"{ROOT}/stop")
async def stoptrade():
    await trading_bot.stop()
    return {"status": "trading stopped"}


@router.get(f"{ROOT}/addsymbol")
async def addsymbol(
    background_tasks: BackgroundTasks, symbols: Optional[List[str]] = Query(None)
):
    if symbols is None:
        return {"status": "No symbols to add"}

    for symbol in symbols:
        if symbol not in trading_bot.active_symbols:
            await trading_bot.add_active_symbols(symbols)
            background_tasks.add_task(trading_bot.trade, symbol)
            return {"status": f"{symbol} added to active symbols and started trading"}
        return {"status": f"{symbol} is already in active symbols"}


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
