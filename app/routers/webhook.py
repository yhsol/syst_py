from fastapi import APIRouter, Request, HTTPException, Query
from app.models.webhook import TradingViewAlert
from app.services.trading import TradingBot
from app.services.bithumb_service import BithumbService, BithumbPrivateService
from app.services.stratege_service import StrategyService
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# 서비스 인스턴스 생성
bithumb_service = BithumbService()
bithumb_private_service = BithumbPrivateService()
strategy_service = StrategyService(
    strategy="Turtle Trading",
    bithumb_service=bithumb_service
)

@router.post("/tradingview")
async def tradingview_webhook(request: Request, test_mode: bool = Query(default=False)):
    try:
        body = await request.json()
        logger.info(f"Received webhook data: {body}")
        
        # 데이터 검증
        alert = TradingViewAlert(**body)
        logger.info(f"Parsed alert data: {alert}")
        
        if test_mode:
            return {
                "status": "success",
                "message": "Test successful",
                "would_execute": {
                    "action": alert.action,
                    "symbol": alert.symbol,
                    "price": alert.price,
                    "timeframe": alert.timeframe
                }
            }
            
        # TradingBot 인스턴스 생성 시 필요한 서비스들 전달
        trading_bot = TradingBot(
            bithumb_service=bithumb_service,
            bithumb_private_service=bithumb_private_service,
            strategy_service=strategy_service
        )
        
        # 심볼 변환 (거래소별 심볼 포맷에 맞게)
        symbol = alert.symbol.upper().replace('KRW', '')
        
        if alert.action == "buy":
            # 수량이 0이면 최대 매수 가능 수량 계산
            quantity = alert.quantity if alert.quantity > 0 else await trading_bot.get_available_buy_units(symbol)
            
            if not quantity:
                raise HTTPException(status_code=400, detail="Failed to calculate buy quantity")

            result = await trading_bot.buy(
                symbol=symbol,
                reason="TradingView Signal"
            )

        elif alert.action == "sell":
            quantity = alert.quantity if alert.quantity > 0 else await trading_bot.get_available_sell_units(symbol)
            
            if not quantity:
                raise HTTPException(status_code=400, detail="No holdings available for sell")

            result = await trading_bot.sell(
                symbol=symbol,
                amount=1.0,  # 전량 매도
                reason="TradingView Signal"
            )

        return result

    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 