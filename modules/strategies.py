from modules.indicators import Indicators
import pandas as pd

indicators = Indicators()

def _signal_trendline_pullback(df1m: pd.DataFrame, dfhtf: pd.DataFrame) -> pd.DataFrame:
    htf_struct = indicators.htf_structure(dfhtf["high"], dfhtf["low"])
    vwap_df    = indicators.vwap(df1m, reset="D")
    vwap_vals  = vwap_df["vwap"]
    rsi_val    = indicators.rsi(df1m["close"]).iloc[-1]
    struct_1m  = indicators.hh_hl_lh_ll(df1m)
    latest     = struct_1m["structure"].iloc[-1]

    if (
        htf_struct == "BULLISH"
        and indicators.near_trendline(df1m, mode="ascending")
        and rsi_val < 45
        and indicators.rsi_turning_up(df1m["close"])
        and indicators.price_reclaimed_vwap(df1m["close"], vwap_vals)
        and indicators.bullish_rejection_candle(df1m)
        and "HH" in latest
    ):
        signal = "BUY"
    elif (
        htf_struct == "BEARISH"
        and indicators.near_trendline(df1m, mode="descending")
        and rsi_val > 55
        and indicators.rsi_turning_down(df1m["close"])
        and indicators.price_rejected_vwap(df1m["close"], vwap_vals)
        and indicators.bearish_rejection_candle(df1m)
        and "LH" in latest
    ):
        signal = "SELL"
    else:
        signal = "HOLD"

    df1m["signal_trendline_pullback"] = signal
    return df1m


def _signal_vwap_ema_continuation(df1m: pd.DataFrame, dfhtf: pd.DataFrame) -> pd.DataFrame:
    htf_struct = indicators.htf_structure(dfhtf["high"], dfhtf["low"])
    ema20      = indicators.ema(df1m["close"], 20)
    ema50      = indicators.ema(df1m["close"], 50)
    vwap_df    = indicators.vwap(df1m, reset="D")
    vwap_vals  = vwap_df["vwap"]
    close_now  = df1m["close"].iloc[-1]
    ema20_now  = ema20.iloc[-1]
    ema50_now  = ema50.iloc[-1]
    vwap_now   = vwap_vals.iloc[-1]

    in_ema_zone = (
        abs(close_now - ema20_now) / close_now < 0.002 or
        abs(close_now - ema50_now) / close_now < 0.002 or
        abs(close_now - vwap_now)  / close_now < 0.002
    )

    if (
        htf_struct == "BULLISH"
        and close_now > ema20_now > ema50_now
        and in_ema_zone
        and indicators.bullish_rejection_candle(df1m)
    ):
        signal = "BUY"
    elif (
        htf_struct == "BEARISH"
        and close_now < ema20_now < ema50_now
        and in_ema_zone
        and indicators.bearish_rejection_candle(df1m)
    ):
        signal = "SELL"
    else:
        signal = "HOLD"

    df1m["signal_vwap_ema_continuation"] = signal
    return df1m

def _signal_exhaustion_reversal(data: pd.DataFrame) -> pd.DataFrame:
    df = data.copy()
    df.columns = df.columns.str.lower().str.strip()

    # ── Indicators ─────────────────────────────────────
    df = indicators.vwap(df, reset="D")
    df["rsi"] = indicators.rsi(df["close"])

    signals = []

    for i in range(len(df)):
        if i < 20:   # warmup buffer
            signals.append("HOLD")
            continue

        sub_df = df.iloc[:i+1]

        rsi_val = sub_df["rsi"].iloc[-1]

        if (
            rsi_val < 38
            and indicators.price_reclaimed_vwap(sub_df["close"], sub_df["vwap"], lookback=5)
            and indicators.bullish_rejection_candle(sub_df)
        ):
            signals.append("BUY")

        elif (
            rsi_val > 62
            and indicators.price_rejected_vwap(sub_df["close"], sub_df["vwap"], lookback=5)
            and indicators.bearish_rejection_candle(sub_df)
        ):
            signals.append("SELL")

        else:
            signals.append("HOLD")

    df["signal"] = signals
    return df

# these are the three indicators add the one that he gave and the three that i created 

def _signal_ema_trendline_confirmation(data:pd.DataFrame) -> pd.DataFrame:
    return indicators.ema_crossing_reversal(ohlcv=data)

def _signal_supertrend_indicator(data:pd.DataFrame) -> pd.DataFrame: # top 10 in tradingview
     return indicators.supertrend(ohlcv=data)

def _signal_macd_ultimate(data:pd.DataFrame) -> pd.DataFrame:
     return indicators.macd_ultimate(ohlcv=data)

def _signal_squeeze_momentum(data:pd.DataFrame) -> pd.DataFrame:
     return indicators.squeeze_momentum(ohlcv=data)
