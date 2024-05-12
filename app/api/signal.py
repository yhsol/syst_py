# app/api/signal.py
from fastapi import APIRouter

from app.services.bithumb_service import BithumbService
from app.services.stratege_service import StrategyService

router = APIRouter()
ROOT = "/signal"

bithumb_service = BithumbService()
strategy_service = StrategyService(
    strategy="Turtle Trading", bithumb_service=bithumb_service
)


@router.get(f"{ROOT}/turtle")
async def get_turtle_signals(ticker: str):
    result = await strategy_service.analyze_currency_by_turtle(ticker.upper())
    return result
