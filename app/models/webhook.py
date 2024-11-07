from pydantic import BaseModel
from typing import Literal

class TradingViewAlert(BaseModel):
    symbol: str
    action: str
    timeframe: str
    quantity: float = 0
    price: float