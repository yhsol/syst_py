from fastapi import APIRouter, Request, HTTPException
from app.models.webhook import TradingViewAlert
from app.services.trading import TradingBot
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/tradingview")
async def tradingview_webhook(request: Request):
    try:
        body = await request.json()
        logger.info(f"Received webhook data: {body}")
        
        # 데이터 검증
        alert = TradingViewAlert(**body)
        logger.info(f"Parsed alert data: {alert}")
        
        trading_bot = TradingBot()
        
        # 심볼 변환 (거래소별 심볼 포맷에 맞게)
        symbol = alert.symbol.upper()
        
        if alert.action == "buy":
            # 수량이 0이면 최대 매수 가능 수량 계산
            quantity = alert.quantity if alert.quantity > 0 else await trading_bot.get_available_buy_units(symbol)
            
            if not quantity:
                raise HTTPException(status_code=400, detail="Failed to calculate buy quantity")

            result = await trading_bot.buy(
                symbol=symbol,
                reason=f"TradingView Signal: {alert.reason}" if alert.reason else "TradingView Signal"
            )

        elif alert.action == "sell":
            quantity = alert.quantity if alert.quantity > 0 else await trading_bot.get_available_sell_units(symbol)
            
            if not quantity:
                raise HTTPException(status_code=400, detail="No holdings available for sell")

            result = await trading_bot.sell(
                symbol=symbol,
                amount=1.0,  # 전량 매도
                reason=f"TradingView Signal: {alert.reason}" if alert.reason else "TradingView Signal"
            )

        if not result or result.get("status") != "0000":
            raise HTTPException(status_code=400, detail="Order failed")

        return {
            "status": "success",
            "message": result.get("message", "Order executed successfully")
        }

    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 