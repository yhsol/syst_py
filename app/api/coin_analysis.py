# app/api/coin_analysis.py
from fastapi import APIRouter
from app.utils.trading_utils import performAnalysisAndNotify
from typing import Literal

router = APIRouter()


@router.get("/analyze")
async def get_ticker(type: Literal["long-term", "short-term"] = "long-term"):
    await performAnalysisAndNotify(type)
    return f"Type ${type} analysis initiated and message sent to Telegram."
