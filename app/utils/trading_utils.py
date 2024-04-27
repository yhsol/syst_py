import math
from typing import Literal
from app.services.bithumb_service import BithumbService
from app.telegram.telegram_client import send_telegram_message, generate_message

bithumb = BithumbService()


async def fetchAllCandlestickData(symbols: list, chartIntervals: str = "1h"):
    candlestickData = {}
    for symbol in symbols:
        data = await bithumb.get_candlestick_data(symbol, "KRW", chartIntervals)
        candlestickData[symbol] = data
    return candlestickData


async def filterCoinsByValue(coinData, limit=100):
    coins = []
    for key, value in coinData.get(
        "data", {}
    ).items():  # .get()을 사용하여 "data"가 없는 경우에 대비
        try:
            # value가 실제로 딕셔너리인지 확인
            if not isinstance(value, dict):
                continue

            tradeVolume = float(
                value.get("units_traded_24H", 0)
            )  # .get()을 사용해 키가 없는 경우 0을 반환
            tradeValue = float(value.get("acc_trade_value_24H", 0))

            # NaN 체크를 하고 유효한 값만 리스트에 추가
            if not (math.isnan(tradeVolume) or math.isnan(tradeValue)):
                coins.append(
                    {
                        "symbol": key,
                        "tradeVolume": tradeVolume,
                        "tradeValue": tradeValue,
                        "data": value,
                    }
                )
        except (ValueError, TypeError) as e:
            print(f"Error processing coin {key}: {str(e)}")
            continue  # 변환 실패 시 다음 코인으로 넘어감

    # 거래대금 기준으로 정렬하고 상위 limit 개 코인을 반환
    sorted_coins = sorted(coins, key=lambda coin: coin["tradeValue"], reverse=True)
    return [coin["symbol"] for coin in sorted_coins[:limit]]


async def filterCoinsByRiseRate(coinsData, limit):
    coins = []
    for symbol, data in coinsData.get("data", {}).items():
        try:
            if (
                isinstance(data, dict)
                and "opening_price" in data
                and "closing_price" in data
            ):
                openPrice = float(data["opening_price"])
                closePrice = float(data["closing_price"])

                if not (math.isnan(openPrice) or math.isnan(closePrice)):
                    coins.append(
                        {
                            "symbol": symbol,
                            "openPrice": openPrice,
                            "closePrice": closePrice,
                            "data": data,
                        }
                    )
        except (ValueError, TypeError) as e:
            print(f"Error processing coin {symbol}: {str(e)}")
            continue

    coinsWithRiseRate = [
        {
            **coin,
            "riseRate": (
                (coin["closePrice"] - coin["openPrice"]) / coin["openPrice"]
                if coin["openPrice"] != 0
                else 0
            ),
        }
        for coin in coins
    ]

    sortedByRiseRate = sorted(
        coinsWithRiseRate, key=lambda coin: coin["riseRate"], reverse=True
    )[:limit]

    return [coin["symbol"] for coin in sortedByRiseRate]


async def findCommonCoins(
    byValueSymbols: list, byRiseSymbols: list, filterType: str = "value"
):
    commonSymbols = list(filter(lambda symbol: symbol in byRiseSymbols, byValueSymbols))
    base = filterType == "value" and byValueSymbols or byRiseSymbols
    commonCoins = list(filter(lambda symbol: symbol in commonSymbols, base))
    return commonCoins


