import math
from typing import Literal
from app.services.bithumb_service import BithumbService
from app.telegram.telegram_client import send_telegram_message, generate_message

bithumb = BithumbService()


async def fetch_all_candlestickdata(symbols: list, chart_intervals: str = "1h"):
    candlestick_data = {}
    for symbol in symbols:
        data = await bithumb.get_candlestick_data(symbol, "KRW", chart_intervals)
        candlestick_data[symbol] = data
    return candlestick_data


async def filter_coins_by_value(coin_data, limit=100):
    coins = []
    for key, value in coin_data.get(
        "data", {}
    ).items():  # .get()을 사용하여 "data"가 없는 경우에 대비
        try:
            # value가 실제로 딕셔너리인지 확인
            if not isinstance(value, dict):
                continue

            trade_volume = float(
                value.get("units_traded_24H", 0)
            )  # .get()을 사용해 키가 없는 경우 0을 반환
            trade_value = float(value.get("acc_trade_value_24H", 0))

            # NaN 체크를 하고 유효한 값만 리스트에 추가
            if not (math.isnan(trade_volume) or math.isnan(trade_value)):
                coins.append(
                    {
                        "symbol": key,
                        "tradeVolume": trade_volume,
                        "tradeValue": trade_value,
                        "data": value,
                    }
                )
        except (ValueError, TypeError) as e:
            print(f"❌ error: Error processing coin {key}: {str(e)}")
            continue  # 변환 실패 시 다음 코인으로 넘어감

    # 거래대금 기준으로 정렬하고 상위 limit 개 코인을 반환
    sorted_coins = sorted(coins, key=lambda coin: coin["tradeValue"], reverse=True)
    return [coin["symbol"] for coin in sorted_coins[:limit]]


