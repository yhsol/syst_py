#!/usr/bin/env python
# XCoin API-call sample script (for Python 3.X)
#
# @author    btckorea
# @date    2017-04-11
#
# 위의 설치 관련 주석은 필요에 따라 참고하되, 실제 코드 실행과는 무관

# RUN
# pipenv shell
# python app/lib/bithumb_auth_header/api_test.py

import os
import asyncio

from app.lib.bithumb_auth_header.xcoin_api_client import XCoinAPI
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("BITHUMB_CON_KEY")
api_secret = os.getenv("BITHUMB_SEC_KEY")

api = XCoinAPI(api_key, api_secret)

rgParams = {
    "endpoint": "/info/ticker",  # <-- endpoint가 가장 처음으로 와야 한다.
    "order_currency": "BTC",
}


async def main():
    result = await api.xcoin_api_call(rgParams["endpoint"], rgParams)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
