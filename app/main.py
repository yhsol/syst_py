from typing import Union

from fastapi import FastAPI

from app.api import coin_analysis
from app.services.bithumb_service import BithumbService
from app.services.stratege_service import StrategyService

app = FastAPI()

app.include_router(coin_analysis.router)

bithumb_service = BithumbService()
strategy_service = StrategyService(
    strategy="Turtle Trading", bithumb_service=bithumb_service
)


@app.get("/")
async def read_root():
    return {"Hello": "World"}


@app.get("/items/{item_id}")
async def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q": q}


@app.get("/turtle/{ticker}")
async def get_turtle_signals(ticker: str):
    result = await strategy_service.analyze_currency(ticker.upper())
    return result
