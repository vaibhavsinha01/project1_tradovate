import numpy as np
import pandas as pd
from logger import get_logger
from ta.trend import SMAIndicator, EMAIndicator

logger = get_logger()

class Indicators:
    def __init__(self):
        pass

    def rsi(self, closes: pd.Series, period: int = 14) -> pd.Series:
        """Wilder RSI. Returns Series of values 0-100."""
        delta    = closes.diff()
        gain     = delta.clip(lower=0)
        loss     = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        rs       = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    def rsi_turning_up(self, closes: pd.Series, period: int = 14, lookback: int = 3) -> bool:
        """True if RSI has been rising for the last `lookback` bars."""
        rsi_vals = self.rsi(closes, period)
        return bool(rsi_vals.iloc[-lookback:].is_monotonic_increasing)

    def rsi_turning_down(self, closes: pd.Series, period: int = 14, lookback: int = 3) -> bool:
        """True if RSI has been falling for the last `lookback` bars."""
        rsi_vals = self.rsi(closes, period)
        return bool(rsi_vals.iloc[-lookback:].is_monotonic_decreasing)

    def ema(self, closes: pd.Series, period: int) -> pd.Series:
        """Standard EMA via pandas ewm."""
        return closes.ewm(span=period, adjust=False).mean()

    def hh_hl_lh_ll(self, ohlcv: pd.DataFrame, lookback: int = 1) -> pd.DataFrame:
        """
        Bar-by-bar swing structure.
        Returns DataFrame with bool columns [HH, HL, LH, LL] + 'structure' label.
        """
        highs = ohlcv['high']
        lows = ohlcv['low']
        ph = highs.shift(lookback)
        pl = lows.shift(lookback)
        hh = highs > ph
        hl = lows  > pl
        lh = highs < ph
        ll = lows  < pl

        def _label(row):
            if row["HH"] and row["HL"]: return "HH+HL"
            if row["LH"] and row["LL"]: return "LH+LL"
            if row["HH"]:               return "HH"
            if row["HL"]:               return "HL"
            if row["LH"]:               return "LH"
            if row["LL"]:               return "LL"
            return "NONE"

        # df = pd.DataFrame({"HH": hh, "HL": hl, "LH": lh, "LL": ll})
        ohlcv['hh'] = hh
        ohlcv['ll'] = ll
        ohlcv['hl'] = hl
        ohlcv['lh'] = lh 
        # ohlcv["structure"] = ohlcv.apply(_label, axis=1)
        ohlcv["structure"] = ohlcv.apply(
            lambda row: _label({"HH": row["hh"], "HL": row["hl"], "LH": row["lh"], "LL": row["ll"]}),
            axis=1
        )
        return ohlcv

    def htf_structure(self, highs: pd.Series, lows: pd.Series, n: int = 5) -> str:
        """
        Dominant HTF structure over the last `n` bars.
        Returns 'BULLISH', 'BEARISH', or 'NEUTRAL'.
        """
        ohlcv = pd.DataFrame({'high': highs, 'low': lows, 'close': highs})
        df      = self.hh_hl_lh_ll(ohlcv)
        recent  = df["structure"].iloc[-n:]
        bull_ct = recent.str.contains("HH|HL").sum()
        bear_ct = recent.str.contains("LH|LL").sum()
        if bull_ct > bear_ct:   return "BULLISH"
        if bear_ct > bull_ct:   return "BEARISH"
        return "NEUTRAL"

    def vwap(self, ohlcv: pd.DataFrame, reset: str = "D") -> pd.DataFrame:
        """
        Session-anchored VWAP with ±1std / ±2std bands.
        Requires DatetimeIndex. Returns [vwap, upper1, lower1, upper2, lower2].
        """
        if not isinstance(ohlcv.index, pd.DatetimeIndex):
            raise ValueError("ohlcv must have a DatetimeIndex.")

        tp  = (ohlcv["high"] + ohlcv["low"] + ohlcv["close"]) / 3
        vol = ohlcv["volume"]

        session  = ohlcv.index.to_period(reset)
        cum_vol  = vol.groupby(session).cumsum()
        cum_tpv  = (tp * vol).groupby(session).cumsum()
        cum_tp2v = (tp ** 2 * vol).groupby(session).cumsum()

        vwap_vals = cum_tpv / cum_vol
        variance  = (cum_tp2v / cum_vol) - vwap_vals ** 2
        std       = np.sqrt(variance.clip(lower=0))

        ohlcv['vwap'] = vwap_vals
        ohlcv['upper1_vwap'] = vwap_vals + std
        ohlcv['lower1_vwap'] = vwap_vals - std
        ohlcv['upper2_vwap'] = vwap_vals + 2*std
        ohlcv['lower2_vwap'] = vwap_vals - 2*std

        # return pd.DataFrame({
        #     "vwap":   vwap_vals,
        #     "upper1": vwap_vals + std,
        #     "lower1": vwap_vals - std,
        #     "upper2": vwap_vals + 2 * std,
        #     "lower2": vwap_vals - 2 * std,
        # }, index=ohlcv.index)
        return ohlcv 

    def price_reclaimed_vwap(self, closes: pd.Series, vwap_vals: pd.Series, lookback: int = 3) -> bool:
        """
        True if price dipped below VWAP then closed back above it within `lookback` bars.
        Bullish VWAP reclaim signal.
        """
        c      = closes.iloc[-lookback:]
        v      = vwap_vals.iloc[-lookback:]
        dipped  = (c < v).any()
        reclaim = closes.iloc[-1] > vwap_vals.iloc[-1]
        return bool(dipped and reclaim)

    def price_rejected_vwap(self, closes: pd.Series, vwap_vals: pd.Series, lookback: int = 3) -> bool:
        """
        True if price poked above VWAP then closed back below it within `lookback` bars.
        Bearish VWAP rejection signal.
        """
        c           = closes.iloc[-lookback:]
        v           = vwap_vals.iloc[-lookback:]
        poked_above = (c > v).any()
        rejection   = closes.iloc[-1] < vwap_vals.iloc[-1]
        return bool(poked_above and rejection)

    def bullish_rejection_candle(self, ohlcv: pd.DataFrame) -> bool:
        """
        Hammer / pin bar on the last bar.
          - Lower wick > 2x body
          - Bullish close (close > open)
          - Upper wick < lower wick
        """
        bar  = ohlcv.iloc[-1]
        o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]
        body       = abs(c - o)
        if body == 0: return False
        lower_wick = min(o, c) - l
        upper_wick = h - max(o, c)
        return bool(lower_wick > 2 * body and c > o and upper_wick < lower_wick)

    def bearish_rejection_candle(self, ohlcv: pd.DataFrame) -> bool:
        """
        Shooting star / pin bar on the last bar.
          - Upper wick > 2x body
          - Bearish close (close < open)
          - Lower wick < upper wick
        """
        bar  = ohlcv.iloc[-1]
        o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]
        body       = abs(c - o)
        if body == 0: return False
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l
        return bool(upper_wick > 2 * body and c < o and lower_wick < upper_wick)

    def near_trendline(
        self,
        ohlcv: pd.DataFrame,
        mode: str = "ascending",    # "ascending" | "descending"
        swing_lookback: int = 20,
        tolerance: float = 0.003,   # 0.3% of price
    ) -> bool:
        """
        Fits a linear regression through the last `swing_lookback` swing
        lows (ascending) or swing highs (descending) and checks if the
        current close is within `tolerance` of the projected trendline value.
        """
        n      = swing_lookback
        x      = np.arange(n)
        prices = (ohlcv["low"] if mode == "ascending" else ohlcv["high"]).iloc[-n:].values

        coeffs   = np.polyfit(x, prices, 1)
        tl_value = np.polyval(coeffs, n - 1)
        current  = ohlcv["close"].iloc[-1]
        near     = abs(current - tl_value) <= current * tolerance

        logger.debug(f"Trendline ({mode}): projected={tl_value:.2f} current={current:.2f} near={near}")
        return bool(near)

    def recent_swing_low(self, lows: pd.Series, lookback: int = 10) -> float:
        """Lowest low over the last `lookback` bars — used as SL for longs."""
        return float(lows.iloc[-lookback:].min())

    def recent_swing_high(self, highs: pd.Series, lookback: int = 10) -> float:
        """Highest high over the last `lookback` bars — used as SL for shorts."""
        return float(highs.iloc[-lookback:].max())

    # returns df working
    def delta(self, ohlcv: pd.DataFrame) -> pd.DataFrame: # check the delta function 
        """
        Approximates bar delta (buy vol - sell vol).
        Pass full OHLCV DataFrame.
        Returns [buy_vol, sell_vol, delta, cum_delta].
        """
        if not isinstance(ohlcv, pd.DataFrame):
            raise ValueError("Pass a full OHLCV DataFrame.")
        h, l, c, v = ohlcv["high"], ohlcv["low"], ohlcv["close"], ohlcv["volume"]
        bar_range   = (h - l).replace(0, np.nan)
        buy_vol     = v * (c - l) / bar_range
        sell_vol    = v * (h - c) / bar_range
        dlt         = buy_vol - sell_vol
        ohlcv['bar_range'] = bar_range
        ohlcv['buy_vol'] = buy_vol
        ohlcv['sell_vol'] = sell_vol
        ohlcv['dlt'] = dlt
        ohlcv['cum_delta'] = ohlcv['dlt'].cumsum()

        return ohlcv
    
    # return df working
    def ema_crossing_reversal(
        self,
        ohlcv: pd.DataFrame,
        ema1_period: int = 30,
        ema2_period: int = 16,
        ema3_period: int = 7,
        rsi_upper: float = 60,
        rsi_lower: float = 40,
        delta_lookback: int = 3,
    ) -> pd.DataFrame:
        """
        EMA Crossing Reversal Strategy (vectorized, DataFrame output)

        Adds:
            ema1, ema2, ema3
            rsi
            delta
            ema_bullish, ema_bearish
            momentum_bullish, momentum_bearish
            trendline_bullish, trendline_bearish
            buy_signal, sell_signal
        """

        df = ohlcv.copy()

        # ── EMA ─────────────────────────────────────────────────────────
        df["ema1"] = self.ema(df["close"], ema1_period)
        df["ema2"] = self.ema(df["close"], ema2_period)
        df["ema3"] = self.ema(df["close"], ema3_period)

        # ── RSI ─────────────────────────────────────────────────────────
        df["rsi"] = self.rsi(df["close"])

        # ── Delta ───────────────────────────────────────────────────────
        # delta_df = self.delta(df)
        self.delta(df)
        df["delta"] = df["dlt"]

        # Smooth delta (reduce noise)
        df["delta_sum"] = df["delta"].rolling(delta_lookback).sum()

        # ── EMA CONDITIONS ──────────────────────────────────────────────
        df["ema_bullish"] = (df["ema1"] > df["ema2"]) & (df["ema1"] > df["ema3"])
        df["ema_bearish"] = (df["ema1"] < df["ema2"]) & (df["ema1"] < df["ema3"])

        # ── MOMENTUM CONDITIONS ─────────────────────────────────────────
        df["momentum_bullish"] = (df["delta_sum"] > 0) | (df["rsi"] < rsi_lower)
        df["momentum_bearish"] = (df["delta_sum"] < 0) | (df["rsi"] > rsi_upper)

        # ── TRENDLINE (non-vectorized → last value only propagated) ─────
        trendline_bullish = self.near_trendline(df, mode="ascending")
        trendline_bearish = self.near_trendline(df, mode="descending")

        df["trendline_bullish"] = False
        df["trendline_bearish"] = False

        df.loc[df.index[-1], "trendline_bullish"] = trendline_bullish
        df.loc[df.index[-1], "trendline_bearish"] = trendline_bearish

        # ── FINAL SIGNALS ───────────────────────────────────────────────
        df["buy_signal"] = (
            df["ema_bullish"] &
            df["momentum_bullish"] &
            df["trendline_bullish"]
        )

        df["sell_signal"] = (
            df["ema_bearish"] &
            df["momentum_bearish"] &
            df["trendline_bearish"]
        )

        return df

    # returns df - working
    def squeeze_momentum(
        self,
        ohlcv: pd.DataFrame,
        length_bb: int   = 20,
        mult_bb: float   = 2.0,
        length_kc: int   = 20,
        mult_kc: float   = 1.5,
        use_true_range: bool = True,
    ) -> pd.DataFrame:
        """
        Squeeze Momentum Indicator - Python port of LazyBear's Pine Script v3.

        Parameters
        ----------
        csv_path       : Path to CSV file with columns: open, high, low, close
        length_bb      : Bollinger Band period          (default 20)
        mult_bb        : Bollinger Band std multiplier  (default 2.0)
        length_kc      : Keltner Channel period         (default 20)
        mult_kc        : Keltner Channel ATR multiplier (default 1.5)
        use_true_range : Use True Range for KC (True) or simple High-Low (False)

        Returns
        -------
        DataFrame with additional columns:
            val     - momentum histogram value (linear regression output)
            bcolor  - histogram bar color  : 'lime' | 'green' | 'red' | 'maroon'
            scolor  - centre-dot color     : 'blue'  (no squeeze)
                                        | 'black' (squeeze ON)
                                        | 'gray'  (squeeze OFF)
        """
        # df = pd.read_csv(csv_path)
        df = ohlcv.copy()
        df.columns = df.columns.str.lower().str.strip()

        # ── Bollinger Bands ──────────────────────────────────────────────────────
        df['sma_bb']   = SMAIndicator(close=df['close'], window=length_bb).sma_indicator()
        df['dev']      = df['close'].rolling(window=length_bb).std()
        df['upper_bb'] = df['sma_bb'] + df['dev'] * mult_bb
        df['lower_bb'] = df['sma_bb'] - df['dev'] * mult_bb

        # ── Keltner Channels ─────────────────────────────────────────────────────
        df['ma_kc'] = SMAIndicator(close=df['close'], window=length_kc).sma_indicator()

        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                (df['high'] - df['close'].shift(1)).abs(),
                (df['low']  - df['close'].shift(1)).abs(),
            )
        )
        range_series  = df['tr'] if use_true_range else (df['high'] - df['low'])
        df['rangema'] = SMAIndicator(close=range_series, window=length_kc).sma_indicator()

        df['upper_kc'] = df['ma_kc'] + df['rangema'] * mult_kc
        df['lower_kc'] = df['ma_kc'] - df['rangema'] * mult_kc

        # ── Squeeze flags ────────────────────────────────────────────────────────
        df['sqz_on']  = (df['lower_bb'] > df['lower_kc']) & (df['upper_bb'] < df['upper_kc'])
        df['sqz_off'] = (df['lower_bb'] < df['lower_kc']) & (df['upper_bb'] > df['upper_kc'])
        df['no_sqz']  = ~df['sqz_on'] & ~df['sqz_off']

        # ── Momentum value  (linreg of delta, offset=0) ──────────────────────────
        df['highest_high'] = df['high'].rolling(window=length_kc).max()
        df['lowest_low']   = df['low'].rolling(window=length_kc).min()
        df['sma_close_kc'] = SMAIndicator(close=df['close'], window=length_kc).sma_indicator()

        df['delta'] = df['close'] - (
            (df['highest_high'] + df['lowest_low']) / 2 + df['sma_close_kc']
        ) / 2

        def _linreg_last(series: pd.Series, window: int) -> np.ndarray:
            """Rolling linear regression – returns the fitted value at the last bar."""
            result = np.full(len(series), np.nan)
            arr    = series.to_numpy()
            x      = np.arange(window)
            for i in range(window - 1, len(arr)):
                y = arr[i - window + 1 : i + 1]
                if np.any(np.isnan(y)):
                    continue
                slope, intercept = np.polyfit(x, y, 1)
                result[i] = intercept + slope * (window - 1)
            return result

        df['val']      = _linreg_last(df['delta'], length_kc)
        df['val_prev'] = df['val'].shift(1)

        # ── Colours ──────────────────────────────────────────────────────────────
        def _bar_color(row):
            if row['val'] > 0:
                return 'lime'   if row['val'] > row['val_prev'] else 'green'
            else:
                return 'red'    if row['val'] < row['val_prev'] else 'maroon'

        df['bcolor'] = df.apply(_bar_color, axis=1)
        df['scolor'] = np.where(
            df['no_sqz'],  'blue',
            np.where(df['sqz_on'], 'black', 'gray')
        )

        # Drop intermediate columns, keep it tidy
        df.drop(columns=['dev', 'tr', 'rangema', 'highest_high', 'lowest_low',
                        'sma_close_kc', 'delta', 'val_prev'], inplace=True)

        return df
    
    # returns df - working
    def macd_ultimate(
        self,
        ohlcv: pd.DataFrame,
        fast_length: int   = 12,
        slow_length: int   = 26,
        signal_length: int = 9,
        hist_color_change: bool = True,
        macd_color_change: bool = True,
    ) -> pd.DataFrame:
        """
        MACD Ultimate - Python port of ChrisMoody's CM_MacD_Ult_MTF Pine Script v3.

        Note: Multi-timeframe (MTF) and 'use different resolution' options from
        the original Pine Script are not applicable here; pass pre-resampled data
        if a different timeframe is required.

        Parameters
        ----------
        csv_path          : Path to CSV file with columns: open, high, low, close
        fast_length       : EMA fast period       (default 12)
        slow_length       : EMA slow period       (default 26)
        signal_length     : SMA signal period     (default  9)
        hist_color_change : 4-colour histogram    (default True)
        macd_color_change : MACD line colour flip on signal cross (default True)

        Returns
        -------
        DataFrame with additional columns:
            macd        - MACD line value
            signal      - Signal line value
            hist        - Histogram value  (macd − signal)

            hist_up_a   - bool : histogram rising  above zero  → aqua
            hist_dn_a   - bool : histogram falling above zero  → blue
            hist_dn_b   - bool : histogram falling below zero  → red
            hist_up_b   - bool : histogram rising  below zero  → maroon

            plot_color  - histogram bar colour
            macd_color  - MACD line colour
            signal_color- signal line colour
            cross       - bool : MACD / Signal crossover on this bar
        """
        # df = pd.read_csv(csv_path)
        df = ohlcv.copy()
        df.columns = df.columns.str.lower().str.strip()

        # ── MACD components ──────────────────────────────────────────────────────
        fast_ma = EMAIndicator(close=df['close'], window=fast_length).ema_indicator()
        slow_ma = EMAIndicator(close=df['close'], window=slow_length).ema_indicator()

        df['macd']   = fast_ma - slow_ma
        df['signal'] = SMAIndicator(close=df['macd'], window=signal_length).sma_indicator()
        df['hist']   = df['macd'] - df['signal']

        # ── Histogram direction flags ────────────────────────────────────────────
        hist_prev         = df['hist'].shift(1)
        df['hist_up_a']   = (df['hist'] > hist_prev) & (df['hist'] >  0)   # rising  above 0
        df['hist_dn_a']   = (df['hist'] < hist_prev) & (df['hist'] >  0)   # falling above 0
        df['hist_dn_b']   = (df['hist'] < hist_prev) & (df['hist'] <= 0)   # falling below 0
        df['hist_up_b']   = (df['hist'] > hist_prev) & (df['hist'] <= 0)   # rising  below 0

        # ── MACD vs Signal position ──────────────────────────────────────────────
        macd_is_above = df['macd'] >= df['signal']

        # ── Histogram colour ─────────────────────────────────────────────────────
        if hist_color_change:
            df['plot_color'] = np.select(
                [df['hist_up_a'], df['hist_dn_a'], df['hist_dn_b'], df['hist_up_b']],
                ['aqua',          'blue',          'red',           'maroon'],
                default='yellow'
            )
        else:
            df['plot_color'] = 'gray'

        # ── MACD & Signal line colours ───────────────────────────────────────────
        if macd_color_change:
            df['macd_color']   = np.where(macd_is_above, 'lime', 'red')
            df['signal_color'] = 'yellow'                          # always yellow when enabled
        else:
            df['macd_color']   = 'red'
            df['signal_color'] = 'lime'

        # ── Crossover dots (circleYPosition = signal value) ──────────────────────
        # Cross occurs when macd and signal swap sides between bars
        prev_above       = macd_is_above.shift(1)
        df['cross']      = macd_is_above != prev_above             # True on cross bar
        df['cross_price'] = np.where(df['cross'], df['signal'], np.nan)

        return df
    
    # returns df - working
    def supertrend(
        self,
        ohlcv: pd.DataFrame,
        atr_period: int       = 10,
        multiplier: float     = 3.0,
        change_atr: bool      = True,
        show_signals: bool    = True,
        highlighting: bool    = True,
    ) -> pd.DataFrame:
        """
        Supertrend Indicator - Python port of Pine Script v4.

        Parameters
        ----------
        csv_path    : Path to CSV file with columns: open, high, low, close
        atr_period  : ATR / SMA(TR) lookback period         (default 10)
        multiplier  : ATR band multiplier                   (default 3.0)
        change_atr  : True  → Wilder's ATR  (atr())
                    False → SMA of TR     (sma(tr, period))
        show_signals: Compute buy/sell signal columns       (default True)
        highlighting: Compute fill-colour columns           (default True)

        Returns
        -------
        DataFrame with additional columns:
            hl2         – (high + low) / 2          [Pine src]
            tr          – True Range
            atr         – ATR or SMA(TR) depending on change_atr flag
            up          – raw upper band (lower band for uptrend line)
            dn          – raw lower band (upper band for downtrend line)
            trend       –  1 = uptrend  |  -1 = downtrend
            supertrend  – actual supertrend line value (up when trend=1, dn when -1)

        If show_signals=True:
            buy_signal  – bool : trend flips from -1 → 1
            sell_signal – bool : trend flips from  1 → -1
            change_cond – bool : any trend direction change

        If highlighting=True:
            long_fill_color  – 'green' during uptrend,  else 'white'
            short_fill_color – 'red'   during downtrend, else 'white'
        """
        # df = pd.read_csv(csv_path)
        df = ohlcv.copy()
        df.columns = df.columns.str.lower().str.strip()

        # ── Source: hl2 ──────────────────────────────────────────────────────────
        df['hl2'] = (df['high'] + df['low']) / 2

        # ── True Range ───────────────────────────────────────────────────────────
        prev_close   = df['close'].shift(1)
        df['tr']     = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                (df['high'] - prev_close).abs(),
                (df['low']  - prev_close).abs(),
            )
        )

        # ── ATR  (Wilder's RMA vs simple SMA of TR) ──────────────────────────────
        if change_atr:
            # Wilder's smoothing  =  EMA with alpha = 1/period  (same as Pine's atr())
            df['atr'] = df['tr'].ewm(alpha=1 / atr_period, adjust=False).mean()
        else:
            # Pine: atr2 = sma(tr, Periods)
            df['atr'] = SMAIndicator(close=df['tr'], window=atr_period).sma_indicator()

        # ── Initial raw bands ────────────────────────────────────────────────────
        df['up_raw'] = df['hl2'] - (multiplier * df['atr'])
        df['dn_raw'] = df['hl2'] + (multiplier * df['atr'])

        # ── Iterative band & trend calculation (must be row-by-row) ─────────────
        up_arr    = df['up_raw'].to_numpy(dtype=float)
        dn_arr    = df['dn_raw'].to_numpy(dtype=float)
        close_arr = df['close'].to_numpy(dtype=float)
        n         = len(df)

        up_final   = np.full(n, np.nan)
        dn_final   = np.full(n, np.nan)
        trend_arr  = np.full(n, np.nan)

        for i in range(n):
            if np.isnan(up_arr[i]):          # ATR not yet warm
                continue

            # ── up band (acts as support in uptrend) ─────────────────────────────
            if i == 0:
                up_final[i] = up_arr[i]
            else:
                up1 = up_final[i - 1] if not np.isnan(up_final[i - 1]) else up_arr[i]
                # Pine: up := close[1] > up1 ? max(up, up1) : up
                up_final[i] = max(up_arr[i], up1) if close_arr[i - 1] > up1 else up_arr[i]

            # ── dn band (acts as resistance in downtrend) ─────────────────────────
            if i == 0:
                dn_final[i] = dn_arr[i]
            else:
                dn1 = dn_final[i - 1] if not np.isnan(dn_final[i - 1]) else dn_arr[i]
                # Pine: dn := close[1] < dn1 ? min(dn, dn1) : dn
                dn_final[i] = min(dn_arr[i], dn1) if close_arr[i - 1] < dn1 else dn_arr[i]

            # ── trend ─────────────────────────────────────────────────────────────
            if i == 0:
                trend_arr[i] = 1
            else:
                prev_trend = trend_arr[i - 1] if not np.isnan(trend_arr[i - 1]) else 1
                dn1        = dn_final[i - 1]  if not np.isnan(dn_final[i - 1])  else dn_arr[i]
                up1        = up_final[i - 1]  if not np.isnan(up_final[i - 1])  else up_arr[i]

                # Pine logic:
                # trend := trend == -1 and close > dn1 ? 1
                #        : trend ==  1 and close < up1 ? -1
                #        : trend
                if   prev_trend == -1 and close_arr[i] > dn1:
                    trend_arr[i] = 1
                elif prev_trend ==  1 and close_arr[i] < up1:
                    trend_arr[i] = -1
                else:
                    trend_arr[i] = prev_trend

        df['up']         = up_final
        df['dn']         = dn_final
        df['trend']      = trend_arr
        df['supertrend'] = np.where(df['trend'] == 1, df['up'], df['dn'])

        # ── Signals ──────────────────────────────────────────────────────────────
        if show_signals:
            prev_trend          = df['trend'].shift(1)
            df['buy_signal']    = (df['trend'] ==  1) & (prev_trend == -1)
            df['sell_signal']   = (df['trend'] == -1) & (prev_trend ==  1)
            df['change_cond']   = df['trend'] != prev_trend

        # ── Highlight colours ────────────────────────────────────────────────────
        if highlighting:
            df['long_fill_color']  = np.where(df['trend'] ==  1, 'green', 'white')
            df['short_fill_color'] = np.where(df['trend'] == -1, 'red',   'white')

        # Drop construction columns
        df.drop(columns=['up_raw', 'dn_raw'], inplace=True)

        return df