import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.strategies import _signal_macd_ultimate
from backtesting import Backtest, Strategy
import pandas as pd
import numpy as np

class Macd_Ultimate(Strategy):
    tp_pct = 150   # stored as basis points (1.5% = 150) to use range()
    sl_pct = 75    # stored as basis points (0.75% = 75)

    def init(self):
        df = pd.DataFrame({
            'open':   self.data.Open,
            'high':   self.data.High,
            'low':    self.data.Low,
            'close':  self.data.Close,
            'volume': self.data.Volume,
        })

        result         = _signal_macd_ultimate(df)
        macd_color_int = np.where(result['macd_color'] == 'red', 1, 0)

        self.macd_color = self.I(lambda x: x, macd_color_int,        name='macd_color')
        self.cross      = self.I(lambda x: x, result['cross'].values, name='cross')

    def next(self):
        if len(self.data) < 2:
            return

        curr_color = self.macd_color[-1]
        curr_cross = self.cross[-1]
        price      = self.data.Close[-1]

        tp = self.tp_pct / 10_000   # convert basis points back to decimal
        sl = self.sl_pct / 10_000

        if curr_cross and curr_color == 0:      # BUY
            if not self.position.is_long:
                if self.position:
                    self.position.close()
                self.buy(tp=price * (1 + tp), sl=price * (1 - sl))

        elif curr_cross and curr_color == 1:    # SELL
            if not self.position.is_short:
                if self.position:
                    self.position.close()
                self.sell(tp=price * (1 - tp), sl=price * (1 + sl))


if __name__ == "__main__":
    path = r"C:\Users\vaibh\OneDrive\Desktop\official_projects\data\ethusd.csv"
    df   = pd.read_csv(path)
    df.columns = df.columns.str.lower().str.strip()

    df["Date"] = pd.to_datetime(df["time"])
    df = df.set_index("Date").sort_index()
    df = df.rename(columns={
        "open": "Open", "high": "High",
        "low":  "Low",  "close": "Close", "volume": "Volume"
    })
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()

    bt = Backtest(df, Macd_Ultimate, cash=10_000_000, commission=0, exclusive_orders=True)

    stats, heatmap = bt.optimize(
        tp_pct = range(50, 400, 25),    # 0.5% to 4.0% in 0.25% steps
        sl_pct = range(25, 200, 25),    # 0.25% to 2.0% in 0.25% steps
        maximize = "Equity Final [$]",
        method   = "sambo",
        return_heatmap       = True,
        return_optimization  = False,
        max_tries = 100,
    )

    print(stats)
    print(f"\nBest TP: {stats._strategy.tp_pct / 100:.2f}%")
    print(f"Best SL: {stats._strategy.sl_pct / 100:.2f}%")
    print("\n── Trade Log ──────────────────────────────────────────────────")
    print(stats["_trades"].to_string())

    trades_path = r"C:\Users\vaibh\OneDrive\Desktop\official_projects\data\trades_data\Macd_Ultimate_trades.csv"
    stats["_trades"].to_csv(trades_path, index=False)
    print(f"\nTrade log saved → {trades_path}")

# from modules.strategies import _signal_supertrend_indicator
# from backtesting import Backtest, Strategy
# import pandas as pd
# import numpy as np

# class Supertrend_Strategy(Strategy):
#     tp_pct = 150   # 1.5%
#     sl_pct = 75    # 0.75%

#     def init(self):
#         df = pd.DataFrame({
#             'open':   self.data.Open,
#             'high':   self.data.High,
#             'low':    self.data.Low,
#             'close':  self.data.Close,
#             'volume': self.data.Volume,
#         })

#         result = _signal_supertrend_indicator(df)

#         self.buy_signal  = self.I(lambda x: x, result['buy_signal'].astype(int).values, name='buy_signal')
#         self.sell_signal = self.I(lambda x: x, result['sell_signal'].astype(int).values, name='sell_signal')

#     def next(self):
#         if len(self.data) < 2:
#             return

#         price = self.data.Close[-1]

#         tp = self.tp_pct / 10_000
#         sl = self.sl_pct / 10_000

#         buy  = self.buy_signal[-1]
#         sell = self.sell_signal[-1]

#         # ── BUY ─────────────────────────────
#         if buy:
#             if not self.position.is_long:
#                 if self.position:
#                     self.position.close()
#                 self.buy(tp=price * (1 + tp), sl=price * (1 - sl))

