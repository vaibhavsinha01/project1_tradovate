# from config import *
# import time
# import numpy as np
# import pandas as pd
# from utils.broker import TradovateBroker
# from modules.indicators import Indicators

# class TradingBot:
#     def __init__(self):
#         self.indicators = Indicators()
#         self.broker = TradovateBroker(
#             username=USERNAME,
#             password=PASSWORD,
#             app_id=APP_ID,
#             app_version=APP_VERSION,
#             device_id=DEVICE_ID,
#             cid=CID,
#             sec=SEC,
#         )
#         self.broker.connect()
#         self.h_pos = 0

#     def fetch_data(self) -> dict[str, pd.DataFrame]:
#         def _get_bars(unit_number: int, n_bars: int) -> pd.DataFrame:
#             params = {
#                 "symbol":     SYMBOL,
#                 "contractId": CONTRACT_ID,
#                 "unit":       "Minute",
#                 "unitNumber": unit_number,
#                 "limit":      n_bars,
#             }
#             raw = self.broker._get("history/getBars?" + "&".join(f"{k}={v}" for k, v in params.items()))
#             bars = raw.get("bars", [])
#             df = pd.DataFrame(bars)
#             df.rename(columns={
#                 "t":           "timestamp",
#                 "o":           "open",
#                 "h":           "high",
#                 "l":           "low",
#                 "c":           "close",
#                 "totalVolume": "volume",
#             }, inplace=True)
#             df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
#             df.set_index("timestamp", inplace=True)
#             df = df[["open", "high", "low", "close", "volume"]].astype(float)
#             return df

#         return {
#             "1m": _get_bars(1,  200),
#             "5m": _get_bars(5,  100),
#             "1h": _get_bars(60, 50),
#         }

#     def calculate_signals(self, data: dict[str, pd.DataFrame]) -> str:
#         df1m = data["1m"]
#         df5m = data["5m"]
#         df1h = data["1h"]

#         structure        = self.indicators.hh_hl_lh_ll(df1m["high"], df1m["low"])
#         latest_structure = structure["structure"].iloc[-1]
#         is_hh = "HH" in latest_structure
#         is_lh = "LH" in latest_structure

#         ema_1m = self.indicators.ema(df1m["close"], 20).iloc[-1]
#         ema_5m = self.indicators.ema(df5m["close"], 20).iloc[-1]
#         ema_1h = self.indicators.ema(df1h["close"], 20).iloc[-1]
#         bull_ema = ema_1m > ema_5m > ema_1h
#         bear_ema = ema_1m < ema_5m < ema_1h

#         vwap_df   = self.indicators.vwap(df1m, reset="D")
#         vwap_vals = vwap_df["vwap"]
#         vwap_now  = vwap_vals.iloc[-1]
#         vwap_avg  = vwap_vals.rolling(5).mean().iloc[-1]
#         bull_vwap = vwap_now > vwap_avg
#         bear_vwap = vwap_now < vwap_avg

#         rsi_val  = self.indicators.rsi(df1m["close"], period=14).iloc[-1]
#         bull_rsi = rsi_val < 50
#         bear_rsi = rsi_val > 50

#         print(
#             f"[SIGNAL] structure={latest_structure} | "
#             f"ema={ema_1m:.2f}/{ema_5m:.2f}/{ema_1h:.2f} | "
#             f"vwap={vwap_now:.2f} avg={vwap_avg:.2f} | rsi={rsi_val:.1f}"
#         )

#         if is_hh and bull_ema and bull_vwap and bull_rsi:
#             return "BUY"
#         if is_lh and bear_ema and bear_vwap and bear_rsi:
#             return "SELL"
#         return "HOLD"

#     def _exit_trade(self) -> None:
#         """Close whatever is open and reset h_pos to 0."""
#         self.broker.close_all_orders()
#         self.h_pos = 0
#         print("[EXEC] Position closed — h_pos reset to 0.")

#     def execute_signals(self, signal: str) -> None:
#         if signal == "HOLD":
#             print(f"[EXEC] HOLD — h_pos unchanged ({self.h_pos})")
#             return