async def filterRisingAndGreenCandles(
    symbols: list, candlestickData: dict, minCandles: int = 3
) -> list:
    rising_and_green_coins = []  # 연속 상승하면서 양봉을 그리는 코인들을 저장할 배열

    try:
        for symbol in symbols:
            candleData = candlestickData[symbol]

            if (
                candleData["status"] == "0000"
                and candleData["data"]
                and len(candleData["data"]) >= minCandles
            ):
                recentCandles = candleData["data"][
                    -minCandles:
                ]  # 최근 minCandles 개의 캔들 데이터
                isRising = True
                isAllGreen = True

                for i in range(1, len(recentCandles)):
                    openPrice = float(recentCandles[i][1])
                    closePrice = float(recentCandles[i][2])
                    previousClosePrice = float(recentCandles[i - 1][2])

                    # 상승 조건과 양봉 조건 검사
                    if closePrice <= previousClosePrice:
                        isRising = False
                    if closePrice <= openPrice:
                        isAllGreen = False

                    # 어느 하나라도 조건을 만족하지 않으면 루프 중지
                    if not (isRising and isAllGreen):
                        break

                # 두 조건을 모두 만족하면 결과 배열에 추가
                if isRising and isAllGreen:
                    rising_and_green_coins.append(symbol)

    except Exception as error:
        print(f"Error in filterRisingAndGreenCandles: {error}")
        return ["error_filterRisingAndGreenCandles"]

    return rising_and_green_coins


async def performAnalysisAndNotify(type: Literal["long-term", "short-term"]):
    message = (
        type == "long-term"
        and await generateLongTermAnalysisMessage()
        or await generateShortTermAnalysisMessage()
    )

    await send_telegram_message(message, type)
    print("Message sent to Telegram Successfully.")


async def generateLongTermAnalysisMessage():
    print("Starting Generating Long Term Analysis Message")
    coinData = await bithumb.get_current_price()
    topValueCoins = await filterCoinsByValue(coinData, 100)
    topRiseRateCoins = await filterCoinsByRiseRate(coinData, 100)
    commonCoins = await findCommonCoins(topValueCoins, topRiseRateCoins)

    oneHourCandlestickData = await fetchAllCandlestickData(topValueCoins, "1h")
    oneHourContinuousRisingAndGreenCoins = await filterRisingAndGreenCandles(
        topValueCoins, oneHourCandlestickData
    )

    oneDayCandlestickData = await fetchAllCandlestickData(topRiseRateCoins, "1d")
    # oneDayContinuousRisingAndGreenCoins 에 뭔가 문제가 있음. 제대로 안나감.
    oneDayContinuousRisingAndGreenCoins = await filterRisingAndGreenCandles(
        topValueCoins, oneDayCandlestickData
    )

    coin_groups = [
        ("🔥 *거래량 + 상승률* 🔥", commonCoins[:20]),
        ("🟢 1h 지속 상승 + 지속 양봉 🟢", oneHourContinuousRisingAndGreenCoins),
        ("🟢 1d 지속 상승 + 지속 양봉 🟢", oneDayContinuousRisingAndGreenCoins),
    ]

    message = generate_message("Sustainability - Long Term", coin_groups)
    return message


async def generateShortTermAnalysisMessage():
    print("Starting Generating Short Term Analysis Message")
    coinData = await bithumb.get_current_price()
    topValueCoins = await filterCoinsByValue(coinData, 100)
    topRiseRateCoins = await filterCoinsByRiseRate(coinData, 100)
    commonCoins = await findCommonCoins(topValueCoins, topRiseRateCoins)

    oneMinuteCandlestickData = await fetchAllCandlestickData(topValueCoins, "1m")
    oneMinuteContinuousRisingAndGreenCoins = await filterRisingAndGreenCandles(
        topValueCoins, oneMinuteCandlestickData
    )

    tenMinutesCandlestickData = await fetchAllCandlestickData(topRiseRateCoins, "10m")
    tenMinutesContinuousRisingAndGreenCoins = await filterRisingAndGreenCandles(
        topValueCoins, tenMinutesCandlestickData
    )

    coin_groups = [
        ("🔥 *거래량 + 상승률* 🔥", commonCoins[:20]),
        ("🟢 1m 지속 상승 + 양봉 🟢", oneMinuteContinuousRisingAndGreenCoins),
        ("🟢 10m 지속 상승 + 양봉 🟢", tenMinutesContinuousRisingAndGreenCoins),
    ]

    message = generate_message("Sustainability - Short Term", coin_groups)
    return message