#         # ── SELL ────────────────────────────
#         elif sell:
#             if not self.position.is_short:
#                 if self.position:
#                     self.position.close()
#                 self.sell(tp=price * (1 - tp), sl=price * (1 + sl))

# if __name__ == "__main__":
#     path = r"C:\Users\vaibh\OneDrive\Desktop\official_projects\data\ethusd.csv"
#     df   = pd.read_csv(path)

#     df.columns = df.columns.str.lower().str.strip()

#     df["Date"] = pd.to_datetime(df["time"])
#     df = df.set_index("Date").sort_index()

#     df = df.rename(columns={
#         "open": "Open", "high": "High",
#         "low":  "Low",  "close": "Close", "volume": "Volume"
#     })

#     df = df[["Open", "High", "Low", "Close", "Volume"]].copy()

#     bt = Backtest(
#         df,
#         Supertrend_Strategy,
#         cash=10_000_000,
#         commission=0,
#         exclusive_orders=True
#     )

#     stats, heatmap = bt.optimize(
#         tp_pct = range(50, 400, 25),   # 0.5% → 4.0%
#         sl_pct = range(25, 200, 25),   # 0.25% → 2.0%
#         maximize = "Equity Final [$]",
#         method   = "sambo",
#         return_heatmap      = True,
#         return_optimization = False,
#         max_tries = 100,
#     )

#     print(stats)
#     print(f"\nBest TP: {stats._strategy.tp_pct / 100:.2f}%")
#     print(f"Best SL: {stats._strategy.sl_pct / 100:.2f}%")

#     print("\n── Trade Log ─────────────────────────────────────────")
#     print(stats["_trades"].to_string())

#     trades_path = r"C:\Users\vaibh\OneDrive\Desktop\official_projects\data\trades_data\Supertrend_trades.csv"
#     stats["_trades"].to_csv(trades_path, index=False)

#     print(f"\nTrade log saved → {trades_path}")

# from backtesting import Strategy

# class SqueezeColor(Strategy):
#     tp_pct = 150   # 1.5%
#     sl_pct = 75    # 0.75%

#     # same encoding you used
#     COLOR_MAP = {
#         "maroon": 0,
#         "red": 1,
#         "gray": 2,
#         "blue": 3,
#         "lime": 4,
#         "green": 5,
#         "black": 6
#     }

#     def init(self):
#         # pass precomputed column
#         self.bcolor = self.I(lambda x: x, self.data.bcolor_int, name="bcolor")

#     def next(self):
#         if len(self.data) < 2:
#             return

#         prev_color = self.bcolor[-2]
#         curr_color = self.bcolor[-1]
#         price      = self.data.Close[-1]

#         tp = self.tp_pct / 10_000
#         sl = self.sl_pct / 10_000

#         # ── BUY: red → maroon ─────────────────────────────
#         if prev_color == self.COLOR_MAP["red"] and curr_color == self.COLOR_MAP["maroon"]:
#             if not self.position.is_long:
#                 if self.position:
#                     self.position.close()

#                 self.buy(
#                     tp=price * (1 + tp),
#                     sl=price * (1 - sl)
#                 )

#         # ── SELL: lime → green ────────────────────────────
#         elif prev_color == self.COLOR_MAP["lime"] and curr_color == self.COLOR_MAP["green"]:
#             if not self.position.is_short:
#                 if self.position:
#                     self.position.close()

#                 self.sell(
#                     tp=price * (1 - tp),
#                     sl=price * (1 + sl)
#                 )

# from backtesting import Backtest
# import pandas as pd

# if __name__ == "__main__":
#     path = r"C:\Users\vaibh\OneDrive\Desktop\alphas\strategy1.csv"
#     df   = pd.read_csv(path)

#     df.columns = df.columns.str.lower().str.strip()

#     df["Date"] = pd.to_datetime(df["time"], unit="ms")
#     df = df.set_index("Date").sort_index()

#     df = df.rename(columns={
#         "open": "Open", "high": "High",
#         "low":  "Low",  "close": "Close", "volume": "Volume"
#     })

#     df = df[["Open", "High", "Low", "Close", "Volume", "bcolor"]].copy()

#     # Encode colors
#     COLOR_MAP = {
#         "maroon": 0,
#         "red": 1,
#         "gray": 2,
#         "blue": 3,
#         "lime": 4,
#         "green": 5,
#         "black": 6
#     }

#     df["bcolor_int"] = df["bcolor"].str.strip().map(COLOR_MAP).fillna(-1).astype(int)

