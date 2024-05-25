from cmath import isnan
import json
import os

import httpx
import websockets
from dotenv import load_dotenv

from app.lib.bithumb_auth_header.xcoin_api_client import XCoinAPI

load_dotenv()

BASE_URL = "https://api.bithumb.com"


class BithumbService:
    def __init__(self):
        print("BithumbService init")

    # 현재가 정보 조회 (ALL)
    async def get_current_price(self, payment_currency: str = "KRW"):
        """
        Get Current Price Information (ALL)
        Provides current price information of virtual assets on Bithumb exchange at the time of request.

        Parameters:
            payment_currency (str): The payment currency (market). Input: KRW or BTC.

        Returns:
            dict: A dictionary containing current price information with the following structure:
                {
                    "status": str,  # Result status code (0000 for success, other error codes for failure)
                    "opening_price": float,  # Opening price at 00:00
                    "closing_price": float,  # Closing price at 00:00
                    "min_price": float,  # Lowest price at 00:00
                    "max_price": float,  # Highest price at 00:00
                    "units_traded": float,  # Trading volume at 00:00
                    "acc_trade_value": float,  # Trading value at 00:00
                    "prev_closing_price": float,  # Previous day's closing price
                    "units_traded_24H": float,  # Trading volume in the last 24 hours
                    "acc_trade_value_24H": float,  # Trading value in the last 24 hours
                    "fluctate_24H": float,  # Fluctuation range in the last 24 hours
                    "fluctate_rate_24H": float,  # Fluctuation rate in the last 24 hours
                    "date": int,  # Timestamp
                }

        """
        url = f"{BASE_URL}/public/ticker/ALL_{payment_currency}"
        headers = {"accept": "application/json"}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            return response.json()

    # 현재가 정보 조회 (자산별)
    async def get_current_price_by_asset(
        self, order_currency: str, payment_currency: str
    ):
        """
        Get Current Price Information (By Asset)
        Provides current price information of virtual assets on Bithumb exchange at the time of request.

        Parameters:
            order_currency (str): The cryptocurrency code. Input: ALL (all cryptocurrencies) or specific cryptocurrency code.
            payment_currency (str): The payment currency (market). Input: KRW or BTC.

        Returns:
            dict: A dictionary containing current price information with the following structure:
                {
                    "status": str,  # Result status code (0000 for success, other error codes for failure)
                    "opening_price": float,  # Opening price at 00:00
                    "closing_price": float,  # Closing price at 00:00
                    "min_price": float,  # Lowest price at 00:00
                    "max_price": float,  # Highest price at 00:00
                    "units_traded": float,  # Trading volume at 00:00
                    "acc_trade_value": float,  # Trading value at 00:00
                    "prev_closing_price": float,  # Previous day's closing price
                    "units_traded_24H": float,  # Trading volume in the last 24 hours
                    "acc_trade_value_24H": float,  # Trading value in the last 24 hours
                    "fluctate_24H": float,  # Fluctuation range in the last 24 hours
                    "fluctate_rate_24H": float,  # Fluctuation rate in the last 24 hours
                    "date": int,  # Timestamp
                }

        """
        url = f"{BASE_URL}/public/ticker/{order_currency}_{payment_currency}"
        headers = {"accept": "application/json"}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            return response.json()

    # 호가 정보 조회 (ALL)
    async def get_orderbook_all(
        self,
        payment_currency: str,
        # , count: int
    ):
        """
        Get Orderbook Information (ALL)
        Provides orderbook information of the exchange.

        Parameters:
            payment_currency (str): The payment currency (market). Input: KRW or BTC.
            count (int): Number of records to retrieve. Range: 1~5 for ALL, 1~30 for specific coins. Default: 5 for ALL, 30 for specific coins.

        Returns:
            dict: A dictionary containing transaction history with the following structure:
                {
                    "status": str,  # Result status code (0000 for success, other error codes for failure)
                    "timestamp": int,  # Timestamp
                    "order_currency": str,  # Order currency (coin)
                    "payment_currency": str,  # Payment currency (market)
                    "bids": list[dict],  # List of buy requests
                        [
                            {
                                "quantity": float,  # Quantity of currency
                                "price": float,  # Trading price
                            },
                            ...
                        ]
                    "asks": list[dict],  # List of sell requests
                        [
                            {
                                "quantity": float,  # Quantity of currency
                                "price": float,  # Trading price
                            },
                            ...
                        ]
                }

        """
        url = f"{BASE_URL}/public/orderbook/ALL_{payment_currency}"
        # params = {"count": count}
        headers = {"accept": "application/json"}
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                # params=params,
                headers=headers,
            )
            return response.json()

    # 호가 정보 조회 (자산별)
    async def get_orderbook(
        self,
        order_currency: str,
        payment_currency: str = "KRW",
        count: int = 30,
    ):
        """
        Get Orderbook Information (By Asset)
        Provides orderbook information of the exchange for a specific asset.

        Parameters:
            order_currency (str): The cryptocurrency code.
            payment_currency (str): The payment currency (market). Input: KRW or BTC.
            count (int): Number of records to retrieve. Range: 1~30. Default: 30.

        Returns:
            dict: A dictionary containing transaction history with the following structure:
                {
                    "status": str,  # Result status code (0000 for success, other error codes for failure)
                    "timestamp": int,  # Timestamp
                    "order_currency": str,  # Order currency (coin)
                    "payment_currency": str,  # Payment currency (market)
                    "bids": list[dict],  # List of buy requests
                        [
                            {
                                "quantity": float,  # Quantity of currency
                                "price": float,  # Trading price
                            },
                            ...
                        ]
                    "asks": list[dict],  # List of sell requests
                        [
                            {
                                "quantity": float,  # Quantity of currency
                                "price": float,  # Trading price
                            },
                            ...
                        ]
                }

        """
        url = f"{BASE_URL}/public/orderbook/{order_currency}_{payment_currency}"
        params = {"count": count}
        headers = {"accept": "application/json"}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, headers=headers)
            return response.json()

    # 최근 체결 내역
    async def get_transaction_history(
        self,
        order_currency: str,
        payment_currency: str,
        count: int = 20,
    ):
        """
        Get Recent Transaction History
        Provides recent transaction history of completed trades for virtual assets on the Bithumb exchange.

        Parameters:
            order_currency (str): The cryptocurrency code.
            payment_currency (str): The payment currency (market). Input: KRW or BTC.
            count (int): Number of records to retrieve. Range: 1~100. Default: 20.

        Returns:
            dict: A dictionary containing transaction history with the following structure:
                {
                    "status": str,  # Result status code (0000 for success, other error codes for failure)
                    "transaction_date": str,  # Transaction date timestamp (YYYY-MM-DD HH:MM:SS)
                    "type": str,  # Transaction type (bid: buy, ask: sell)
                    "units_traded": float,  # Quantity of currency traded
                    "price": float,  # Trading price
                    "total": float,  # Total transaction amount
                }

        """
        url = (
            f"{BASE_URL}/public/transaction_history/{order_currency}_{payment_currency}"
        )
        params = {"count": count}
        headers = {"accept": "application/json"}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, headers=headers)
            return response.json()

    # 네트워크 정보 조회
    async def get_network_info(self):
        """
        Get Network Information
        Provides information about the deposit/withdrawal status of virtual assets.

        Returns:
            dict: A dictionary containing network information with the following structure:
                {
                    "status": str,  # Result status code (0000 for success, other error codes for failure)
                    "net_type": str,  # Network type code for deposit/withdrawal (e.g., "btc" for Bitcoin)
                    "net_name": str,  # Network name for deposit/withdrawal (e.g., "Bitcoin")
                }

        """
        url = f"{BASE_URL}/public/network-info"
        headers = {"accept": "application/json"}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            return response.json()

    # 입/출금 지원 현황 조회
    async def get_assets_status(self, currency: str):
        """
        Get Asset Status
        Provides information about the deposit/withdrawal status of virtual assets.

        Parameters:
            currency (str): The cryptocurrency code.

        Returns:
            dict: A dictionary containing asset status information with the following structure:
                {
                    "status": str,  # Result status code (0000 for success, other error codes for failure)
                    "currency": str,  # Virtual asset code in English (e.g., "BTC" for Bitcoin)
                    "net_type": str,  # Network type code for deposit/withdrawal (e.g., "btc" for Bitcoin)
                    "deposit_status": int,  # Deposit availability status (1: available, 0: not available)
                    "withdrawal_status": int,  # Withdrawal availability status (1: available, 0: not available)
                }

        """
        url = f"{BASE_URL}/public/assetsstatus/multichain/{currency}"
        headers = {"accept": "application/json"}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            return response.json()

    # 코인 출금 최소 수량 조회
    async def get_minimum_withdrawal(self, currency: str):
        """
        Get Minimum Withdrawal Amount
        Provides information about the minimum withdrawal quantity for each cryptocurrency.

        Parameters:
            currency (str): The cryptocurrency code.

        Returns:
            dict: A dictionary containing information about the minimum withdrawal quantity for the specified cryptocurrency with the following structure:
                {
                    "status": str,  # Result status code (0000 for success, other error codes for failure)
                    "currency": str,  # Virtual asset code in English (e.g., "BTC" for Bitcoin)
                    "net_type": str,  # Withdrawal network type code (e.g., "btc" for Bitcoin)
                    "minimum": float,  # Minimum withdrawal quantity for the specified cryptocurrency
                }

        """
        url = f"{BASE_URL}/public/withdraw/minimum/{currency}"
        headers = {"accept": "application/json"}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            return response.json()

    # 캔들스틱 정보 조회
    async def get_candlestick_data(
        self, order_currency: str, payment_currency: str, chart_intervals: str
    ):
        """
        Get Candlestick Data
        Provides price and volume information for virtual asset trading on the Bithumb exchange based on time and interval.

        Parameters:
            order_currency (str): The cryptocurrency code.
            payment_currency (str): The payment currency (market).
            chart_intervals (str): Chart interval (e.g., 1m, 3m, 5m, 10m, 30m, 1h, 6h, 12h, 24h).

        Returns:
            dict: A dictionary containing candlestick data with the following structure:
                {
                    "status": str,  # Result status code (0000 for success, other error codes for failure)
                    "data": [
                        [
                            int,  # Timestamp of the data point
                            float,  # Opening price
                            float,  # Closing price
                            float,  # Highest price
                            float,  # Lowest price
                            float  # Trading volume
                        ],
                        ...
                    ]
                }
        """
        url = f"{BASE_URL}/public/candlestick/{order_currency}_{payment_currency}/{chart_intervals}"
        headers = {"accept": "application/json"}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            return response.json()

    async def bithumb_ws_client(self, subscribe_type, symbols, tick_types=None):
        uri = "wss://pubwss.bithumb.com/pub/ws"

        # 동적 구독 요청 메시지 생성
        subscribe_message = {"type": subscribe_type, "symbols": symbols}

        # tick_types가 제공되는 경우 메시지에 추가
        if tick_types:
            subscribe_message["tickTypes"] = tick_types

        async with websockets.connect(uri) as websocket:
            # 구독 요청 메시지 전송
            await websocket.send(json.dumps(subscribe_message))
            print(
                f"bithumb_ws_client: Subscribed to {subscribe_type} for {symbols} with tick types {tick_types}"
            )

            # 서버로부터 메시지 수신 및 출력
            while True:
                message = await websocket.recv()
                message_data = json.loads(message)
                print(f"bithumb_ws_client: Received message: {message_data}")

    async def filter_coins_by_value(self, coins_data: dict, limit: int = 100):
        """
        Filter coins by 24-hour trading value and return the top N coins.

        Parameters:
            coins_data (dict): The dictionary containing current price information of all coins.
                {
                    "status": "0000",
                    "data": {
                        "BTC": {
                            "opening_price": "92804000",
                            "closing_price": "93565000",
                            "min_price": "92585000",
                            "max_price": "93900000",
                            "units_traded": "359.38654768",
                            "acc_trade_value": "33489632722.73385",
                            "prev_closing_price": "92826000",
                            "units_traded_24H": "478.53544545",
                            "acc_trade_value_24H": "44569497270.86515",
                            "fluctate_24H": "385000",
                            "fluctate_rate_24H": "0.41"
                        },
                        "ETH": {
                            "opening_price": "4311000",
                            "closing_price": "4310000",
                            "min_price": "4294000",
                            "max_price": "4351000",
                            "units_traded": "3147.895641287358349337",
                            "acc_trade_value": "13607234885.237061815493005",
                            "prev_closing_price": "4314000",
                            "units_traded_24H": "4829.017820891019106504",
                            "acc_trade_value_24H": "20879803821.046096267234167",
                            "fluctate_24H": "-44000",
                            "fluctate_rate_24H": "-1.01"
                        },
                        ...
                        "date": "1716119655233"
                    }
                }
            limit (int): The number of top coins to return based on trading value.

        Returns:
            list: A list of symbols of the top N coins sorted by 24-hour trading value.
        """
        if coins_data["status"] != "0000":
            return []  # Return an empty list if the request was not successful

        # Extract and sort the coins by their 24-hour trading value
        coins = [
            {
                "symbol": key,
                "trade_volume": float(value["units_traded_24H"]),
                "trade_value": float(value["acc_trade_value_24H"]),
                "data": value,
            }
            for key, value in coins_data["data"].items()
            if key != "date"
            and value["units_traded_24H"]
            and value["acc_trade_value_24H"]
        ]

        # Filter out coins with invalid trade volume or value
        valid_coins = [
            coin
            for coin in coins
            if not (isnan(coin["trade_volume"]) or isnan(coin["trade_value"]))
        ]

        # Sort by trade value and get the top N coins
        sorted_by_value = sorted(
            valid_coins, key=lambda coin: coin["trade_value"], reverse=True
        )[:limit]

        return [coin["symbol"] for coin in sorted_by_value]


