import requests
from logger import get_logger
from config import *

logger = get_logger()

BASE_URL = "https://demo.tradovateapi.com/v1"  # swap to live.tradovateapi.com for production

class TradovateBroker:
    def __init__(self, username: str, password: str, app_id: str, app_version: str, device_id: str, cid: str, sec: str):
        self.username    = username
        self.password    = password
        self.app_id      = app_id
        self.app_version = app_version
        self.device_id   = device_id
        self.cid         = cid
        self.sec         = sec

        self.access_token = None
        self.account_id   = None
        self.session      = requests.Session()

    def connect(self) -> None:
        """Authenticate and store the access token + account id."""
        payload = {
            "name":        self.username,
            "password":    self.password,
            "appId":       self.app_id,
            "appVersion":  self.app_version,
            "deviceId":    self.device_id,
            "cid":         self.cid,
            "sec":         self.sec,
            "environment": "demo",   # required for demo auth flow
            "enc":         True,     # password is pre-encoded by Tradovate
        }

        logger.debug(f"Connecting to Tradovate as {self.username}...")
        resp = self.session.post(f"{BASE_URL}/auth/accesstokenrequest", json=payload)
        data = resp.json()

        if "accessToken" not in data:
            logger.error(f"Auth failed: {data}")
            raise RuntimeError(f"Tradovate auth failed: {data.get('errorText', data)}")

        self.access_token = data["accessToken"]
        self.session.headers.update({"Authorization": f"Bearer {self.access_token}"})
        logger.debug(f"Access token acquired.")

        accounts = self._get("account/list")
        if not accounts:
            raise RuntimeError("No accounts found for this user.")
        self.account_id = accounts[0]["id"]
        logger.info(f"Connected. Account ID: {self.account_id}")

    def fetch_data(self, contract_id: int) -> dict:
        """Return the latest quote for a given contract id."""
        data = self._get(f"md/getQuote?contractId={contract_id}")
        logger.debug(f"Quote for contractId={contract_id}: {data}")
        return data

    def place_order(
        self,
        symbol: str,
        action: str,
        quantity: int,
        order_type: str = "Market",
        price: float = None,
        stop_price: float = None,
    ) -> dict:
        """Place an order and return the order response."""
        payload = {
            "accountSpec": self.username,
            "accountId":   self.account_id,
            "action":      action,
            "symbol":      symbol,
            "orderQty":    quantity,
            "orderType":   order_type,
            "isAutomated": True,
        }
        if price is not None:
            payload["price"] = price
        if stop_price is not None:
            payload["stopPrice"] = stop_price

        data = self._post("order/placeorder", payload)
        logger.info(f"Order placed: action={action} symbol={symbol} qty={quantity} type={order_type} → {data}")
        return data

    def cancel_order(self, order_id: int) -> dict:
        """Cancel a specific order by its id."""
        data = self._post("order/cancelorder", {"orderId": order_id})
        logger.info(f"Order {order_id} cancelled: {data}")
        return data

    def close_all_orders(self) -> list:
        """Close open position and cancel all working orders on the account."""
        # Cancel all working orders
        open_orders = self._get(f"order/list?accountId={self.account_id}")
        results = []
        for order in open_orders:
            if order.get("ordStatus") in ("Working", "PendingNew"):
                results.append(self.cancel_order(order["id"]))

        # Liquidate any open position via closeContract
        positions = self.get_open_positions()
        for pos in positions:
            if pos.get("netPos", 0) != 0:
                liq = self._post("order/liquidateposition", {
                    "accountId":  self.account_id,
                    "contractId": pos["contractId"],
                    "admin":      False,
                })
                logger.info(f"Liquidated position contractId={pos['contractId']}: {liq}")
                results.append(liq)

        logger.info(f"close_all_orders: {len(results)} action(s) taken.")
        return results

    def get_trade(self, order_id: int) -> dict:
        """Fetch full details for a single order by its id."""
        data = self._get(f"order/item?id={order_id}")
        logger.debug(f"Trade details for orderId={order_id}: {data}")
        return data

    def get_open_positions(self) -> list[dict]:
        """Return all open positions on the account."""
        data = self._get(f"position/list?accountId={self.account_id}")
        logger.debug(f"Open positions: {data}")
        return data

    def get_trade_history(self, n: int = 50) -> list[dict]:
        """Return the last `n` filled orders, most-recent first."""
        fills = self._get(f"fill/list?accountId={self.account_id}")
        recent = list(reversed(fills))[:n]
        logger.debug(f"Trade history ({len(recent)} fills): {recent}")
        return recent

    def get_account_summary(self) -> dict:
        """Return a snapshot of account cash, P&L, and margin."""
        balance       = self._post("cashBalance/getcashbalancesnapshot", {"accountId": self.account_id})
        margins       = self._get(f"marginSnapshot/list?accountId={self.account_id}")
        latest_margin = margins[-1] if margins else {}

        summary = {
            "cash_balance":       balance.get("cashBalance"),
            "realized_pnl":       balance.get("realizedPnl"),
            "open_pnl":           balance.get("openPnl"),
            "net_liquidation":    balance.get("netLiquidatingValue"),
            "initial_margin":     latest_margin.get("initialMargin"),
            "maintenance_margin": latest_margin.get("maintenanceMargin"),
            "excess_margin":      latest_margin.get("excessMargin"),
        }
        logger.debug(f"Account summary: {summary}")
        return summary

    def get_position_pnl(self, contract_id: int) -> dict:
        """Return live P&L details for a single open position."""
        positions = self.get_open_positions()
        pos = next((p for p in positions if p.get("contractId") == contract_id), None)
        if pos is None:
            logger.warning(f"No open position found for contractId={contract_id}")
            return {"error": f"No open position for contractId={contract_id}"}

        quote         = self.fetch_data(contract_id)
        current_price = quote.get("last") or quote.get("bid") or 0.0
        net_pos       = pos.get("netPos", 0)
        avg_entry     = pos.get("netPrice", 0.0)
        open_pnl      = (current_price - avg_entry) * net_pos

        result = {
            "contract_id":   contract_id,
            "net_pos":       net_pos,
            "avg_entry":     avg_entry,
            "current_price": current_price,
            "open_pnl":      open_pnl,
            "realized_pnl":  pos.get("realizedPnl", 0.0),
        }
        logger.debug(f"Position PnL: {result}")
        return result

    def _get(self, endpoint: str):
        resp = self.session.get(f"{BASE_URL}/{endpoint}")
        if not resp.ok:
            logger.error(f"GET {endpoint} failed [{resp.status_code}]: {resp.text}")
        resp.raise_for_status()
        return resp.json()

    def _post(self, endpoint: str, payload: dict):
        resp = self.session.post(f"{BASE_URL}/{endpoint}", json=payload)
        if not resp.ok:
            logger.error(f"POST {endpoint} failed [{resp.status_code}]: {resp.text}")
        resp.raise_for_status()
        return resp.json()
    