#         if signal == "BUY":
#             if self.h_pos == 1:
#                 print("[EXEC] Already holding BUY — skipping.")
#                 return
#             if self.h_pos == -1:
#                 print("[EXEC] Exiting SELL trade before entering BUY.")
#                 self._exit_trade()
#             self.broker.place_order(SYMBOL, "Buy", TRADE_QTY, order_type="Market")
#             self.h_pos = 1
#             print(f"[EXEC] BUY {TRADE_QTY} {SYMBOL} — h_pos set to 1.")

#         elif signal == "SELL":
#             if self.h_pos == -1:
#                 print("[EXEC] Already holding SELL — skipping.")
#                 return
#             if self.h_pos == 1:
#                 print("[EXEC] Exiting BUY trade before entering SELL.")
#                 self._exit_trade()
#             self.broker.place_order(SYMBOL, "Sell", TRADE_QTY, order_type="Market")
#             self.h_pos = -1
#             print(f"[EXEC] SELL {TRADE_QTY} {SYMBOL} — h_pos set to -1.")

#     def _check_position_open(self) -> bool:
#         """
#         Ask the broker if we still have an open position for this contract.
#         Returns True if the position is still live, False if it's been closed
#         (hit SL/TP, manually closed, or liquidated).

#         Resets h_pos to 0 automatically when a closure is detected.
#         """
#         positions = self.broker.get_open_positions()

#         # A position is open if netPos is non-zero for our contract
#         active = next(
#             (p for p in positions
#              if p.get("contractId") == CONTRACT_ID and p.get("netPos", 0) != 0),
#             None
#         )

#         if active is None:
#             # Position no longer exists on the broker side
#             print(f"[MONITOR] Position closed externally — resetting h_pos from {self.h_pos} to 0.")
#             self.h_pos = 0
#             return False

#         net_pos = active.get("netPos", 0)
#         net_price = active.get("netPrice", 0.0)
#         open_pnl = active.get("openPnl", "n/a")
#         print(f"[MONITOR] Position still open | netPos={net_pos} | avgEntry={net_price} | openPnl={open_pnl}")
#         return True

#     def main(self) -> None:
#         """
#         Two-mode loop:

#         h_pos == 0  →  ENTRY MODE
#             Fetch OHLCV, calculate signals, execute if conditions met.

#         h_pos != 0  →  MONITOR MODE
#             Do NOT re-evaluate entry signals.
#             Only check if the current position is still open.
#             If it has been closed (SL/TP hit, manual close, liquidation),
#             reset h_pos to 0 so the next iteration re-enters entry mode.
#         """
#         try:
#             if self.h_pos == 0:
#                 print("\n[BOT] ENTRY MODE — scanning for signals...")
#                 data   = self.fetch_data()
#                 signal = self.calculate_signals(data)
#                 print(f"[BOT] Signal → {signal}")
#                 self.execute_signals(signal)

#             else:
#                 side = "LONG" if self.h_pos == 1 else "SHORT"
#                 print(f"\n[BOT] MONITOR MODE — holding {side} (h_pos={self.h_pos}), checking position...")
#                 self._check_position_open()

#         except Exception as e:
#             print(f"[ERROR] {e}")

#         finally:
#             print(f"[BOT] Sleeping {LOOP_SLEEP}s...\n")
#             time.sleep(LOOP_SLEEP)


# if __name__ == "__main__":
#     session = TradingBot()
#     while True:
#         session.main()

from config import *
import time
import numpy as np
import pandas as pd
from utils.broker import TradovateBroker
from modules.indicators import Indicators