#     bt = Backtest(
#         df,
#         SqueezeColor,
#         cash=10_000_000,
#         commission=0,
#         exclusive_orders=True
#     )

#     stats, heatmap = bt.optimize(
#         tp_pct = range(50, 400, 25),
#         sl_pct = range(25, 200, 25),
#         maximize = "Equity Final [$]",
#         method   = "sambo",
#         return_heatmap      = True,
#         return_optimization = False,
#         max_tries = 100,
#     )

#     print(stats)
#     print(f"\nBest TP: {stats._strategy.tp_pct / 100:.2f}%")
#     print(f"Best SL: {stats._strategy.sl_pct / 100:.2f}%")

#     print("\n── Trade Log ─────────────────────────────────────────")
#     print(stats["_trades"].to_string())

#     stats["_trades"].to_csv("squeeze_color_trades.csv", index=False)

# from modules.strategies import _signal_exhaustion_reversal
# from backtesting import Strategy
# import numpy as np
# import pandas as pd

# class ExhaustionReversal(Strategy):
#     tp_pct = 150
#     sl_pct = 75

#     SIGNAL_MAP = {
#         "HOLD": 0,
#         "BUY": 1,
#         "SELL": -1
#     }

#     def init(self):
#         df = pd.DataFrame({
#             'open':   self.data.Open,
#             'high':   self.data.High,
#             'low':    self.data.Low,
#             'close':  self.data.Close,
#             'volume': self.data.Volume,
#         },index=self.data.index)

#         result = _signal_exhaustion_reversal(df)

#         signal_int = result["signal"].map(self.SIGNAL_MAP).values

#         self.signal = self.I(lambda x: x, signal_int, name="signal")

#     def next(self):
#         if len(self.data) < 2:
#             return

#         sig   = self.signal[-1]
#         price = self.data.Close[-1]

#         tp = self.tp_pct / 10_000
#         sl = self.sl_pct / 10_000

#         # ── BUY ─────────────────────────────
#         if sig == 1:
#             if not self.position.is_long:
#                 if self.position:
#                     self.position.close()

#                 self.buy(
#                     tp=price * (1 + tp),
#                     sl=price * (1 - sl)
#                 )

#         # ── SELL ────────────────────────────
#         elif sig == -1:
#             if not self.position.is_short:
#                 if self.position:
#                     self.position.close()

#                 self.sell(
#                     tp=price * (1 - tp),
#                     sl=price * (1 + sl)
#                 )

# from backtesting import Backtest
# import pandas as pd

# if __name__ == "__main__":
#     path = r"C:\Users\vaibh\OneDrive\Desktop\official_projects\data\ethusd.csv"
#     df   = pd.read_csv(path)

#     df.columns = df.columns.str.lower().str.strip()

#     df["Date"] = pd.to_datetime(df["time"])
#     df = df.set_index("Date").sort_index()

#     df = df.rename(columns={
#         "open": "Open", "high": "High",
#         "low":  "Low",  "close": "Close", "volume": "Volume"
#     })

#     df = df[["Open", "High", "Low", "Close", "Volume"]].copy()

#     bt = Backtest(
#         df,
#         ExhaustionReversal,
#         cash=10_000_000,
#         commission=0,
#         exclusive_orders=True
#     )

#     stats, heatmap = bt.optimize(
#         tp_pct = range(50, 400, 25),
#         sl_pct = range(25, 200, 25),
#         maximize = "Equity Final [$]",
#         method   = "sambo",
#         return_heatmap      = True,
#         return_optimization = False,
#         max_tries = 100,
#     )

#     print(stats)
#     print(f"\nBest TP: {stats._strategy.tp_pct / 100:.2f}%")
#     print(f"Best SL: {stats._strategy.sl_pct / 100:.2f}%")

#     print("\n── Trade Log ─────────────────────────────────────────")
#     print(stats["_trades"].to_string())

#     stats["_trades"].to_csv("exhaustion_reversal_trades.csv", index=False)

# import pandas as pd
# from backtesting import Backtest, Strategy

# from modules.strategies import _signal_trendline_pullback,_signal_vwap_ema_continuation

# import pandas as pd

# # ── Load 1m data ─────────────────────────────────────────
# df1m = pd.read_csv(r"C:\Users\vaibh\OneDrive\Desktop\official_projects\data\ethusd_1m.csv")
# df1m.columns = df1m.columns.str.lower().str.strip()

# df1m["time"] = pd.to_datetime(df1m["time"], unit="ms")
# df1m = df1m.set_index("time").sort_index()