if __name__ == "__main__":
    broker = TradovateBroker(username=USERNAME,password=PASSWORD,app_id=APP_ID,app_version=APP_VERSION,device_id=DEVICE_ID,cid=CID,sec=SEC)
    broker.connect() # check the connection
    df = broker.fetch_data(contract_id=CONTRACT_ID) # id for MSEM6 - may change after april so check
    print(df)
    place_order_response = broker.place_order(symbol=SYMBOL,action="BUY",quantity=1,order_type="Market",price=None,stop_price=None) # try placing a market 
    print(place_order_response)
    price = df['close'].iloc[-1]*1.01 # one percent higher price to buy
    print(df['close'].iloc[-1]) # the latest price of the close price
    print(df['close'].iloc[-2]) # get this price to check the validity of data , by comparing it in tradingview
    print(price) # price calculated
    get_trade_response = broker.get_trade(order_id="") # use this to check if the open posn != 0
    print(get_trade_response)
    cancel_order_response = broker.cancel_order(order_id="") # this should be filled based on the response that you get from placing the order
    print(cancel_order_response)
    limit_order_response = broker.place_order(symbol=SYMBOL,action="BUY",quantity=1,order_type="Limit",price=price,stop_price=price-1) # check the condition for a stop_price , when triggered
    print(limit_order_response)
    acc_summary = broker.get_account_summary() # get knowledge about the account 
    print(acc_summary)
    posn_pnl = broker.get_position_pnl(contract_id=CONTRACT_ID) # get the posn for the contracts 
    print(posn_pnl)
    trade_hist = broker.get_trade_history(n=5) # get the info for the last 5 trades
    print(trade_hist)
    open_posn = broker.get_open_positions() # get the positions 
    print(open_posn)
    cancel_order_response = broker.close_all_orders() # check if this function is working
    print(cancel_order_response)

