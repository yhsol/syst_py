import pandas as pd
import numpy as np
import pytz

from app.services.bithumb_service import BithumbService


class StrategyService:
    def __init__(self, strategy: str, bithumb_service: BithumbService):
        self.strategy = strategy
        self.bithumb_service = bithumb_service

    def process_candles(self, data):
        df = pd.DataFrame(
            data["data"],
            columns=["timestamp", "open", "close", "high", "low", "volume"],
        )
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)

        # Convert timestamps to datetime objects
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

        # Convert UTC to KST
        kst = pytz.timezone("Asia/Seoul")
        df["timestamp"] = df["timestamp"].dt.tz_localize("UTC").dt.tz_convert(kst)
        df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")

        return df

    def compute_moving_averages(self, df, short_window=50, long_window=200):
        df["short_ma"] = df["close"].rolling(window=short_window).mean()
        df["long_ma"] = df["close"].rolling(window=long_window).mean()
        return df

    def compute_vwma(self, df, length=20):
        df["typical_price"] = (df["close"] + df["high"] + df["low"]) / 3
        df["vwap"] = (df["typical_price"] * df["volume"]).rolling(
            window=length
        ).sum() / df["volume"].rolling(window=length).sum()
        return df

    def compute_atr(self, df, window=14):
        df["high-low"] = df["high"] - df["low"]
        df["high-close"] = (df["high"] - df["close"].shift()).abs()
        df["low-close"] = (df["low"] - df["close"].shift()).abs()
        df["true_range"] = df[["high-low", "high-close", "low-close"]].max(axis=1)
        df["atr"] = df["true_range"].rolling(window=window).mean()
        return df

    def compute_signals(
        self,
        df,
        entry_length=20,
        exit_length=10,
        short_window=50,
        long_window=200,
        atr_window=14,
        vwma_length=20,
    ):
        try:
            # 기본 터틀 트레이딩 시그널
            df["high"] = pd.to_numeric(df["high"], errors="coerce")
            df["low"] = pd.to_numeric(df["low"], errors="coerce")
            df["close"] = pd.to_numeric(df["close"], errors="coerce")
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce")

            df["upper"] = df["high"].rolling(window=entry_length).max()
            df["lower"] = df["low"].rolling(window=entry_length).min()
            df["exit_upper"] = df["high"].rolling(window=exit_length).max()
            df["exit_lower"] = df["low"].rolling(window=exit_length).min()
            df["long_entry"] = df["high"] > df["upper"].shift(1)
            df["short_entry"] = df["low"] < df["lower"].shift(1)
            df["long_exit"] = df["low"] < df["exit_lower"].shift(1)
            df["short_exit"] = df["high"] > df["exit_upper"].shift(1)

            # 이동평균선
            df["short_ma"] = df["close"].rolling(window=short_window).mean()
            df["long_ma"] = df["close"].rolling(window=long_window).mean()
            df["ma_condition"] = df["short_ma"] > df["long_ma"]

            # VWMA
            df["typical_price"] = (df["close"] + df["high"] + df["low"]) / 3
            df["vwap"] = (df["typical_price"] * df["volume"]).rolling(
                window=vwma_length
            ).sum() / df["volume"].rolling(window=vwma_length).sum()
            df["vwma_condition"] = df["close"] > df["vwap"]

            # ATR
            df["high-low"] = df["high"] - df["low"]
            df["high-close"] = (df["high"] - df["close"].shift()).abs()
            df["low-close"] = (df["low"] - df["close"].shift()).abs()
            df["true_range"] = df[["high-low", "high-close", "low-close"]].max(axis=1)
            df["atr"] = df["true_range"].rolling(window=atr_window).mean()

            # 최종 시그널
            df["long_entry"] = (
                df["long_entry"] & df["ma_condition"] & df["vwma_condition"]
            )
            df["long_exit"] = df["long_exit"]

            return df
        except Exception as e:
            print(f"Error in compute_signals: {e}")
            return df

    def compute_channel_breakout_signals(self, df, length=5):
        df["upBound"] = df["high"].rolling(window=length).max()
        df["downBound"] = df["low"].rolling(window=length).min()
        df["long_entry"] = df["close"] > df["upBound"].shift(1)
        df["short_entry"] = df["close"] < df["downBound"].shift(1)
        return df

    async def analyze_currency_by_channel_breakout(
        self, order_currency, payment_currency="KRW", chart_intervals="1h", length=5
    ):
        data = await self.bithumb_service.get_candlestick_data(
            order_currency, payment_currency, chart_intervals
        )

        if data["status"] != "0000":
            return {"status": "error", "message": "Data retrieval failed"}

        df = self.process_candles(data)
        df = self.compute_channel_breakout_signals(df, length)
        signal_columns = ["long_entry", "short_entry"]

        if not set(signal_columns).issubset(df.columns):
            return {
                "status": "error",
                "message": f"Missing expected signal columns in DataFrame",
            }

        filtered_signals = df[["timestamp"] + signal_columns]
        filtered_signals = filtered_signals.sort_values(by="timestamp", ascending=False)

        signal_status = self.determine_signal_status(filtered_signals, signal_columns)

        return {
            "ticker": order_currency,
            "status": "success",
            "type_latest_signal": signal_status["latest"],
            "type_last_true_signal": signal_status["last_true"],
            "type_last_true_timestamp": signal_status["last_true_timestamp"],
            "data": filtered_signals.head(20).to_dict(orient="records"),
        }

    def determine_signal_status(self, filtered_signals, signal_columns) -> dict:
        if filtered_signals.empty:
            return {
                "latest": "No active signal.",
                "last_true": "No active signal.",
                "last_true_timestamp": None,
            }

        # 가장 최근 시그널 상태
        latest_signal_status = "No active signal."
        latest_signals = filtered_signals.iloc[0]
        if any(latest_signals[col] for col in signal_columns):
            latest_signal_status = "Signal detected: " + ", ".join(
                col for col in signal_columns if latest_signals[col]
            )

        # 가장 최근 True 시그널 상태
        last_true_signals = filtered_signals[
            filtered_signals[signal_columns].any(axis=1)
        ]
        if last_true_signals.empty:
            last_true_signal_status = "No active signal."
        else:
            last_true_signals = last_true_signals.iloc[0]
            last_true_signal_status = "Signal detected: " + ", ".join(
                col for col in signal_columns if last_true_signals[col]
            )

        last_true_signal_timestamp = (
            last_true_signals["timestamp"] if not last_true_signals.empty else None
        )

        return {
            "latest": latest_signal_status,
            "last_true": last_true_signal_status,
            "last_true_timestamp": last_true_signal_timestamp,
        }

    async def analyze_currency_by_turtle(
        self, order_currency, payment_currency="KRW", chart_intervals="1h"
    ):
        data = await self.bithumb_service.get_candlestick_data(
            order_currency, payment_currency, chart_intervals
        )

        if data["status"] != "0000":
            return {"status": "error", "message": "Data retrieval failed"}

        df = self.process_candles(data)
        df = self.compute_signals(df)
        signal_columns = ["long_entry", "long_exit", "short_entry", "short_exit"]

        if not set(signal_columns).issubset(df.columns):
            return {
                "status": "error",
                "message": f"Missing expected signal columns in DataFrame",
            }

        filtered_signals = df[["timestamp"] + signal_columns]
        filtered_signals = filtered_signals.sort_values(by="timestamp", ascending=False)

        signal_status = self.determine_signal_status(filtered_signals, signal_columns)

        return {
            "ticker": order_currency,
            "status": "success",
            "type_latest_signal": signal_status["latest"],
            "type_last_true_signal": signal_status["last_true"],
            "type_last_true_timestamp": signal_status["last_true_timestamp"],
            "data": filtered_signals.head(20).to_dict(orient="records"),
        }

    async def vwma(
        self,
        order_currency: str,
        payment_currency: str,
        length: int,
        chart_intervals: str,
    ):
        price_data = await self.bithumb_service.get_candlestick_data(
            order_currency, payment_currency, chart_intervals
        )

        if price_data["status"] != "0000":
            raise ValueError("Failed to fetch data for VWMA calculation")

        data = price_data["data"]
        df = pd.DataFrame(
            data,
            columns=[
                "timestamp",
                "opening_price",
                "closing_price",
                "high_price",
                "low_price",
                "units_traded",
            ],
        )

        # 문자열 데이터를 숫자로 변환
        df["closing_price"] = df["closing_price"].astype(float)
        df["units_traded"] = df["units_traded"].astype(float)

        df["volume"] = df["units_traded"]
        df["close"] = df["closing_price"]

        price_volume = df["close"] * df["volume"]
        df["VWMA"] = (
            price_volume.rolling(window=length).sum()
            / df["volume"].rolling(window=length).sum()
        )

        return df[["timestamp", "VWMA"]]

    async def get_atr(self, symbol: str, atr_window: int = 14):
        candlestick_data = await self.bithumb_service.get_candlestick_data(
            symbol, "KRW", "1d"
        )
        if candlestick_data["status"] != "0000":
            return 0  # 데이터가 유효하지 않은 경우 0 반환

        df = pd.DataFrame(
            candlestick_data["data"],
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["high-low"] = df["high"] - df["low"]
        df["high-close"] = (df["high"] - df["close"].shift()).abs()
        df["low-close"] = (df["low"] - df["close"].shift()).abs()
        df["true_range"] = df[["high-low", "high-close", "low-close"]].max(axis=1)
        atr = df["true_range"].rolling(window=atr_window).mean().iloc[-1]
        return atr
