import os

import pandas as pd

from shared.types.packets import Candle


class CSVPriceFeedAdapter:
    data: pd.DataFrame | None

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.data = None
        self._load_data()

    def _load_data(self):
        """Load data from CSV. Expects: timestamp, open, high, low, close, volume."""
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"CSV file not found: {self.file_path}")

        self.data = pd.read_csv(self.file_path)
        assert self.data is not None
        self.data["timestamp"] = pd.to_datetime(self.data["timestamp"])
        self.data.set_index("timestamp", inplace=True)
        self.data.sort_index(inplace=True)

    def resample(self, timeframe: str) -> pd.DataFrame:
        """
        Resample data to a different timeframe.
        Examples: '1H', '4H', '1D', '15T'
        """
        resampled = (
            self.data.resample(timeframe)
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }
            )
            .dropna()
        )
        return resampled

    def get_candles(self, timeframe: str | None = None) -> list[Candle]:
        """Get a list of standardized Candle objects."""
        df = self.resample(timeframe) if timeframe else self.data
        candles = []
        for ts, row in df.iterrows():
            candles.append(
                Candle(
                    timestamp=ts.to_pydatetime(),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )
        return candles

    def get_last_n_days(self, days: int, timeframe: str | None = None) -> list[Candle]:
        """Filter data for the last N days."""
        if self.data.empty:
            return []

        last_date = self.data.index.max()
        start_date = last_date - pd.Timedelta(days=days)

        mask = self.data.index >= start_date
        filtered_df = self.data.loc[mask]

        # If resampling is needed on the filtered data
        if timeframe:
            filtered_df = (
                filtered_df.resample(timeframe)
                .agg(
                    {
                        "open": "first",
                        "high": "max",
                        "low": "min",
                        "close": "last",
                        "volume": "sum",
                    }
                )
                .dropna()
            )

        candles = []
        for ts, row in filtered_df.iterrows():
            candles.append(
                Candle(
                    timestamp=ts.to_pydatetime(),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )
        return candles