class BithumbPrivateService:
    def __init__(self):
        print("BithumbPrivateService init")
        self.api_key = os.getenv("BITHUMB_CON_KEY")
        self.api_secret = os.getenv("BITHUMB_SEC_KEY")
        self.auth_api = XCoinAPI(self.api_key, self.api_secret)

    # 회원 정보 조회
    async def get_account_info(
        self, order_currency: str = "BTC", payment_currency: str = "KRW"
    ):
        """
        회원 정보 조회 (Account Information)
        Fetches user information and coin trading fee information.

        Parameters:
            order_currency (str): The order currency (coin).
            payment_currency (str): The payment currency (market), default 'KRW' or 'BTC'.

        Returns:
            dict: A dictionary containing information about the user's account with the following structure:
                {
                    "status": str,  # Result status code (0000 for success, other error codes for failure)
                    "created": int,  # Timestamp of account registration
                    "account_id": str,  # User account ID
                    "order_currency": str,  # Order currency (coin)
                    "payment_currency": str,  # Payment currency (market)
                    "trade_fee": float,  # Trading fee rate
                    "balance": float,  # Available order quantity
                }

        """
        # url = f"{BASE_URL}/info/account"
        # headers = {
        #     "accept": "application/json",
        #     "content-type": "application/x-www-form-urlencoded",
        #     "Api-Key": self.api_key,
        #     "Api-Nonce": str(int(time.time() * 1000)),
        #     "Api-Sign": self.auth_api.xcoin_api_call(
        #         "/info/account",
        #         {
        #             "order_currency": order_currency,
        #             "payment_currency": payment_currency,
        #         },
        #     ),  # You will need to define the `create_signature` function based on your API secret and encoding requirements.
        # }
        # async with httpx.AsyncClient() as client:
        #     response = await client.post(url, headers=headers, data=data)
        #     return response.json()
        # result = await api.xcoin_api_call(rgParams["endpoint"], rgParams)
        params = {
            "endpoint": "/info/account",
            "order_currency": order_currency,
            "payment_currency": payment_currency,
        }
        result = await self.auth_api.xcoin_api_call(params["endpoint"], params)
        return result

    # 보유자산 조회
    async def get_balance(self, currency: str = "BTC"):
        """
        보유자산 조회 (Balance Inquiry)
        Fetches user's asset information.

        Parameters:
            currency (str): The cryptocurrency code, default 'BTC'.

        Returns:
            dict: A dictionary containing information about the user's asset status with the following structure:
                {
                    "status": str,  # Result status code (0000 for success, other error codes for failure)
                    "total_{currency}": float,  # Total quantity of virtual assets
                    "total_krw": float,  # Total amount in Korean Won (KRW)
                    "inuse_{currency}": float,  # Quantity of virtual assets locked in orders
                    "in_use_krw": float,  # Amount of KRW locked in orders
                    "available_{currency}": float,  # Available quantity of virtual assets for trading
                    "available_krw": float,  # Available amount of KRW for trading
                    "xcoinlast_{currency}": float  # Last traded amount in the specified currency
                }

        """
        # url = f"{BASE_URL}/info/balance"
        # headers = {
        #     "accept": "application/json",
        #     "content-type": "application/x-www-form-urlencoded",
        #     "Api-Key": self.api_key,
        #     "Api-Nonce": str(int(time.time() * 1000)),
        #     "Api-Sign": self.auth_api.xcoin_api_call(
        #         "/info/balance", {"currency": currency}
        #     ),  # You will need to define the `create_signature` function based on your API secret and encoding requirements.
        # }
        # data = {"currency": currency}
        # async with httpx.AsyncClient() as client:
        #     response = await client.post(url, data=data, headers=headers)
        #     return response.json()
        params = {
            "endpoint": "/info/balance",
            "currency": currency,
        }
        result = await self.auth_api.xcoin_api_call(params["endpoint"], params)
        return result

    # 입금 주소 조회
    async def get_wallet_address(
        self, currency: str = "BTC", net_type: str = "Bitcoin"
    ):
        """
        입금지갑 주소 조회 (Wallet Address Inquiry)
        Fetches user's coin deposit wallet address.

        Parameters:
            currency (str): The cryptocurrency code, default 'BTC'.
            net_type (str): The network code, default 'Bitcoin'.

        Returns:
            dict: A dictionary containing the following information about the user's wallet address:
                {
                    "status": str,  # Result status code (0000 for success, other error codes for failure)
                    "wallet_address": str,  # Wallet address for the specified virtual asset
                    "currency": str,  # Virtual asset code (same as Request Parameters data)
                    "net_type": str  # Network type (same as Request Parameters data)
                }

        """
        # url = f"{BASE_URL}/info/wallet_address"
        # headers = {
        #     "accept": "application/json",
        #     "content-type": "application/x-www-form-urlencoded",
        #     "Api-Key": self.api_key,
        #     "Api-Nonce": str(int(time.time() * 1000)),
        #     "Api-Sign": self.auth_api.xcoin_api_call(
        #         "/info/wallet_address", {"currency": currency, "net_type": net_type}
        #     ),  # You will need to define the `create_signature` function based on your API secret and encoding requirements.
        # }
        # data = {"currency": currency, "net_type": net_type}
        # async with httpx.AsyncClient() as client:
        #     response = await client.post(url, data=data, headers=headers)
        #     return response.json()
        params = {
            "endpoint": "/info/wallet_address",
            "currency": currency,
            "net_type": net_type,
        }
        result = await self.auth_api.xcoin_api_call(params["endpoint"], params)
        return result

    # 최근 거래정보 조회
    async def get_recent_transaction_info(
        self, order_currency: str = "BTC", payment_currency: str = "KRW"
    ):
        """
        최근 거래정보 조회 (Recent Transaction Information Inquiry)
        Fetches member's virtual asset trading information.

        Parameters:
            order_currency (str): The cryptocurrency code, default 'BTC'.
            payment_currency (str): The payment currency (market), default 'KRW'.

        Returns:
            dict: A dictionary containing the following information about the user's recent trading data:
                {
                    "status": str,  # Result status code (0000 for success, other error codes for failure)
                    "order_currency": str,  # Coin being traded
                    "payment_currency": str,  # Market currency
                    "opening_price": float,  # Member's starting trading price (last 24 hours)
                    "closing_price": float,  # Member's last trading price (last 24 hours)
                    "min_price": float,  # Member's lowest trading price (last 24 hours)
                    "max_price": float,  # Member's highest trading price (last 24 hours)
                    "average_price": float,  # Average price (last 24 hours)
                    "units_traded": float,  # Trading volume (last 24 hours)
                    "volume_1day": float,  # Currency trading volume (last 1 day)
                    "volume_7day": float,  # Currency trading volume (last 7 days)
                    "fluctate_24H": float,  # Fluctuation in the last 24 hours
                    "fluctate_rate_24H": float,  # Fluctuation rate in the last 24 hours
                    "Date": int  # Timestamp
                }

        """
        # url = f"{BASE_URL}/info/ticker"
        # headers = {
        #     "accept": "application/json",
        #     "content-type": "application/x-www-form-urlencoded",
        #     "Api-Key": self.api_key,
        #     "Api-Nonce": str(int(time.time() * 1000)),
        #     "Api-Sign": self.auth_api.xcoin_api_call(
        #         "/info/ticker",
        #         {
        #             "order_currency": order_currency,
        #             "payment_currency": payment_currency,
        #         },
        #     ),  # You will need to define the `create_signature` function based on your API secret and encoding requirements.
        # }
        # data = {"order_currency": order_currency, "payment_currency": payment_currency}
        # async with httpx.AsyncClient() as client:
        #     response = await client.post(url, data=data, headers=headers)
        #     return response.json()
        params = {
            "endpoint": "/info/ticker",
            "order_currency": order_currency,
            "payment_currency": payment_currency,
        }
        result = await self.auth_api.xcoin_api_call(params["endpoint"], params)
        return result

    # 거래 주문내역 조회
    async def get_order_history(
        self,
        order_currency: str = "BTC",
        payment_currency: str = "KRW",
        order_id: str = "",
        order_type: str = "",
        count: int = 100,
        after: int = 0,
    ):
        """
        거래 주문내역 조회 (Inquiry of Trading Order History)
        Provides information on member's buy/sell registration or ongoing history.

        Parameters:
            order_currency (str): The cryptocurrency code, default 'BTC'.
            payment_currency (str): The payment currency (market), default 'KRW'.
            order_id (str): The order ID registered for buy/sell (input to extract the corresponding data).
            order_type (str): The transaction type (bid: buy ask: sell).
            count (int): 1~1000 (default: 100).
            after (int): Extract data later than the input time (UNIX Timestamp format).

        Returns:
            dict: A dictionary containing the following information about the user's order:
                {
                    "status": str,  # Result status code (0000 for success, other error codes for failure)
                    "order_currency": str,  # Coin being traded
                    "payment_currency": str,  # Market currency
                    "order_id": str,  # Order number registered for buy/sell orders
                    "order_date": int,  # Timestamp of order registration
                    "type": str,  # Type of order request (bid: buy, ask: sell)
                    "watch_price": str,  # Price at which the order is being placed (for automatic orders)
                    "units": str,  # Currency being traded
                    "units_remaining": float,  # Remaining balance after order fulfillment
                    "price": float  # Price per unit of currency
                }

        """
        # url = f"{BASE_URL}/info/orders"
        # headers = {
        #     "accept": "application/json",
        #     "content-type": "application/x-www-form-urlencoded",
        #     "Api-Key": self.api_key,
        #     "Api-Nonce": str(int(time.time() * 1000)),
        #     "Api-Sign": self.auth_api.xcoin_api_call(
        #         "/info/orders",
        #         {
        #             "order_currency": order_currency,
        #             "payment_currency": payment_currency,
        #         },
        #     ),  # You will need to define the `create_signature` function based on your API secret and encoding requirements.
        # }
        # data = {
        #     "order_currency": order_currency,
        #     "payment_currency": payment_currency,
        #     "order_id": order_id,
        #     "type": order_type,
        #     "count": count,
        #     "after": after,
        # }
        # async with httpx.AsyncClient() as client:
        #     response = await client.post(url, data=data, headers=headers)
        #     return response.json()
        params = {
            "endpoint": "/info/orders",
            "order_currency": order_currency,
            "payment_currency": payment_currency,
            "order_id": order_id,
            "type": order_type,
            "count": count,
            "after": after,
        }
        result = await self.auth_api.xcoin_api_call(params["endpoint"], params)
        return result

    # 거래 주문내역 상세 조회
    async def get_order_detail(
        self, order_id: str, order_currency: str = "BTC", payment_currency: str = "KRW"
    ):
        """
        거래 주문내역 상세 조회 (Inquiry of Detailed Trading Order History)
        Provides detailed information on member's buy/sell settlement history.

        Parameters:
            order_id (str): The order ID registered for buy/sell (input to extract the corresponding data).
            order_currency (str): The cryptocurrency code, default 'BTC'.
            payment_currency (str): The payment currency (market), default 'KRW'.

        Returns:
            dict: A dictionary containing the following information about the user's order:
                {
                    "status": str,  # Result status code (0000 for success, other error codes for failure)
                    "order_date": int,  # Timestamp of order request
                    "type": str,  # Type of order request (bid: buy, ask: sell)
                    "order_status": str,  # Order status
                    "order_currency": str,  # Coin being traded
                    "payment_currency": str,  # Market currency
                    "watch_price": str,  # Price at which the order was placed (for automatic orders)
                    "order_price": float,  # Requested bid price
                    "order_qty": float,  # Requested quantity
                    "cancel_date": int,  # Timestamp of cancellation (if canceled)
                    "cancel_type": str,  # Type of cancellation
                    "contract": [  # List of contract details
                        {
                            "transaction_date": int,  # Timestamp of transaction
                            "price": float,  # Price per unit
                            "units": float,  # Quantity traded
                            "fee_currency": str,  # Currency of the fee
                            "fee": float,  # Transaction fee
                            "total": float  # Total transaction amount
                        }
                    ]
                }

        """
        # url = f"{BASE_URL}/info/order_detail"
        # headers = {
        #     "accept": "application/json",
        #     "content-type": "application/x-www-form-urlencoded",
        #     "Api-Key": self.api_key,
        #     "Api-Nonce": str(int(time.time() * 1000)),
        #     "Api-Sign": self.auth_api.xcoin_api_call(
        #         "/info/order_detail",
        #         {
        #             "order_id": order_id,
        #             "order_currency": order_currency,
        #             "payment_currency": payment_currency,
        #         },
        #     ),  # You will need to define the `create_signature` function based on your API secret and encoding requirements.
        # }
        # data = {
        #     "order_id": order_id,
        #     "order_currency": order_currency,
        #     "payment_currency": payment_currency,
        # }
        # async with httpx.AsyncClient() as client:
        #     response = await client.post(url, data=data, headers=headers)
        #     return response.json()
        params = {
            "endpoint": "/info/order_detail",
            "order_id": order_id,
            "order_currency": order_currency,
            "payment_currency": payment_currency,
        }
        result = await self.auth_api.xcoin_api_call(params["endpoint"], params)
        return result

    # 거래 체결내역 조회
    async def get_user_transactions(
        self,
        order_currency: str = "BTC",
        payment_currency: str = "KRW",
        offset: int = 0,
        count: int = 20,
        search_gb: int = 0,
    ):
        """
        거래 체결내역 조회 (Inquiry of Completed Transaction History)
        Provides information on member's completed transaction history.

        Parameters:
            offset (int): 0 or higher (default: 0).
            count (int): 1 to 50 (default: 20).
            search_gb (int): Search type.
                0: All
                1: Buy completed
                2: Sell completed
                3: Withdrawal in progress
                4: Deposit
                5: Withdrawal
                9: KRW deposit in progress (default: 0).
            order_currency (str): The cryptocurrency code (default: 'BTC').
            payment_currency (str): The payment currency (market), default 'KRW'.

        Returns:
            dict: A dictionary containing the following information about the user's transaction:
                {
                    "status": str,  # Result status code (0000 for success, other error codes for failure)
                    "search": str,  # Search criteria (0: all, 1: buy completed, 2: sell completed, 3: withdrawal in progress, 4: deposit, 5: withdrawal, 9: KRW deposit in progress)
                    "transfer_date": int,  # Timestamp of transaction
                    "order_currency": str,  # Coin being traded
                    "payment_currency": str,  # Market currency
                    "units": str,  # Quantity of traded currency
                    "price": float,  # Price per unit
                    "amount": float,  # Total transaction amount
                    "fee_currency": str,  # Currency of the fee
                    "fee": float,  # Transaction fee
                    "order_balance": float,  # Remaining balance of the traded currency
                    "payment_balance": float  # Remaining balance of the market currency
                }

        """
        # url = f"{BASE_URL}/info/user_transactions"
        # headers = {
        #     "accept": "application/json",
        #     "content-type": "application/x-www-form-urlencoded",
        #     "Api-Key": self.api_key,
        #     "Api-Nonce": str(int(time.time() * 1000)),
        #     "Api-Sign": self.auth_api.xcoin_api_call(
        #         "/info/user_transactions",
        #         {
        #             "offset": offset,
        #             "count": count,
        #             "searchGb": search_gb,
        #             "order_currency": order_currency,
        #             "payment_currency": payment_currency,
        #         },
        #     ),  # You will need to define the `create_signature` function based on your API secret and encoding requirements.
        # }
        # data = {
        #     "offset": offset,
        #     "count": count,
        #     "searchGb": search_gb,
        #     "order_currency": order_currency,
        #     "payment_currency": payment_currency,
        # }
        # async with httpx.AsyncClient() as client:
        #     response = await client.post(url, data=data, headers=headers)
        #     return response.json()
        params = {
            "endpoint": "/info/user_transactions",
            "offset": offset,
            "count": count,
            "searchGb": search_gb,
            "order_currency": order_currency,
            "payment_currency": payment_currency,
        }
        result = await self.auth_api.xcoin_api_call(params["endpoint"], params)
        return result

    # 지정가 주문하기
    async def place_limit_order(
        self,
        order_currency: str,
        payment_currency: str,
        units: float,
        price: int,
        order_type: str,
    ):
        """
        Place a limit order (지정가 주문하기)
        Provides functionality to register limit buy/sell orders.

        Parameters:
            order_currency (str): The cryptocurrency code.
            payment_currency (str): The payment currency (market).
            units (float): Order quantity.
            price (int): Price per unit.
            order_type (str): Type of transaction (bid: buy, ask: sell).

        Returns:
            dict: A dictionary containing the following information about the order:
                {
                    "status": str,  # Result status code (0000 for success, other error codes for failure)
                    "order_id": str  # Order number
                }

        """
        # url = f"{BASE_URL}/trade/place"
        # headers = {
        #     "accept": "application/json",
        #     "content-type": "application/x-www-form-urlencoded",
        #     "Api-Key": self.api_key,
        #     "Api-Nonce": str(int(time.time() * 1000)),
        #     "Api-Sign": self.auth_api.xcoin_api_call(
        #         "/trade/place",
        #         {
        #             "order_currency": order_currency,
        #             "payment_currency": payment_currency,
        #             "units": units,
        #             "price": price,
        #             "type": order_type,
        #         },
        #     ),  # You will need to define the `create_signature` function based on your API secret and encoding requirements.
        # }
        # data = {
        #     "order_currency": order_currency,
        #     "payment_currency": payment_currency,
        #     "units": units,
        #     "price": price,
        #     "type": order_type,
        # }
        # async with httpx.AsyncClient() as client:
        #     response = await client.post(url, data=data, headers=headers)
        #     return response.json()
        params = {
            "endpoint": "/trade/place",
            "order_currency": order_currency,
            "payment_currency": payment_currency,
            "units": units,
            "price": price,
            "type": order_type,
        }
        result = await self.auth_api.xcoin_api_call(params["endpoint"], params)
        return result

    # 시장가 매수하기
    async def market_buy(
        self,
        units: float,
        order_currency: str,
        payment_currency: str = "KRW",
    ):
        """
        Market buy (시장가 매수하기)
        Provides functionality to market buy.

        Parameters:
            units (float): Coin purchase quantity [maximum order amount: 10 billion KRW].
            order_currency (str): The cryptocurrency code.
            payment_currency (str): The payment currency (market).

        Returns:
            dict: A dictionary containing the following information about the order:
                {
                    "status": str,  # Result status code (0000 for success, other error codes for failure)
                    "order_id": str  # Order number
                }

        """
        # url = f"{BASE_URL}/trade/market_buy"
        # headers = {
        #     "accept": "application/json",
        #     "content-type": "application/x-www-form-urlencoded",
        #     "Api-Key": self.api_key,
        #     "Api-Nonce": str(int(time.time() * 1000)),
        #     "Api-Sign": self.auth_api.xcoin_api_call(
        #         "/trade/market_buy",
        #         {
        #             "units": units,
        #             "order_currency": order_currency,
        #             "payment_currency": payment_currency,
        #         },
        #     ),  # You will need to define the `create_signature` function based on your API secret and encoding requirements.
        # }
        # data = {
        #     "units": units,
        #     "order_currency": order_currency,
        #     "payment_currency": payment_currency,
        # }
        # async with httpx.AsyncClient() as client:
        #     response = await client.post(url, data=data, headers=headers)
        #     return response.json()
        params = {
            "endpoint": "/trade/market_buy",
            "units": units,
            "order_currency": order_currency,
            "payment_currency": payment_currency,
        }
        result = await self.auth_api.xcoin_api_call(params["endpoint"], params)
        return result

    # 시장가 매도하기
    async def market_sell(
        self,
        units: float,
        order_currency: str,
        payment_currency: str,
    ):
        """
        Market sell (시장가 매도하기)
        Provides functionality to market sell.

        Parameters:
            units (float): Coin sale quantity [maximum order amount: 10 billion KRW].
            order_currency (str): The cryptocurrency code.
            payment_currency (str): The payment currency (market).

        Returns:
            dict: A dictionary containing the following information about the order:
                {
                    "status": str,  # Result status code (0000 for success, other error codes for failure)
                    "order_id": str  # Order number
                }

        """
        # url = f"{BASE_URL}/trade/market_sell"
        # headers = {
        #     "accept": "application/json",
        #     "content-type": "application/x-www-form-urlencoded",
        #     "Api-Key": self.api_key,
        #     "Api-Nonce": str(int(time.time() * 1000)),
        #     "Api-Sign": self.auth_api.xcoin_api_call(
        #         "/trade/market_sell",
        #         {
        #             "units": units,
        #             "order_currency": order_currency,
        #             "payment_currency": payment_currency,
        #         },
        #     ),  # You will need to define the `create_signature` function based on your API secret and encoding requirements.
        # }
        # data = {
        #     "units": units,
        #     "order_currency": order_currency,
        #     "payment_currency": payment_currency,
        # }
        # async with httpx.AsyncClient() as client:
        #     response = await client.post(url, data=data, headers=headers)
        #     return response.json()

        if not isinstance(units, float):
            units = float(units)
        if not isinstance(order_currency, str):
            order_currency = str(order_currency)
        if not isinstance(payment_currency, str):
            payment_currency = str(payment_currency)

        params = {
            "endpoint": "/trade/market_sell",
            "units": units,
            "order_currency": order_currency,
            "payment_currency": payment_currency,
        }
        print(f"sell params: {params}")
        result = await self.auth_api.xcoin_api_call(params["endpoint"], params)
        return result

    # 자동 주문하기
    async def stop_limit_order(
        self,
        order_currency: str,
        payment_currency: str,
        watch_price: float,
        price: float,
        units: float,
        order_type: str,
    ):
        """
        Stop Limit Order (자동 주문하기)
        Provides functionality to place stop limit orders.

        Parameters:
            order_currency (str): The cryptocurrency code.
            payment_currency (str): The payment currency (market).
            watch_price (float): The price at which the order will be placed.
            price (float): The trading price.
            units (float): Order quantity [maximum order amount: 50 billion KRW].
            order_type (str): Order type (bid: buy, ask: sell).

        Returns:
            dict: A dictionary containing the following information about the order:
                {
                    "status": str,  # Result status code (0000 for success, other error codes for failure)
                    "order_id": str  # Order number
                }

        """
        # url = f"{BASE_URL}/trade/stop_limit"
        # headers = {
        #     "accept": "application/json",
        #     "content-type": "application/x-www-form-urlencoded",
        #     "Api-Key": self.api_key,
        #     "Api-Nonce": str(int(time.time() * 1000)),
        #     "Api-Sign": self.auth_api.xcoin_api_call(
        #         "/trade/stop_limit",
        #         {
        #             "order_currency": order_currency,
        #             "payment_currency": payment_currency,
        #             "watch_price": watch_price,
        #             "price": price,
        #             "units": units,
        #             "type": order_type,
        #         },
        #     ),  # You will need to define the `create_signature` function based on your API secret and encoding requirements.
        # }
        # data = {
        #     "order_currency": order_currency,
        #     "payment_currency": payment_currency,
        #     "watch_price": watch_price,
        #     "price": price,
        #     "units": units,
        #     "type": order_type,
        # }
        # async with httpx.AsyncClient() as client:
        #     response = await client.post(url, data=data, headers=headers)
        #     return response.json()
        params = {
            "endpoint": "/trade/stop_limit",
            "order_currency": order_currency,
            "payment_currency": payment_currency,
            "watch_price": watch_price,
            "price": price,
            "units": units,
            "type": order_type,
        }
        result = await self.auth_api.xcoin_api_call(params["endpoint"], params)
        return result

    # 주문 취소하기
    async def cancel_order(
        self,
        order_type: str,
        order_id: str,
        order_currency: str,
        payment_currency: str,
    ):
        """
        Cancel Order (주문 취소하기)
        Provides functionality to cancel registered buy/sell orders.

        Parameters:
            order_type (str): Transaction type (bid: buy, ask: sell).
            order_id (str): Order number registered for buy/sell.
            order_currency (str): The cryptocurrency code.
            payment_currency (str): The payment currency (market).

        Returns:
            dict: A dictionary containing the following information:
                {
                    "status": str  # Result status code (0000 for success, other error codes for failure)
                }

        """
        # url = f"{BASE_URL}/trade/cancel"
        # headers = {
        #     "accept": "application/json",
        #     "content-type": "application/x-www-form-urlencoded",
        #     "Api-Key": self.api_key,
        #     "Api-Nonce": str(int(time.time() * 1000)),
        #     "Api-Sign": self.auth_api.xcoin_api_call(
        #         "/trade/cancel",
        #         {
        #             "type": order_type,
        #             "order_id": order_id,
        #             "order_currency": order_currency,
        #             "payment_currency": payment_currency,
        #         },
        #     ),  # You will need to define the `create_signature` function based on your API secret and encoding requirements.
        # }
        # data = {
        #     "type": order_type,
        #     "order_id": order_id,
        #     "order_currency": order_currency,
        #     "payment_currency": payment_currency,
        # }
        # async with httpx.AsyncClient() as client:
        #     response = await client.post(url, data=data, headers=headers)
        #     return response.json()
        params = {
            "endpoint": "/trade/cancel",
            "type": order_type,
            "order_id": order_id,
            "order_currency": order_currency,
            "payment_currency": payment_currency,
        }
        result = await self.auth_api.xcoin_api_call(params["endpoint"], params)
        return result
