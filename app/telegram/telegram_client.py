from typing import Literal

import os
import httpx


async def send_telegram_message(
    message: str, term_type: Literal["long-term", "short-term"]
):
    is_long_term = term_type == "long-term"
    telegram_bot_token = (
        os.getenv("TELEGRAM_LONG_TERM_BOT_TOKEN")
        if is_long_term
        else os.getenv("TELEGRAM_BOT_TOKEN")
    )
    chat_id = os.getenv("TELEGRAM_BOT_ID")

    url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            )
            response.raise_for_status()  # 이 부분은 요청이 실패했을 때 예외를 발생시킵니다.
    except httpx.RequestError as error:
        print(f"❌ error: Telegram send error: {error}")


def format_trading_view_link(coin):
    return f"[{coin}](https://kr.tradingview.com/chart/m0kspXtg/?symbol=BITHUMB%3A{coin}KRW)"


def generate_message(head_title, coin_groups):
    sections = []
    for title, coins in coin_groups:
        links = ", ".join(format_trading_view_link(coin) for coin in coins)
        sections.append(f"*{title}*\n{links}\n")

    header = f"🐅 {head_title}\n" + "🐅\n" * 4
    footer = "🐅\n" * 5
    body = "\n".join(sections)

    return f"{header}\n\n{body}\n\n{footer}"