async def filter_coins_by_rise_rate(coin_data, limit):
    coins = []
    for symbol, data in coin_data.get("data", {}).items():
        try:
            if (
                isinstance(data, dict)
                and "opening_price" in data
                and "closing_price" in data
            ):
                open_price = float(data["opening_price"])
                close_price = float(data["closing_price"])

                if not (math.isnan(open_price) or math.isnan(close_price)):
                    coins.append(
                        {
                            "symbol": symbol,
                            "openPrice": open_price,
                            "closePrice": close_price,
                            "data": data,
                        }
                    )
        except (ValueError, TypeError) as e:
            print(f"❌ error: Error processing coin {symbol}: {str(e)}")
            continue

    coins_with_rise_rate = [
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

    sorted_by_rise_rate = sorted(
        coins_with_rise_rate, key=lambda coin: coin["riseRate"], reverse=True
    )[:limit]

    return [coin["symbol"] for coin in sorted_by_rise_rate]


async def find_common_coins(
    by_value_symbols: list, by_rise_symbols: list, filter_type: str = "value"
):
    common_symbols = list(
        filter(lambda symbol: symbol in by_rise_symbols, by_value_symbols)
    )
    base = filter_type == "value" and by_value_symbols or by_rise_symbols
    common_coins = list(filter(lambda symbol: symbol in common_symbols, base))
    return common_coins


async def filter_rising_and_green_candles(
    symbols: list, candlestick_data: dict, min_candles: int = 3
) -> list:
    rising_and_green_coins = []  # 연속 상승하면서 양봉을 그리는 코인들을 저장할 배열

    try:
        for symbol in symbols:

            if symbol not in candlestick_data:
                continue

            candle_data = candlestick_data[symbol]

            if (
                candle_data["status"] == "0000"
                and candle_data["data"]
                and len(candle_data["data"]) >= min_candles
            ):
                recent_candles = candle_data["data"][
                    -min_candles:
                ]  # 최근 minCandles 개의 캔들 데이터
                is_rising = True
                is_all_green = True

                for i in range(1, len(recent_candles)):
                    open_price = float(recent_candles[i][1])
                    close_price = float(recent_candles[i][2])
                    previous_close_price = float(recent_candles[i - 1][2])

                    # 상승 조건과 양봉 조건 검사
                    if close_price <= previous_close_price:
                        is_rising = False
                    if close_price <= open_price:
                        is_all_green = False

                    # 어느 하나라도 조건을 만족하지 않으면 루프 중지
                    if not (is_rising and is_all_green):
                        break

                # 두 조건을 모두 만족하면 결과 배열에 추가
                if is_rising and is_all_green:
                    rising_and_green_coins.append(symbol)

    except ValueError as error:
        print(f"❌ error: Error in filterRisingAndGreenCandles: {error}")
        return ["error_filterRisingAndGreenCandles"]
    except TypeError as error:
        print(f"❌ error: Error in filterRisingAndGreenCandles: {error}")
        return ["error_filterRisingAndGreenCandles"]

    return rising_and_green_coins


async def perform_analysis_and_notify(term_type: Literal["long-term", "short-term"]):
    message = (
        term_type == "long-term"
        and await generate_long_term_analysis_message()
        or await generate_short_term_analysis_message()
    )

    await send_telegram_message(message, term_type)
    print("✅ success: Message sent to Telegram Successfully.")


async def generate_long_term_analysis_message():
    print("🏃 start: Starting Generating Long Term Analysis Message")
    coin_data = await bithumb.get_current_price()
    top_value_coins = await filter_coins_by_value(coin_data, 100)
    top_rise_rate_coins = await filter_coins_by_rise_rate(coin_data, 100)
    common_coins = await find_common_coins(top_value_coins, top_rise_rate_coins)

    one_hour_candlestick_data = await fetch_all_candlestickdata(top_value_coins, "1h")
    one_hour_continuous_rising_and_green_coins = await filter_rising_and_green_candles(
        top_value_coins, one_hour_candlestick_data
    )

    one_day_candlestick_data = await fetch_all_candlestickdata(
        top_rise_rate_coins, "1d"
    )
    # oneDayContinuousRisingAndGreenCoins 에 뭔가 문제가 있음. 제대로 안나감.
    one_day_continuous_rising_and_green_coins = await filter_rising_and_green_candles(
        top_value_coins, one_day_candlestick_data
    )

    coin_groups = [
        ("🔥 *거래량 + 상승률* 🔥", common_coins[:20]),
        ("🟢 1h 지속 상승 + 지속 양봉 🟢", one_hour_continuous_rising_and_green_coins),
        ("🟢 1d 지속 상승 + 지속 양봉 🟢", one_day_continuous_rising_and_green_coins),
    ]

    message = generate_message("Sustainability - Long Term", coin_groups)
    return message


async def generate_short_term_analysis_message():
    print("🏃 start: Starting Generating Short Term Analysis Message")
    coin_data = await bithumb.get_current_price()
    top_value_coins = await filter_coins_by_value(coin_data, 100)
    top_rise_rate_coins = await filter_coins_by_rise_rate(coin_data, 100)
    common_coins = await find_common_coins(top_value_coins, top_rise_rate_coins)

    one_minute_candlestick_data = await fetch_all_candlestickdata(top_value_coins, "1m")
    one_minute_continuous_rising_and_green_coins = (
        await filter_rising_and_green_candles(
            top_value_coins, one_minute_candlestick_data
        )
    )

    ten_minute_candlestick_data = await fetch_all_candlestickdata(
        top_rise_rate_coins, "10m"
    )
    ten_minute_continuous_rising_and_green_coins = (
        await filter_rising_and_green_candles(
            top_value_coins, ten_minute_candlestick_data
        )
    )

    coin_groups = [
        ("🔥 *거래량 + 상승률* 🔥", common_coins[:20]),
        ("🟢 1m 지속 상승 + 양봉 🟢", one_minute_continuous_rising_and_green_coins),
        ("🟢 10m 지속 상승 + 양봉 🟢", ten_minute_continuous_rising_and_green_coins),
    ]

    message = generate_message("Sustainability - Short Term", coin_groups)
    return message
