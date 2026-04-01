from config import *
import time
import numpy as np
import pandas as pd
from utils.broker import TradovateBroker
from logger import get_logger
from modules.indicators import Indicators
from modules.strategies import Strategy

logger = get_logger()


class TradingBot:
    def __init__(self):
        self.indicators = Indicators()
        self.strategy   = Strategy()

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

        self.h_pos       = 0      # 0 = flat | +1 = long | -1 = short
        self.entry_price = None
        self.sl_price    = None
        self.tp_price    = None

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------
    def fetch_data(self) -> dict[str, pd.DataFrame]:
        def _get_bars(unit_number: int, n_bars: int) -> pd.DataFrame:
            params = {
                "symbol":     SYMBOL,
                "contractId": CONTRACT_ID,
                "unit":       "Minute",
                "unitNumber": unit_number,
                "limit":      n_bars,
            }
            raw  = self.broker._get(
                "history/getBars?" + "&".join(f"{k}={v}" for k, v in params.items())
            )
            bars = raw.get("bars", [])
            df   = pd.DataFrame(bars)
            df.rename(
                columns={"t": "timestamp", "o": "open", "h": "high",
                         "l": "low",       "c": "close", "totalVolume": "volume"},
                inplace=True,
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df.set_index("timestamp", inplace=True)
            return df[["open", "high", "low", "close", "volume"]].astype(float)

        return {
            "1m":  _get_bars(1,  200),
            "5m":  _get_bars(5,  100),
            "30m": _get_bars(30,  60),
            "1h":  _get_bars(60,  50),
        }

    # ------------------------------------------------------------------
    # HTF S/R injection
    # ------------------------------------------------------------------
    def _inject_htf_sr(self, data: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        Compute regression-based S/R on 30m and 1h, combine them, and
        inject the resulting levels into the 1m DataFrame.

        Returns the 1m DataFrame with `support_line` and `resistance_line`
        columns populated from HTF data.
        """
        logger.info("[HTF] Injecting HTF S/R levels into 1m data...")
        df_1m = self.indicators.compute_htf_sr(
            df_30m=data["30m"],
            df_1h=data["1h"],
            df_1m=data["1m"],
            window_30m=50,   # ~25 h of 30m bars
            window_1h=30,    # 30 h of 1h bars
        )
        logger.info("[HTF] HTF S/R injection complete.")
        return df_1m

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------
    def calculate_signals(self, data: dict[str, pd.DataFrame]) -> str:
        """
        1. Inject HTF S/R into 1m data.
        2. Run Strategy (all 1m indicators + entry logic).
        3. Read the signal from the last completed bar (iloc[-2]).
           The last bar (iloc[-1]) may be incomplete in live trading.

        Returns "BUY", "SELL", or "HOLD".
        """
        # Step 1 — Inject HTF levels (no lookahead: ffill from closed HTF bars)
        df_1m = self._inject_htf_sr(data)

        # Step 2 — Run strategy; skip_sr=True so HTF levels are preserved
        df_1m = self.strategy.apply(df_1m, htf_sr_injected=True)

        # Step 3 — Read signal from the last *closed* 1m bar
        last = df_1m.iloc[-2]   # -1 is the still-forming candle

        if last["long_entry"]:
            signal = "BUY"
        elif last["short_entry"]:
            signal = "SELL"
        else:
            signal = "HOLD"

        logger.info(
            f"[SIGNALS] long_entry={last['long_entry']} | "
            f"short_entry={last['short_entry']} → {signal}"
        )
        return signal

    # ------------------------------------------------------------------
    # SL / TP calculation
    # ------------------------------------------------------------------
    def _calculate_sl_tp(
        self, signal: str, entry: float, df1m: pd.DataFrame
    ) -> tuple[float, float]:
        """
        SL  = recent swing high (short) or swing low (long)
        TP  = entry ± 2 × risk  →  1:2 risk-to-reward
        """
        if signal == "BUY":
            sl   = self.indicators.recent_swing_low(df1m["low"], lookback=10)
            risk = entry - sl
            tp   = entry + 2 * risk
        else:
            sl   = self.indicators.recent_swing_high(df1m["high"], lookback=10)
            risk = sl - entry
            tp   = entry - 2 * risk

        logger.info(
            f"[SL/TP] entry={entry:.2f} | sl={sl:.2f} | tp={tp:.2f} | risk={risk:.2f}pts"
        )
        return sl, tp

    # ------------------------------------------------------------------
    # Exit
    # ------------------------------------------------------------------
    def _exit_trade(self) -> None:
        self.broker.close_all_orders()
        self.h_pos       = 0
        self.entry_price = None
        self.sl_price    = None
        self.tp_price    = None
        logger.info("[EXEC] Position closed — h_pos reset to 0.")

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def execute_signals(self, signal: str, data: dict[str, pd.DataFrame]) -> None:
        if signal == "HOLD":
            logger.info(f"[EXEC] HOLD — h_pos unchanged ({self.h_pos})")
            return

        df1m = data["1m"]

        if signal == "BUY":
            if self.h_pos == 1:
                logger.info("[EXEC] Already holding BUY — skipping.")
                return
            if self.h_pos == -1:
                logger.info("[EXEC] Exiting SELL before entering BUY.")
                self._exit_trade()

            resp   = self.broker.place_order(SYMBOL, "Buy", TRADE_QTY, order_type="Market")
            fill   = resp.get("avgFillPrice") or resp.get("price") or df1m["close"].iloc[-1]
            entry  = float(fill)
            sl, tp = self._calculate_sl_tp("BUY", entry, df1m)

            self.h_pos       = 1
            self.entry_price = entry
            self.sl_price    = sl
            self.tp_price    = tp
            logger.info(f"[EXEC] BUY {TRADE_QTY} {SYMBOL} @ {entry:.2f} | SL={sl:.2f} | TP={tp:.2f}")

        elif signal == "SELL":
            if self.h_pos == -1:
                logger.info("[EXEC] Already holding SELL — skipping.")
                return
            if self.h_pos == 1:
                logger.info("[EXEC] Exiting BUY before entering SELL.")
                self._exit_trade()

            resp   = self.broker.place_order(SYMBOL, "Sell", TRADE_QTY, order_type="Market")
            fill   = resp.get("avgFillPrice") or resp.get("price") or df1m["close"].iloc[-1]
            entry  = float(fill)
            sl, tp = self._calculate_sl_tp("SELL", entry, df1m)

            self.h_pos       = -1
            self.entry_price = entry
            self.sl_price    = sl
            self.tp_price    = tp
            logger.info(f"[EXEC] SELL {TRADE_QTY} {SYMBOL} @ {entry:.2f} | SL={sl:.2f} | TP={tp:.2f}")

    # ------------------------------------------------------------------
    # Position monitor
    # ------------------------------------------------------------------
    def _check_position_open(self) -> bool:
        """
        Monitor mode — every tick while h_pos != 0:
          1. Check dynamic SL/TP against live price.
          2. Verify broker still shows an open position.
          3. Reset h_pos to 0 if closed externally.
        """
        if self.entry_price is not None and self.sl_price is not None:
            pnl_data = self.broker.get_position_pnl(CONTRACT_ID)
            current  = pnl_data.get("current_price")

            if current:
                current = float(current)
                logger.info(
                    f"[MONITOR] entry={self.entry_price:.2f} | current={current:.2f} | "
                    f"sl={self.sl_price:.2f} | tp={self.tp_price:.2f}"
                )

                # TP hit
                if self.h_pos == 1 and current >= self.tp_price:
                    logger.info(f"[MONITOR] TP hit at {current:.2f} — exiting LONG.")
                    self._exit_trade()
                    return False
                if self.h_pos == -1 and current <= self.tp_price:
                    logger.info(f"[MONITOR] TP hit at {current:.2f} — exiting SHORT.")
                    self._exit_trade()
                    return False

                # SL hit
                if self.h_pos == 1 and current <= self.sl_price:
                    logger.info(f"[MONITOR] SL hit at {current:.2f} — exiting LONG.")
                    self._exit_trade()
                    return False
                if self.h_pos == -1 and current >= self.sl_price:
                    logger.info(f"[MONITOR] SL hit at {current:.2f} — exiting SHORT.")
                    self._exit_trade()
                    return False

        # Broker-side position check
        positions = self.broker.get_open_positions()
        active = next(
            (p for p in positions
             if p.get("contractId") == CONTRACT_ID and p.get("netPos", 0) != 0),
            None,
        )
        if active is None:
            logger.info("[MONITOR] Position closed externally — resetting h_pos to 0.")
            self.h_pos       = 0
            self.entry_price = None
            self.sl_price    = None
            self.tp_price    = None
            return False

        logger.info(
            f"[MONITOR] Position alive | netPos={active.get('netPos')} | "
            f"avgEntry={active.get('netPrice')} | openPnl={active.get('openPnl', 'n/a')}"
        )
        return True

    # ------------------------------------------------------------------
    # Main loop body
    # ------------------------------------------------------------------
    def main(self) -> None:
        """
        h_pos == 0  →  ENTRY MODE  : compute HTF S/R, run strategy, enter if triggered
        h_pos != 0  →  MONITOR MODE: check dynamic SL/TP + broker position
        """
        try:
            if self.h_pos == 0:
                logger.info("\n[BOT] ENTRY MODE — scanning for signals...")
                data   = self.fetch_data()
                signal = self.calculate_signals(data)
                logger.info(f"[BOT] Final signal → {signal}")
                self.execute_signals(signal, data)

            else:
                side = "LONG" if self.h_pos == 1 else "SHORT"
                logger.info(f"\n[BOT] MONITOR MODE — holding {side} (h_pos={self.h_pos})")
                self._check_position_open()

        except Exception as e:
            logger.error(f"[ERROR] {e}", exc_info=True)

        finally:
            logger.info(f"[BOT] Sleeping {LOOP_SLEEP}s...")
            time.sleep(LOOP_SLEEP)


if __name__ == "__main__":
    session = TradingBot()
    while True:
        session.main()