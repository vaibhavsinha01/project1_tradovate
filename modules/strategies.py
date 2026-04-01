from modules.indicators import Indicators
import pandas as pd


class Strategy:
    def __init__(self):
        self.indicators = Indicators()

    # ------------------------------------------------------------------
    # Internal: run all 1m indicators (HTF S/R already in df if injected)
    # ------------------------------------------------------------------
    def _apply_indicators(self, df: pd.DataFrame, skip_sr: bool = False) -> pd.DataFrame:
        return self.indicators.compute_all(df, skip_sr=skip_sr)

    # ------------------------------------------------------------------
    # Step 1 — Location: price near a key HTF level
    # ------------------------------------------------------------------
    def _compute_location(self, df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
        distance_threshold = df["atr"] * 0.5

        near_support    = df["close"].sub(df["support_line"]).abs()    <= distance_threshold
        near_resistance = df["close"].sub(df["resistance_line"]).abs() <= distance_threshold

        return near_support, near_resistance

    # ------------------------------------------------------------------
    # Step 2 — VWAP confirmation (optional — participates in OR block)
    # ------------------------------------------------------------------
    def _compute_vwap_confirmation(self, df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
        vwap_long  = (df["close"] > df["vwap"]) & (df["low"]  <= df["vwap"])
        vwap_short = (df["close"] < df["vwap"]) & (df["high"] >= df["vwap"])

        return vwap_long, vwap_short

    # ------------------------------------------------------------------
    # Steps 3 & 4 — Trigger (mandatory) + Confirmation (OR logic)
    # ------------------------------------------------------------------
    def _compute_base_signals(
        self,
        df:             pd.DataFrame,
        near_support:   pd.Series,
        near_resistance: pd.Series,
        vwap_long:      pd.Series,
        vwap_short:     pd.Series,
    ) -> tuple[pd.Series, pd.Series]:

        # LONG
        long_trigger      = df["bullish_rejection"]
        long_confirmation = (
            df["rsi_turning_up"]
            | df["delta_signal_long"]
            | df["ema_bullish"]
            | vwap_long
        )
        long_base = near_support & long_trigger & long_confirmation

        # SHORT
        short_trigger      = df["bearish_rejection"]
        short_confirmation = (
            df["rsi_turning_down"]
            | df["delta_signal_short"]
            | df["ema_bearish"]
            | vwap_short
        )
        short_base = near_resistance & short_trigger & short_confirmation

        return long_base, short_base

    # ------------------------------------------------------------------
    # Step 6 — Entry refinement: next candle breaks the rejection candle
    #           shift(1) on both signal and anchor → zero lookahead
    # ------------------------------------------------------------------
    def _compute_refined_entries(
        self,
        df:         pd.DataFrame,
        long_base:  pd.Series,
        short_base: pd.Series,
    ) -> tuple[pd.Series, pd.Series]:

        # Anchor: high/low of the rejection candle (bar i-1 relative to entry bar i)
        rejection_high = df["high"].shift(1)
        rejection_low  = df["low"].shift(1)

        # Signal from the previous bar
        long_signal_prev  = long_base.shift(1).fillna(False)
        short_signal_prev = short_base.shift(1).fillna(False)

        # Current bar breaks the rejection candle's extreme
        long_entry  = long_signal_prev  & (df["high"] > rejection_high)
        short_entry = short_signal_prev & (df["low"]  < rejection_low)

        return long_entry, short_entry

    # ------------------------------------------------------------------
    # Master method
    # ------------------------------------------------------------------
    def apply(self, df: pd.DataFrame, htf_sr_injected: bool = False) -> pd.DataFrame:
        """
        Apply the level-based reaction strategy to a 1m OHLCV DataFrame.

        Parameters
        ----------
        df               : 1m OHLCV DataFrame with DatetimeIndex.
                           If htf_sr_injected=True, must already contain
                           `support_line` and `resistance_line` columns.
        htf_sr_injected  : Set True when HTF S/R was pre-computed and injected
                           by TradingBot before calling this method. Prevents
                           compute_all() from overwriting them with 1m S/R.

        Returns
        -------
        DataFrame with all indicator columns plus:
            long_entry  (bool) — bar on which to enter a long
            short_entry (bool) — bar on which to enter a short
        """
        # Compute all 1m indicators; skip S/R if HTF levels already injected
        df = self._apply_indicators(df, skip_sr=htf_sr_injected)

        # Step 1 — Location
        near_support, near_resistance = self._compute_location(df)

        # Step 2 — VWAP confirmation
        vwap_long, vwap_short = self._compute_vwap_confirmation(df)

        # Steps 3 & 4 — Trigger + confirmation
        long_base, short_base = self._compute_base_signals(
            df, near_support, near_resistance, vwap_long, vwap_short
        )

        # Step 6 — Refine: next-bar breakout (no lookahead)
        long_entry, short_entry = self._compute_refined_entries(df, long_base, short_base)

        # Step 7 — Attach
        df["long_entry"]  = long_entry
        df["short_entry"] = short_entry

        return df