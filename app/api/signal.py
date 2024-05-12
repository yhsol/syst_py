# app/api/signal.py
from fastapi import APIRouter

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
async def get_turtle_signals(ticker: str):
    result = await strategy_service.analyze_currency_by_turtle(ticker.upper())
    return result


@router.get(f"{ROOT}/info")
async def get_info():
    result = await bithumb_private_service.get_account_info("STX")
    return result


@router.get(f"{ROOT}/socket")
async def get_socket():
    await bithumb_service.bithumb_ws_client(
        "ticker",
        [
            # "BTC_KRW", "ETH_KRW"
            "PEPE_KRW"
        ],
        ["30M"],
    )


@router.get(f"{ROOT}/trade")
async def trade(action: str, symbol: str):
    if action == "buy":
        result = await trading_bot.execute_trade(action="buy", symbol=symbol)

        if result["status"] != "0000":
            return {
                "status": "error",
                "message": "Failed to buy.",
                "result": result,
            }

        return {
            "status": "success",
            "message": f"Successfully bought {symbol}.",
            "result": result,
        }

    if action == "sell":
        result = await trading_bot.execute_trade(action="sell", symbol=symbol)

        if result["status"] != "0000":
            return {
                "status": "error",
                "message": "Failed to sell.",
                "result": result,
            }

        return {
            "status": "success",
            "message": f"Successfully sold {symbol}.",
            "result": result,
        }

    return "Invalid action."