# # ── Load HTF (15m) ───────────────────────────────────────
# df15m = pd.read_csv(r"C:\Users\vaibh\OneDrive\Desktop\official_projects\data\ethusd.csv")
# df15m.columns = df15m.columns.str.lower().str.strip()

# df15m["time"] = pd.to_datetime(df15m["time"])
# df15m = df15m.set_index("time").sort_index()

# # ── Align HTF → 1m (forward fill) ────────────────────────
# df15m_aligned = df15m.reindex(df1m.index, method="ffill")

# from modules.strategies import _signal_trendline_pullback

# def compute_trendline_signals(df1m, df15m):
#     signals = []

#     for i in range(len(df1m)):
#         if i < 50:
#             signals.append("HOLD")
#             continue

#         sub_1m  = df1m.iloc[:i+1].copy()
#         sub_htf = df15m.iloc[:i+1].copy()

#         res = _signal_trendline_pullback(sub_1m, sub_htf)
#         signals.append(res["signal_trendline_pullback"].iloc[-1])

#     df1m["signal_trendline"] = signals
#     return df1m

# from modules.strategies import _signal_vwap_ema_continuation

# def compute_vwap_ema_signals(df1m, df15m):
#     signals = []

#     for i in range(len(df1m)):
#         if i < 50:
#             signals.append("HOLD")
#             continue

#         sub_1m  = df1m.iloc[:i+1].copy()
#         sub_htf = df15m.iloc[:i+1].copy()

#         res = _signal_vwap_ema_continuation(sub_1m, sub_htf)
#         signals.append(res["signal_vwap_ema_continuation"].iloc[-1])

#     df1m["signal_vwap_ema"] = signals
#     return df1m

# def combine_signals(df):
#     final = []

#     for t, v in zip(df["signal_trendline"], df["signal_vwap_ema"]):
#         if t == v and t != "HOLD":
#             final.append(t)
#         else:
#             final.append("HOLD")

#     df["signal"] = final
#     return df

# from backtesting import Strategy
# import numpy as np

# class MTFStrategy(Strategy):
#     tp_pct = 150
#     sl_pct = 75

#     MAP = {"HOLD": 0, "BUY": 1, "SELL": -1}

    
#     def init(self):
#         # Convert to numpy array first
#         signal_raw = np.array(self.data.signal)

#         # Map manually (FAST + SAFE)
#         signal_int = np.vectorize(self.MAP.get)(signal_raw)

#         # Shift to avoid lookahead
#         signal_int = np.roll(signal_int, 1)
#         signal_int[0] = 0  # first value safe

#         self.signal = self.I(lambda x: x, signal_int)

#     def next(self):
#         if len(self.data) < 2:
#             return

#         sig   = self.signal[-1]
#         price = self.data.Close[-1]

#         tp = self.tp_pct / 10_000
#         sl = self.sl_pct / 10_000

#         if sig == 1:
#             if not self.position.is_long:
#                 if self.position:
#                     self.position.close()
#                 self.buy(tp=price*(1+tp), sl=price*(1-sl))

#         elif sig == -1:
#             if not self.position.is_short:
#                 if self.position:
#                     self.position.close()
#                 self.sell(tp=price*(1-tp), sl=price*(1+sl))

# from backtesting import Backtest

# # ── Compute signals ──────────────────────────────────────
# df1m = compute_trendline_signals(df1m, df15m_aligned)
# df1m = compute_vwap_ema_signals(df1m, df15m_aligned)
# df1m = combine_signals(df1m)

# # ── Prepare for backtest ─────────────────────────────────
# df_bt = df1m.rename(columns={
#     "open": "Open", "high": "High",
#     "low": "Low", "close": "Close", "volume": "Volume"
# })

# df_bt = df_bt[["Open","High","Low","Close","Volume","signal"]].dropna()

# # ── Run backtest ─────────────────────────────────────────
# bt = Backtest(df_bt, MTFStrategy, cash=10_000_000, commission=0)

# stats, heatmap = bt.optimize(
#     tp_pct = range(50, 400, 25),
#     sl_pct = range(25, 200, 25),
#     maximize = "Equity Final [$]",
#     method   = "sambo",
#     return_heatmap=True,
#     max_tries=100
# )

# print(stats)
# print(f"\nBest TP: {stats._strategy.tp_pct / 100:.2f}%")
# print(f"Best SL: {stats._strategy.sl_pct / 100:.2f}%")

# stats["_trades"].to_csv("mtf_trades.csv", index=False)

