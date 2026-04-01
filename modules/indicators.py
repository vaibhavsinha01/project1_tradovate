import numpy as np
import pandas as pd
from logger import get_logger
from ta.volatility import AverageTrueRange

logger = get_logger()

class Indicators:
    def __init__(self):
        pass

    def _compute_ema(self, df: pd.DataFrame) -> pd.DataFrame:
        for span in [7, 16, 30]:
            df[f"ema_{span}"] = df["close"].ewm(span=span, adjust=False).mean()
        return df

    def _compute_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))
        return df

    def _compute_vwap(self, df: pd.DataFrame) -> pd.DataFrame:
        tp = (df["high"] + df["low"] + df["close"]) / 3
        tp_vol = tp * df["volume"]

        date_key = df.index.normalize() if hasattr(df.index, "normalize") else df.index.date

        cum_tp_vol = tp_vol.groupby(date_key).cumsum()
        cum_vol = df["volume"].groupby(date_key).cumsum()

        df["vwap"] = cum_tp_vol / cum_vol.replace(0, np.nan)
        return df
    
    def _compute_delta(self, df: pd.DataFrame) -> pd.DataFrame:
        df["delta"] = (
            (df["close"] - df["open"]) / (df["high"] - df["low"] + 1e-6)
        ) * df["volume"]
        df["delta_ma"] = df["delta"].rolling(window=5, min_periods=1).mean()
        return df

    def _compute_delta_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        delta = df["delta"]
        delta_ma = df["delta_ma"]
        delta_diff = delta.diff()

        delta_dry_up_long = (delta < 0) & (delta.abs() < delta_ma.abs())
        delta_turning_long = delta_diff > 0
        df["delta_signal_long"] = delta_dry_up_long & delta_turning_long

        delta_dry_up_short = (delta > 0) & (delta.abs() < delta_ma.abs())
        delta_turning_short = delta_diff < 0
        df["delta_signal_short"] = delta_dry_up_short & delta_turning_short

        return df

    def _compute_pivots(self, df: pd.DataFrame) -> pd.DataFrame:
        high = df["high"]
        low  = df["low"]

        df["pivot_high"] = (high > high.shift(1)) & (high > high.shift(-1))
        df["pivot_low"]  = (low  < low.shift(1))  & (low  < low.shift(-1))

        return df

    def _compute_atr(self, df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
        df["atr"] = AverageTrueRange(
            high=df["high"], low=df["low"], close=df["close"], window=window
        ).average_true_range()
        return df

    def _regression_sr(
        self, df: pd.DataFrame, window: int = 50
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Compute pivot-regression support & resistance on any OHLCV DataFrame.
        Pivots are computed internally on a temporary copy — no side effects.

        Returns
        -------
        (support_arr, resistance_arr) — numpy arrays aligned to df's index.
        """
        tmp = df.copy()
        tmp = self._compute_pivots(tmp)

        n               = len(tmp)
        resistance_line = np.full(n, np.nan)
        support_line    = np.full(n, np.nan)

        pos             = np.arange(n)
        pivot_high_mask = tmp["pivot_high"].values
        pivot_low_mask  = tmp["pivot_low"].values
        high_vals       = tmp["high"].values
        low_vals        = tmp["low"].values

        prev_res = np.nan
        prev_sup = np.nan

        for i in range(n):
            start = max(0, i - window + 1)

            # ---- Resistance ----
            res_idx = pos[start : i + 1][pivot_high_mask[start : i + 1]]
            res_y   = high_vals[res_idx]

            if len(res_idx) >= 2:
                slope, intercept = np.polyfit(res_idx, res_y, 1)
                val = slope * i + intercept
                resistance_line[i] = val
                prev_res = val
            elif len(res_idx) == 1:
                resistance_line[i] = res_y[0]
                prev_res = res_y[0]
            else:
                resistance_line[i] = prev_res if not np.isnan(prev_res) \
                    else (np.nanmax(high_vals[start : i + 1]) if i >= start else np.nan)

            # ---- Support ----
            sup_idx = pos[start : i + 1][pivot_low_mask[start : i + 1]]
            sup_y   = low_vals[sup_idx]

            if len(sup_idx) >= 2:
                slope, intercept = np.polyfit(sup_idx, sup_y, 1)
                val = slope * i + intercept
                support_line[i] = val
                prev_sup = val
            elif len(sup_idx) == 1:
                support_line[i] = sup_y[0]
                prev_sup = sup_y[0]
            else:
                support_line[i] = prev_sup if not np.isnan(prev_sup) \
                    else (np.nanmin(low_vals[start : i + 1]) if i >= start else np.nan)

        return support_line, resistance_line

    def _compute_support_resistance(
        self, df: pd.DataFrame, window: int = 100
    ) -> pd.DataFrame:
        support_arr, resistance_arr = self._regression_sr(df, window=window)
        df["support_line"]    = support_arr
        df["resistance_line"] = resistance_arr
        return df

    def compute_htf_sr(
        self,
        df_30m:     pd.DataFrame,
        df_1h:      pd.DataFrame,
        df_1m:      pd.DataFrame,
        window_30m: int = 50,
        window_1h:  int = 30,
    ) -> pd.DataFrame:
        """
        Compute regression S/R on 30m and 1h independently, combine by taking
        the strongest level at each 1m bar, then inject into df_1m.

        Combining logic:
          resistance = max(res_30m, res_1h)  →  higher ceiling is the stronger wall
          support    = min(sup_30m, sup_1h)  →  lower floor is the stronger base

        Both series are forward-filled onto the 1m index, so a HTF bar's level
        only propagates AFTER that bar has closed — no lookahead bias.

        Parameters
        ----------
        df_30m, df_1h : Raw OHLCV DataFrames with DatetimeIndex.
        df_1m         : 1m OHLCV DataFrame to inject levels into.
        window_30m    : Lookback for 30m regression (default 50 bars ≈ 25 h).
        window_1h     : Lookback for 1h regression  (default 30 bars = 30 h).

        Returns
        -------
        df_1m (copy) with `support_line` and `resistance_line` added/overwritten.
        """
        logger.info("[HTF S/R] Computing 30m regression levels...")
        sup_30m, res_30m = self._regression_sr(df_30m, window=window_30m)
        sr_30m = pd.DataFrame(
            {"support_line": sup_30m, "resistance_line": res_30m},
            index=df_30m.index,
        )

        logger.info("[HTF S/R] Computing 1h regression levels...")
        sup_1h, res_1h = self._regression_sr(df_1h, window=window_1h)
        sr_1h = pd.DataFrame(
            {"support_line": sup_1h, "resistance_line": res_1h},
            index=df_1h.index,
        )

        # Forward-fill each HTF series onto the 1m index.
        # reindex + ffill: a 30m/1h bar's value appears only after its close timestamp.
        target_idx = df_1m.index
        sr_30m_1m  = sr_30m.reindex(target_idx, method="ffill")
        sr_1h_1m   = sr_1h.reindex(target_idx,  method="ffill")

        # Combine — strongest level from either timeframe wins
        df_1m = df_1m.copy()
        df_1m["support_line"] = sr_30m_1m["support_line"].combine(
            sr_1h_1m["support_line"], np.fmin   # lower support = stronger floor
        )
        df_1m["resistance_line"] = sr_30m_1m["resistance_line"].combine(
            sr_1h_1m["resistance_line"], np.fmax  # higher resistance = stronger ceiling
        )

        logger.info("[HTF S/R] HTF levels injected into 1m DataFrame.")
        return df_1m

    def _compute_wick_rejection(self, df: pd.DataFrame) -> pd.DataFrame:
        body       = (df["close"] - df["open"]).abs()
        upper_wick = df["high"] - df[["open", "close"]].max(axis=1)
        lower_wick = df[["open", "close"]].min(axis=1) - df["low"]

        df["bullish_rejection"] = lower_wick > 2 * body
        df["bearish_rejection"] = upper_wick > 2 * body
        return df

    def _compute_ema_trend(self, df: pd.DataFrame) -> pd.DataFrame:
        df["ema_bullish"] = (df["ema_7"] > df["ema_16"]) & (df["ema_16"] > df["ema_30"])
        df["ema_bearish"] = (df["ema_7"] < df["ema_16"]) & (df["ema_16"] < df["ema_30"])
        return df

    def _compute_rsi_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        rsi_diff = df["rsi"].diff()
        df["rsi_turning_up"]   = (df["rsi"] < 45) & (rsi_diff > 0)
        df["rsi_turning_down"] = (df["rsi"] > 55) & (rsi_diff < 0)
        return df

    def recent_swing_low(self, low: pd.Series, lookback: int = 10) -> float:
        return float(low.iloc[-lookback:].min())

    def recent_swing_high(self, high: pd.Series, lookback: int = 10) -> float:
        return float(high.iloc[-lookback:].max())

    def compute_all(
        self,
        df:        pd.DataFrame,
        sr_window: int  = 100,
        skip_sr:   bool = False,
    ) -> pd.DataFrame:
        """
        Compute all 1m indicators on an OHLCV DataFrame.

        Parameters
        ----------
        df        : OHLCV DataFrame with DatetimeIndex.
        sr_window : Lookback for 1m-native S/R (ignored when skip_sr=True).
        skip_sr   : Pass True when HTF levels were already injected via
                    compute_htf_sr() — avoids overwriting them with 1m S/R.

        Returns
        -------
        DataFrame with all indicator columns appended.
        """
        required_cols = {"open", "high", "low", "close", "volume"}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(f"Input DataFrame is missing columns: {missing}")

        df = df.copy()
        df = self._compute_ema(df)
        df = self._compute_rsi(df)
        df = self._compute_vwap(df)
        df = self._compute_delta(df)
        df = self._compute_delta_signals(df)
        df = self._compute_atr(df)
        df = self._compute_pivots(df)
        if not skip_sr:
            df = self._compute_support_resistance(df, window=sr_window)
        else:
            logger.info("Skipping 1m S/R — using pre-injected HTF levels.")

        df = self._compute_wick_rejection(df)
        df = self._compute_ema_trend(df)
        df = self._compute_rsi_signals(df)
        return df