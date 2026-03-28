import requests

BASE_URL = "https://demo.tradovateapi.com/v1"  # swap to live.tradovateapi.com for production


class TradovateBroker:
    def __init__(self, username: str, password: str, app_id: str, app_version: str, device_id: str, cid: str, sec: str):
        self.username = username
        self.password = password
        self.app_id = app_id
        self.app_version = app_version
        self.device_id = device_id
        self.cid = cid
        self.sec = sec

        self.access_token = None
        self.account_id = None
        self.session = requests.Session()

    def connect(self) -> None:
        """Authenticate and store the access token + account id."""
        payload = {
            "name": self.username,
            "password": self.password,
            "appId": self.app_id,
            "appVersion": self.app_version,
            "deviceId": self.device_id,
            "cid": self.cid,
            "sec": self.sec,
        }
        resp = self.session.post(f"{BASE_URL}/auth/accesstokenrequest", json=payload)
        resp.raise_for_status()
        data = resp.json()

        self.access_token = data["accessToken"]
        self.session.headers.update({"Authorization": f"Bearer {self.access_token}"})

        accounts = self._get("account/list")
        if not accounts:
            raise RuntimeError("No accounts found for this user.")
        self.account_id = accounts[0]["id"]
        print(f"Connected. Account ID: {self.account_id}")

    def fetch_data(self, contract_id: int) -> dict:
        """Return the latest quote for a given contract id."""
        return self._get(f"md/getQuote?contractId={contract_id}")

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
        print(f"Order placed: {data}")
        return data

    def cancel_order(self, order_id: int) -> dict:
        """Cancel a specific order by its id."""
        data = self._post("order/cancelorder", {"orderId": order_id})
        print(f"Order {order_id} cancelled: {data}")
        return data

    def close_all_orders(self) -> list:
        """Cancel every open order on the account."""
        open_orders = self._get(f"order/list?accountId={self.account_id}")
        results = []
        for order in open_orders:
            if order.get("ordStatus") in ("Working", "PendingNew"):
                results.append(self.cancel_order(order["id"]))
        print(f"Closed {len(results)} open order(s).")
        return results

    def set_leverage(self) -> None:
        """Not supported — Tradovate uses fixed margin per contract."""
        raise NotImplementedError("Tradovate does not expose a leverage-setting endpoint.")

    def get_trade(self, order_id: int) -> dict:
        """
        Fetch full details for a single order by its id.

        Returns a dict containing:
            id, accountId, contractId, timestamp, action,
            orderQty, orderType, price, fillPrice, ordStatus,
            filledQty, avgFillPrice, and more.
        """
        return self._get(f"order/item?id={order_id}")

    def get_open_positions(self) -> list[dict]:
        """
        Return all open positions on the account.

        Each position dict contains:
            id, accountId, contractId, netPos (+ long / - short),
            netPrice (avg entry), realizedPnl, openPnl, and more.
        """
        return self._get(f"position/list?accountId={self.account_id}")

    def get_trade_history(self, n: int = 50) -> list[dict]:
        """
        Return the last `n` filled orders (executions) for the account.

        Each fill dict contains:
            id, orderId, contractId, timestamp, action,
            qty, price, commission, and more.
        """
        fills = self._get(f"fill/list?accountId={self.account_id}")
        # Tradovate returns chronological — return most-recent first
        return list(reversed(fills))[:n]

    def get_account_summary(self) -> dict:
        """
        Return a snapshot of account cash, P&L, and margin.

        Combines:
            /cashBalance/getcashbalancesnapshot  → balance, realizedPnl, openPnl
            /marginSnapshot/list                 → initialMargin, maintenanceMargin

        Returns a single flat dict for easy consumption.
        """
        balance       = self._post("cashBalance/getcashbalancesnapshot", {"accountId": self.account_id})
        margins       = self._get(f"marginSnapshot/list?accountId={self.account_id}")
        latest_margin = margins[-1] if margins else {}

        return {
            # Cash & P&L
            "cash_balance":       balance.get("cashBalance"),
            "realized_pnl":       balance.get("realizedPnl"),
            "open_pnl":           balance.get("openPnl"),
            "net_liquidation":    balance.get("netLiquidatingValue"),
            # Margin
            "initial_margin":     latest_margin.get("initialMargin"),
            "maintenance_margin": latest_margin.get("maintenanceMargin"),
            "excess_margin":      latest_margin.get("excessMargin"),
        }

    def get_position_pnl(self, contract_id: int) -> dict:
        """
        Return live P&L details for a single open position.

        Looks up the position by contractId, then fetches the current
        market price so open_pnl is always fresh.

        Returns:
            contract_id, net_pos, avg_entry, current_price,
            open_pnl, realized_pnl
        """
        positions = self.get_open_positions()
        pos = next((p for p in positions if p.get("contractId") == contract_id), None)
        if pos is None:
            return {"error": f"No open position for contractId={contract_id}"}

        quote         = self.fetch_data(contract_id)
        current_price = quote.get("last") or quote.get("bid") or 0.0

        net_pos   = pos.get("netPos", 0)
        avg_entry = pos.get("netPrice", 0.0)
        open_pnl  = (current_price - avg_entry) * net_pos   # negative net_pos flips sign for shorts

        return {
            "contract_id":   contract_id,
            "net_pos":       net_pos,
            "avg_entry":     avg_entry,
            "current_price": current_price,
            "open_pnl":      open_pnl,
            "realized_pnl":  pos.get("realizedPnl", 0.0),
        }

    def _get(self, endpoint: str):
        resp = self.session.get(f"{BASE_URL}/{endpoint}")
        resp.raise_for_status()
        return resp.json()

    def _post(self, endpoint: str, payload: dict):
        resp = self.session.post(f"{BASE_URL}/{endpoint}", json=payload)
        resp.raise_for_status()
        return resp.json()