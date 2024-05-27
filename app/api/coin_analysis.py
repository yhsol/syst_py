# app/api/coin_analysis.py
from typing import Literal

from fastapi import APIRouter, Depends

from app.dependencies.auth import verify_api_key
from app.utils.trading_helpers import perform_analysis_and_notify


router = APIRouter()


@router.get("/analyze", dependencies=[Depends(verify_api_key)])
async def get_ticker(term_type: Literal["long-term", "short-term"] = "long-term"):
    await perform_analysis_and_notify(term_type)
    return f"Type ${term_type} analysis initiated and message sent to Telegram."
