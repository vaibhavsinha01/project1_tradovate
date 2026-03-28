import numpy as np
import pandas as pd
from utils.broker import TradovateBroker


class Indicators:
    def __init__(self):
        pass

    def rsi(self, closes: pd.Series, period: int = 14) -> pd.Series:
        """
        Classic Wilder RSI.
        Returns a Series of RSI values (0–100).
        """
        delta = closes.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    def ema(self, closes: pd.Series, period: int) -> pd.Series:
        """
        Standard EMA using pandas ewm.
        Returns a Series of EMA values.
        """
        return closes.ewm(span=period, adjust=False).mean()

    def hh_hl_lh_ll(self, highs: pd.Series, lows: pd.Series, lookback: int = 1) -> pd.DataFrame:
        """
        Identifies swing trend structure bar-by-bar.

        Compares each bar's high/low against the previous `lookback` bar:
          HH - Higher High   : high > prior high  (bullish continuation)
          HL - Higher Low    : low  > prior low   (bullish continuation)
          LH - Lower High    : high < prior high  (bearish continuation)
          LL - Lower Low     : low  < prior low   (bearish continuation)

        Returns a DataFrame with boolean columns [HH, HL, LH, LL]
        and a 'structure' column summarising the dominant label.
        """
        ph = highs.shift(lookback)
        pl = lows.shift(lookback)

        hh = highs > ph
        hl = lows  > pl
        lh = highs < ph
        ll = lows  < pl

        def _label(row):
            if row["HH"] and row["HL"]:
                return "HH+HL"
            if row["LH"] and row["LL"]:
                return "LH+LL"
            if row["HH"]:
                return "HH"
            if row["HL"]:
                return "HL"
            if row["LH"]:
                return "LH"
            if row["LL"]:
                return "LL"
            return "NONE"

        df = pd.DataFrame({"HH": hh, "HL": hl, "LH": lh, "LL": ll})
        df["structure"] = df.apply(_label, axis=1)
        return df

    def delta(self, closes: pd.Series, volumes: pd.Series) -> pd.DataFrame:
        """
        Approximates bar delta using the close position within the bar.

        buy_volume  = volume * ( close - low  ) / ( high - low )
        sell_volume = volume * ( high  - close) / ( high - low )
        delta       = buy_volume - sell_volume

        Accepts a combined OHLCV DataFrame or individual Series.
        Returns a DataFrame with [buy_vol, sell_vol, delta, cum_delta].
        """
        # Accept either a full OHLCV df or separate series
        if isinstance(closes, pd.DataFrame):
            df = closes
            o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]
        else:
            raise ValueError("Pass a full OHLCV DataFrame as the first argument.")

        bar_range = (h - l).replace(0, np.nan)
        buy_vol  = v * (c - l) / bar_range
        sell_vol = v * (h - c) / bar_range
        dlt      = buy_vol - sell_vol

        return pd.DataFrame({
            "buy_vol":   buy_vol,
            "sell_vol":  sell_vol,
            "delta":     dlt,
            "cum_delta": dlt.cumsum(),
        })


    def vwap(self, ohlcv: pd.DataFrame, reset: str = "D") -> pd.DataFrame:
        """
        Parameters
        ----------
        ohlcv   : DataFrame with columns [open, high, low, close, volume]
                  and a DatetimeIndex.
        reset   : pandas offset alias for session anchor — 'D' (daily),
                  'W' (weekly), 'M' (monthly).

        Returns a DataFrame with columns [vwap, upper1, lower1, upper2, lower2].
        """
        if not isinstance(ohlcv.index, pd.DatetimeIndex):
            raise ValueError("ohlcv must have a DatetimeIndex.")

        tp  = (ohlcv["high"] + ohlcv["low"] + ohlcv["close"]) / 3  # typical price
        vol = ohlcv["volume"]

        session = ohlcv.index.to_period(reset)

        cum_vol   = vol.groupby(session).cumsum()
        cum_tpv   = (tp * vol).groupby(session).cumsum()
        cum_tp2v  = (tp ** 2 * vol).groupby(session).cumsum()

        vwap_vals = cum_tpv / cum_vol
        variance  = (cum_tp2v / cum_vol) - vwap_vals ** 2
        std       = np.sqrt(variance.clip(lower=0))

        return pd.DataFrame({
            "vwap":   vwap_vals,
            "upper1": vwap_vals + 1 * std,
            "lower1": vwap_vals - 1 * std,
            "upper2": vwap_vals + 2 * std,
            "lower2": vwap_vals - 2 * std,
        }, index=ohlcv.index)