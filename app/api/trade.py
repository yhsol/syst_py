# app/api/trade.py
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import FileResponse, JSONResponse

from app.services.bithumb_service import BithumbService, BithumbPrivateService
from app.services.market_monitor import MarketMonitor
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
market_monitor = MarketMonitor(trading_bot=trading_bot, bithumb_service=bithumb_service)


@router.get(f"{ROOT}/api-test", dependencies=[Depends(verify_api_key)])
async def apitest():
    result = "add api for test"
    return result


@router.get(f"{ROOT}/run", dependencies=[Depends(verify_api_key)])
async def runtrade(
    background_tasks: BackgroundTasks,
    symbols: Optional[List[str]] = Query(None),
    timeframe: str = "30m",
    stoploss_percent: float = 0.02,
) -> dict:
    if symbols is not None:
        symbols = [symbol.upper() for symbol in symbols]

    print(
        f"Endpoint runtrade Receive: trade: Symbols: {symbols}, Timeframe: {timeframe}, Stop Loss Percent: {stop_loss_percent}"
    )
    background_tasks.add_task(
        trading_bot.run,
        symbols=symbols,
        timeframe=timeframe,
        stop_loss_percent=stoploss_percent,
    )
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
    split_sell_count: int = 0,
) -> dict:
    symbol = symbol.upper()

    await trading_bot.add_holding_coin(symbol, units, buy_price, split_sell_count)
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

    return {
        "status": f"{symbol} removed from holding coins, and now holding coins are {trading_bot.holding_coins}"
    }


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


@router.get(f"{ROOT}/set-timeframe-for-chart", dependencies=[Depends(verify_api_key)])
async def set_timeframe_for_chart(timeframe: str) -> dict:
    trading_bot.set_timeframe_for_chart(timeframe)
    return {"status": f"timeframe for chart is set to {timeframe}"}


@router.get(
    f"{ROOT}/set-timeframe-for-internal", dependencies=[Depends(verify_api_key)]
)
async def set_timeframe_for_internal(timeframe: str) -> dict:
    trading_bot.set_timeframe_for_interval(timeframe)
    return {"status": f"timeframe for interval is set to {timeframe}"}


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


@router.get(
    f"{ROOT}/set-available-split-sell-count", dependencies=[Depends(verify_api_key)]
)
async def set_available_split_sell_count(split_sell_count: int) -> dict:
    response = trading_bot.set_available_split_sell_count(split_sell_count)
    return response


@router.get(f"{ROOT}/set-stop-loss-percent", dependencies=[Depends(verify_api_key)])
def stop_loss_percent(percent: float = 0.02) -> dict:
    response = trading_bot.set_stop_loss_percent(percent)
    return response


@router.get(f"{ROOT}/run-mm", dependencies=[Depends(verify_api_key)])
async def run_market_monitor(
    background_tasks: BackgroundTasks,
):
    background_tasks.add_task(market_monitor.run)
    return {"status": 200, "message": "market monitor started"}


@router.get(f"{ROOT}/stop-mm", dependencies=[Depends(verify_api_key)])
async def stop_market_monitor() -> dict:
    await market_monitor.stop()
    return {"status": 200, "message": "market monitor stopped"}


@router.get(f"{ROOT}/download-log", dependencies=[Depends(verify_api_key)])
async def download_log():
    log_file_path = "trading_bot.log"
    return FileResponse(
        log_file_path, media_type="application/octet-stream", filename="trading_bot.log"
    )


@router.get(f"{ROOT}/clear-log", dependencies=[Depends(verify_api_key)])
async def clear_log():
    log_file_path = "trading_bot.log"
    try:
        with open(log_file_path, "w") as log_file:
            log_file.truncate(0)  # 로그 파일을 비웁니다.
        return JSONResponse(
            content={"status": "success", "message": "Log file cleared."}
        )
    except Exception as e:
        return JSONResponse(
            content={"status": "error", "message": str(e)}, status_code=500
        )


@router.get(f"{ROOT}/backtest", dependencies=[Depends(verify_api_key)])
async def run_backtest(
    background_tasks: BackgroundTasks,
    symbols: Optional[List[str]] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    timeframe: str = "1h",
):
    symbols = [symbol.upper() for symbol in symbols] if symbols is not None else None
    background_tasks.add_task(
        trading_bot.run_backtest, symbols, start_date, end_date, timeframe
    )
    return {"status": "backtest started"}
