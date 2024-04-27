from pydantic import BaseModel, Field

# 아직 response 까지 정의하진 않을 것. 다만, bithumb_service 의 함수 코멘트에 returns 를 정의뒀기 때문에, 필요하다면 returns 를 참고해서 response 를 정의할 수 있다.


class CurrentPriceResponse(BaseModel):
    status: str = Field(
        ...,
        description="Result status code (0000 for success, other error codes for failure)",
    )
    opening_price: float = Field(..., description="Opening price at 00:00")
    closing_price: float = Field(..., description="Closing price at 00:00")
    min_price: float = Field(..., description="Lowest price at 00:00")
    max_price: float = Field(..., description="Highest price at 00:00")
    units_traded: float = Field(..., description="Trading volume at 00:00")
    acc_trade_value: float = Field(..., description="Trading value at 00:00")
    prev_closing_price: float = Field(..., description="Previous day's closing price")
    units_traded_24H: float = Field(
        ..., description="Trading volume in the last 24 hours"
    )
    acc_trade_value_24H: float = Field(
        ..., description="Trading value in the last 24 hours"
    )
    fluctate_24H: float = Field(
        ..., description="Fluctuation range in the last 24 hours"
    )
    fluctate_rate_24H: float = Field(
        ..., description="Fluctuation rate in the last 24 hours"
    )
    date: int = Field(..., description="Timestamp")
