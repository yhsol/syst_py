import pandas as pd
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

    def compute_signals(self, df, entry_length=20, exit_length=10):
        df["upper"] = df["high"].rolling(window=entry_length).max()
        df["lower"] = df["low"].rolling(window=entry_length).min()
        df["exit_upper"] = df["high"].rolling(window=exit_length).max()
        df["exit_lower"] = df["low"].rolling(window=exit_length).min()

        df["long_entry"] = df["high"] > df["upper"].shift(1)
        df["short_entry"] = df["low"] < df["lower"].shift(1)
        df["long_exit"] = df["low"] < df["exit_lower"].shift(1)
        df["short_exit"] = df["high"] > df["exit_upper"].shift(1)

        return df

    def determine_signal_status(self, filtered_signals, signal_columns):
        if filtered_signals.empty:
            return "No active signal.", "No active signal."

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

        return latest_signal_status, last_true_signal_status

    async def analyze_currency(
        self, order_currency, payment_currency="KRW", chart_intervals="1h"
    ):
        data = await self.bithumb_service.get_candlestick_data(
            order_currency, payment_currency, chart_intervals
        )

        if data["status"] != "0000":
            return {"status": "error", "message": "Data retrieval failed"}

        df = self.process_candles(data)
        signals = self.compute_signals(df)
        signal_columns = ["long_entry", "short_entry", "long_exit", "short_exit"]

        filtered_signals = signals[["timestamp"] + signal_columns]
        filtered_signals = filtered_signals.sort_values(by="timestamp", ascending=False)

        latest_signal_status, last_true_signal_status = self.determine_signal_status(
            filtered_signals, signal_columns
        )

        return {
            "ticker": order_currency,
            "status": "success",
            "latest_signal_type": latest_signal_status,
            "last_true_signal_type": last_true_signal_status,
            "data": filtered_signals.head(20).to_dict(orient="records"),
        }
