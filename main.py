from config import *
import time
import numpy as np
import pandas as pd
from utils.broker import TradovateBroker
from logger import get_logger
from modules.indicators import Indicators
from modules.strategies import _signal_exhaustion_reversal,_signal_trendline_pullback,_signal_vwap_ema_continuation
logger = get_logger()

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

        self.h_pos       = 0      #  0 = flat | +1 = long | -1 = short
        self.entry_price = None
        self.sl_price    = None
        self.tp_price    = None

    def fetch_data(self) -> dict[str, pd.DataFrame]:
        def _get_bars(unit_number: int, n_bars: int) -> pd.DataFrame:
            params = {
                "symbol":     SYMBOL,
                "contractId": CONTRACT_ID,
                "unit":       "Minute",
                "unitNumber": unit_number,
                "limit":      n_bars,
            }
            raw  = self.broker._get("history/getBars?" + "&".join(f"{k}={v}" for k, v in params.items()))
            bars = raw.get("bars", [])
            df   = pd.DataFrame(bars)
            df.rename(columns={"t": "timestamp", "o": "open", "h": "high",
                                "l": "low", "c": "close", "totalVolume": "volume"}, inplace=True)
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df.set_index("timestamp", inplace=True)
            return df[["open", "high", "low", "close", "volume"]].astype(float)

        return {
            "1m":  _get_bars(1,  200),
            "5m":  _get_bars(5,  100),
            "30m": _get_bars(30, 60),
            "1h":  _get_bars(60, 50),
        }

    def calculate_signals(self, data: dict[str, pd.DataFrame]) -> str:
        """
        Runs all three signals. First non-HOLD result wins.
        Priority: Signal1 (trendline) > Signal2 (continuation) > Signal3 (exhaustion)
        """
        s1 = _signal_trendline_pullback(data)
        s2 = _signal_vwap_ema_continuation(data)
        s3 = _signal_exhaustion_reversal(data)

        logger.info(f"[SIGNALS] S1={s1} | S2={s2} | S3={s3}")

        for sig in (s1, s2, s3):
            if sig != "HOLD":
                return sig
        return "HOLD"

    def _calculate_sl_tp(self, signal: str, entry: float, df1m: pd.DataFrame):
        """
        SL  = recent swing high (short) or swing low (long)
        TP  = entry ± 2 x (entry - SL)   →  1:2 risk-to-reward
        """
        if signal == "BUY":
            sl = self.indicators.recent_swing_low(df1m["low"], lookback=10)
            risk = entry - sl
            tp   = entry + 2 * risk
        else:
            sl   = self.indicators.recent_swing_high(df1m["high"], lookback=10)
            risk = sl - entry
            tp   = entry - 2 * risk

        logger.info(f"[SL/TP] entry={entry:.2f} sl={sl:.2f} tp={tp:.2f} risk={risk:.2f}pts")
        return sl, tp

    def _exit_trade(self) -> None:
        self.broker.close_all_orders()
        self.h_pos       = 0
        self.entry_price = None
        self.sl_price    = None
        self.tp_price    = None
        logger.info("[EXEC] Position closed — h_pos reset to 0.")

    def execute_signals(self, signal: str, data: dict) -> None:
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

            resp         = self.broker.place_order(SYMBOL, "Buy", TRADE_QTY, order_type="Market")
            fill         = resp.get("avgFillPrice") or resp.get("price") or df1m["close"].iloc[-1]
            entry        = float(fill)
            sl, tp       = self._calculate_sl_tp("BUY", entry, df1m)

            self.h_pos       = 1
            self.entry_price = entry
            self.sl_price    = sl
            self.tp_price    = tp
            logger.info(f"[EXEC] BUY {TRADE_QTY} {SYMBOL} @ {entry:.2f} | SL={sl:.2f} TP={tp:.2f}")

        elif signal == "SELL":
            if self.h_pos == -1:
                logger.info("[EXEC] Already holding SELL — skipping.")
                return
            if self.h_pos == 1:
                logger.info("[EXEC] Exiting BUY before entering SELL.")
                self._exit_trade()

            resp         = self.broker.place_order(SYMBOL, "Sell", TRADE_QTY, order_type="Market")
            fill         = resp.get("avgFillPrice") or resp.get("price") or df1m["close"].iloc[-1]
            entry        = float(fill)
            sl, tp       = self._calculate_sl_tp("SELL", entry, df1m)

            self.h_pos       = -1
            self.entry_price = entry
            self.sl_price    = sl
            self.tp_price    = tp
            logger.info(f"[EXEC] SELL {TRADE_QTY} {SYMBOL} @ {entry:.2f} | SL={sl:.2f} TP={tp:.2f}")

    def _check_position_open(self) -> bool:
        """
        Monitor mode — every tick while h_pos != 0:
          1. Check dynamic SL/TP levels against live price
          2. Verify broker still shows an open position
          3. Reset h_pos to 0 if closed externally
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
            None
        )
        if active is None:
            logger.info(f"[MONITOR] Position closed externally — resetting h_pos to 0.")
            self.h_pos = 0; self.entry_price = None
            self.sl_price = None; self.tp_price = None
            return False

        logger.info(
            f"[MONITOR] Position alive | netPos={active.get('netPos')} | "
            f"avgEntry={active.get('netPrice')} | openPnl={active.get('openPnl','n/a')}"
        )
        return True
    
    def main(self) -> None:
        """
        h_pos == 0  →  ENTRY MODE  : run all 3 signals, enter if triggered
        h_pos != 0  →  MONITOR MODE: check dynamic SL/TP + broker position
        """
        try:
            if self.h_pos == 0:
                logger.info("\n[BOT] ENTRY MODE — scanning all signals...")
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