class TradingBot:
    def __init__(self):
        self.indicators = Indicators()
        self.broker = TradovateBroker(
            username=USERNAME,
            password=PASSWORD,
            app_id=APP_ID,
            app_version=APP_VERSION,
            device_id=DEVICE_ID,
            cid=CID,
            sec=SEC,
        )
        self.broker.connect()

        # Holding position tracker
        #   0  → flat (no open trade)
        #  +1  → holding a BUY trade
        #  -1  → holding a SELL trade
        self.h_pos      = 0
        self.entry_price = None     # price at which we entered the trade

    # ------------------------------------------------------------------ #
    #  Data                                                                #
    # ------------------------------------------------------------------ #

    def fetch_data(self) -> dict[str, pd.DataFrame]:
        def _get_bars(unit_number: int, n_bars: int) -> pd.DataFrame:
            params = {
                "symbol":     SYMBOL,
                "contractId": CONTRACT_ID,
                "unit":       "Minute",
                "unitNumber": unit_number,
                "limit":      n_bars,
            }
            raw = self.broker._get(
                "history/getBars?" + "&".join(f"{k}={v}" for k, v in params.items())
            )
            bars = raw.get("bars", [])
            df = pd.DataFrame(bars)
            df.rename(columns={
                "t":           "timestamp",
                "o":           "open",
                "h":           "high",
                "l":           "low",
                "c":           "close",
                "totalVolume": "volume",
            }, inplace=True)
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df.set_index("timestamp", inplace=True)
            df = df[["open", "high", "low", "close", "volume"]].astype(float)
            return df

        return {
            "1m": _get_bars(1,  200),
            "5m": _get_bars(5,  100),
            "1h": _get_bars(60, 50),
        }

    def calculate_signals(self, data: dict[str, pd.DataFrame]) -> str:
        """
        BUY  : HH + ema1m>ema5m>ema1h + vwap>vwap.rolling(5) + rsi<50
        SELL : LH + ema1m<ema5m<ema1h + vwap<vwap.rolling(5) + rsi>50
        """
        df1m = data["1m"]
        df5m = data["5m"]
        df1h = data["1h"]

        # 1. Structure
        structure        = self.indicators.hh_hl_lh_ll(df1m["high"], df1m["low"])
        latest_structure = structure["structure"].iloc[-1]
        is_hh = "HH" in latest_structure
        is_lh = "LH" in latest_structure

        # 2. EMA alignment
        ema_1m   = self.indicators.ema(df1m["close"], 20).iloc[-1]
        ema_5m   = self.indicators.ema(df5m["close"], 20).iloc[-1]
        ema_1h   = self.indicators.ema(df1h["close"], 20).iloc[-1]
        bull_ema = ema_1m > ema_5m > ema_1h
        bear_ema = ema_1m < ema_5m < ema_1h

        # 3. VWAP momentum
        vwap_df   = self.indicators.vwap(df1m, reset="D")
        vwap_vals = vwap_df["vwap"]
        vwap_now  = vwap_vals.iloc[-1]
        vwap_avg  = vwap_vals.rolling(5).mean().iloc[-1]
        bull_vwap = vwap_now > vwap_avg
        bear_vwap = vwap_now < vwap_avg

        # 4. RSI
        rsi_val  = self.indicators.rsi(df1m["close"], period=14).iloc[-1]
        bull_rsi = rsi_val < 50
        bear_rsi = rsi_val > 50

        print(
            f"[SIGNAL] structure={latest_structure} | "
            f"ema={ema_1m:.2f}/{ema_5m:.2f}/{ema_1h:.2f} | "
            f"vwap={vwap_now:.2f} avg={vwap_avg:.2f} | rsi={rsi_val:.1f}"
        )

        if is_hh and bull_ema and bull_vwap and bull_rsi:
            return "BUY"
        if is_lh and bear_ema and bear_vwap and bear_rsi:
            return "SELL"
        return "HOLD"

    # ------------------------------------------------------------------ #
    #  Execution                                                           #
    # ------------------------------------------------------------------ #

    def _exit_trade(self) -> None:
        """Close the open position and reset state."""
        self.broker.close_all_orders()
        self.h_pos       = 0
        self.entry_price = None
        print("[EXEC] Position closed — h_pos reset to 0.")

    def execute_signals(self, signal: str) -> None:
        """
        One trade at a time via h_pos.
        On entry, places the market order + bracket TP/SL orders.
        """
        if signal == "HOLD":
            print(f"[EXEC] HOLD — h_pos unchanged ({self.h_pos})")
            return

        if signal == "BUY":
            if self.h_pos == 1:
                print("[EXEC] Already holding BUY — skipping.")
                return
            if self.h_pos == -1:
                print("[EXEC] Exiting SELL before entering BUY.")
                self._exit_trade()

            resp = self.broker.place_order(SYMBOL, "Buy", TRADE_QTY, order_type="Market")
            self.h_pos = 1

            # Record entry price for manual TP/SL tracking in monitor mode
            fill = resp.get("avgFillPrice") or resp.get("price")
            self.entry_price = float(fill) if fill else None
            print(f"[EXEC] BUY {TRADE_QTY} {SYMBOL} @ {self.entry_price} — h_pos=1 | TP=+{TP}pts SL=-{SL}pts")

        elif signal == "SELL":
            if self.h_pos == -1:
                print("[EXEC] Already holding SELL — skipping.")
                return
            if self.h_pos == 1:
                print("[EXEC] Exiting BUY before entering SELL.")
                self._exit_trade()

            resp = self.broker.place_order(SYMBOL, "Sell", TRADE_QTY, order_type="Market")
            self.h_pos = -1

            fill = resp.get("avgFillPrice") or resp.get("price")
            self.entry_price = float(fill) if fill else None
            print(f"[EXEC] SELL {TRADE_QTY} {SYMBOL} @ {self.entry_price} — h_pos=-1 | TP=+{TP}pts SL=-{SL}pts")

    def _check_position_open(self) -> bool:
        """
        Monitor mode — called every tick while h_pos != 0.

        1. Checks if the broker still shows an open position.
        2. If entry_price is known, checks TP/SL manually and exits if hit.
        3. Resets h_pos to 0 if position is gone.
        """
        # ── TP / SL check via live price ────────────────────────────────
        if self.entry_price is not None:
            pnl_data = self.broker.get_position_pnl(CONTRACT_ID)
            current  = pnl_data.get("current_price")

            if current:
                if self.h_pos == 1:
                    pnl_pts = current - self.entry_price
                else:
                    pnl_pts = self.entry_price - current

                print(f"[MONITOR] entry={self.entry_price} | current={current:.2f} | pnl={pnl_pts:.2f}pts")

                if pnl_pts >= TP:
                    print(f"[MONITOR] TP hit ({pnl_pts:.2f} >= {TP}) — exiting.")
                    self._exit_trade()
                    return False

                if pnl_pts <= -SL:
                    print(f"[MONITOR] SL hit ({pnl_pts:.2f} <= -{SL}) — exiting.")
                    self._exit_trade()
                    return False

        # ── Broker-side position check ───────────────────────────────────
        positions = self.broker.get_open_positions()
        active = next(
            (p for p in positions
             if p.get("contractId") == CONTRACT_ID and p.get("netPos", 0) != 0),
            None
        )

        if active is None:
            print(f"[MONITOR] Position closed externally — resetting h_pos from {self.h_pos} to 0.")
            self.h_pos       = 0
            self.entry_price = None
            return False

        net_pos   = active.get("netPos", 0)
        net_price = active.get("netPrice", 0.0)
        open_pnl  = active.get("openPnl", "n/a")
        print(f"[MONITOR] Position alive | netPos={net_pos} | avgEntry={net_price} | openPnl={open_pnl}")
        return True

    # ------------------------------------------------------------------ #
    #  Main loop                                                           #
    # ------------------------------------------------------------------ #

    def main(self) -> None:
        """
        h_pos == 0  →  ENTRY MODE  : scan signals, enter trade if conditions met
        h_pos != 0  →  MONITOR MODE: check TP/SL + broker position every tick
        """
        try:
            if self.h_pos == 0:
                print("\n[BOT] ENTRY MODE — scanning for signals...")
                data   = self.fetch_data()
                signal = self.calculate_signals(data)
                print(f"[BOT] Signal → {signal}")
                self.execute_signals(signal)

            else:
                side = "LONG" if self.h_pos == 1 else "SHORT"
                print(f"\n[BOT] MONITOR MODE — holding {side} (h_pos={self.h_pos})")
                self._check_position_open()

        except Exception as e:
            print(f"[ERROR] {e}")

        finally:
            print(f"[BOT] Sleeping {LOOP_SLEEP}s...\n")
            time.sleep(LOOP_SLEEP)


if __name__ == "__main__":
    session = TradingBot()
    while True:
        session.main()