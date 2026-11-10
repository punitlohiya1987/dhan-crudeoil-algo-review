
# ==========================================================
# DHAN CRUDEOILM - DHAN API CLIENT
# VERSION 5.1 - CLOUDHQ SECURITY COMPATIBLE
#
# DHAN HQ API V2
# READ-ONLY MARKET / ACCOUNT DATA
# ORDER BOOK / TRADE BOOK / POSITIONS
# ORDER LOOKUP BY ID / CORRELATION ID
# LIVE LTP MARKETFEED
#
# ORDER WRITE METHODS SAFETY LOCKED
# NO AUTOMATIC RETRY
# NO HIDDEN ORDER SUBMISSION
# ==========================================================

import json
import urllib.request
import urllib.error

import config


BASE_URL = "https://api.dhan.co/v2"
REQUEST_TIMEOUT = 20


class DhanClient:

    def __init__(self):

        self.client_id = str(
            config.DHAN_CLIENT_ID or ""
        ).strip()

        self.access_token = str(
            config.DHAN_ACCESS_TOKEN or ""
        ).strip()

        self.order_placement_enabled = (
            config.ORDER_PLACEMENT_ENABLED is True
        )

        self.position_conversion_enabled = (
            config.POSITION_CONVERSION_ENABLED is True
        )

        self.live_trading_enabled = (
            config.LIVE_TRADING_ENABLED is True
        )

        self.trading_mode = str(
            config.TRADING_MODE
        ).upper()

        if not self.client_id or not self.access_token:
            raise RuntimeError(
                "Dhan credentials missing. "
                "CloudHQ secure configuration check karein."
            )

    # ======================================================
    # COMMON HTTP REQUEST
    # ======================================================

    def _request(
        self,
        endpoint,
        method="GET",
        payload=None,
        allow_write=False,
    ):

        method = str(method).upper()

        if not endpoint or not str(endpoint).startswith("/"):
            raise RuntimeError(
                "Invalid Dhan API endpoint."
            )

        if method not in ("GET", "POST", "PUT", "DELETE"):
            raise RuntimeError(
                "Unsupported HTTP method."
            )

        if method in ("PUT", "DELETE"):
            if allow_write is not True:
                raise RuntimeError(
                    "Broker write request is blocked."
                )

        if method == "POST" and allow_write is not True:
            if endpoint not in (
                "/marketfeed/ltp",
                "/marketfeed/ohlc",
                "/marketfeed/quote",
            ):
                raise RuntimeError(
                    "POST request is not an approved read operation."
                )

        if allow_write is True:

            if self.trading_mode != "LIVE":
                raise RuntimeError(
                    "Broker write blocked: trading mode is not LIVE."
                )

            if self.live_trading_enabled is not True:
                raise RuntimeError(
                    "Broker write blocked: live trading is disabled."
                )

            if self.order_placement_enabled is not True:
                raise RuntimeError(
                    "Broker write blocked by order placement switch."
                )

        url = BASE_URL + endpoint

        headers = {
            "access-token": self.access_token,
            "client-id": self.client_id,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        body = None

        if payload is not None:
            body = json.dumps(
                payload,
                separators=(",", ":"),
            ).encode("utf-8")

        request = urllib.request.Request(
            url=url,
            data=body,
            headers=headers,
            method=method,
        )

        try:

            with urllib.request.urlopen(
                request,
                timeout=REQUEST_TIMEOUT,
            ) as response:

                raw = response.read().decode("utf-8")

                if not raw:
                    return {}

                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    raise RuntimeError(
                        "Dhan API returned invalid JSON."
                    )

        except urllib.error.HTTPError as error:

            try:
                error_body = error.read().decode("utf-8")
            except Exception:
                error_body = ""

            raise RuntimeError(
                "Dhan HTTP error "
                + str(error.code)
                + ": "
                + error_body[:1000]
            )

        except urllib.error.URLError as error:

            raise RuntimeError(
                "Dhan network error: "
                + str(error.reason)
            )

        except TimeoutError:

            raise RuntimeError(
                "Dhan API request timed out. "
                "Request was not automatically retried."
            )

    # ======================================================
    # RESPONSE LIST NORMALIZATION
    # ======================================================

    def _extract_list(self, response, possible_keys):

        if isinstance(response, list):
            return response

        if isinstance(response, str):

            try:
                response = json.loads(response)
            except json.JSONDecodeError:
                raise RuntimeError(
                    "Dhan response string is invalid."
                )

        if not isinstance(response, dict):
            raise RuntimeError(
                "Unexpected Dhan response format."
            )

        for key in possible_keys:

            value = response.get(key)

            if isinstance(value, list):
                return value

        data = response.get("data")

        if isinstance(data, list):
            return data

        if isinstance(data, dict):

            for key in possible_keys:

                value = data.get(key)

                if isinstance(value, list):
                    return value

        raise RuntimeError(
            "Expected list was not found in Dhan response."
        )

    # ======================================================
    # POSITIONS
    # ======================================================

    def get_positions(self):

        return self._request(
            "/positions",
            method="GET",
        )

    # ======================================================
    # ORDER BOOK
    # ======================================================

    def get_orders(self):

        response = self._request(
            "/orders",
            method="GET",
        )

        return self._extract_list(
            response,
            (
                "data",
                "orders",
                "orderList",
            ),
        )

    # ======================================================
    # FUND LIMITS
    # ======================================================

    def get_fund_limits(self):

        return self._request(
            "/fundlimit",
            method="GET",
        )

    # ======================================================
    # TRADE HISTORY
    # ======================================================

    def get_trade_history(self):

        return self._request(
            "/trades",
            method="GET",
        )

    # ======================================================
    # HOLDINGS
    # ======================================================

    def get_holdings(self):

        return self._request(
            "/holdings",
            method="GET",
        )

    # ======================================================
    # ORDER LOOKUP BY ID
    # ======================================================

    def get_order_by_id(self, order_id):

        if not order_id:
            raise RuntimeError(
                "Order ID is required."
            )

        return self._request(
            "/orders/" + str(order_id),
            method="GET",
        )

    # ======================================================
    # ORDER LOOKUP BY CORRELATION ID
    # ======================================================

    def get_order_by_correlation(self, correlation_id):

        if not correlation_id:
            raise RuntimeError(
                "Correlation ID is required."
            )

        orders = self.get_orders()
        matches = []

        for order in orders:

            if not isinstance(order, dict):
                continue

            broker_correlation = str(
                order.get("correlationId")
                or order.get("correlation_id")
                or ""
            )

            if broker_correlation == str(correlation_id):
                matches.append(order)

        if len(matches) > 1:
            raise RuntimeError(
                "Multiple broker orders share the same correlation ID."
            )

        if not matches:
            return None

        return matches[0]

    # ======================================================
    # LIVE MARKETFEED LTP
    # ======================================================

    def get_ltp(
        self,
        exchange_segment,
        security_id,
    ):

        if not exchange_segment or not security_id:
            raise RuntimeError(
                "Exchange segment and security ID are required."
            )

        payload = {
            str(exchange_segment): [
                str(security_id)
            ]
        }

        response = self._request(
            "/marketfeed/ltp",
            method="POST",
            payload=payload,
            allow_write=False,
        )

        if not isinstance(response, dict):
            raise RuntimeError(
                "Invalid Dhan LTP response."
            )

        data = response.get("data", {})

        if not isinstance(data, dict):
            raise RuntimeError(
                "Dhan LTP data is missing."
            )

        segment_data = data.get(
            str(exchange_segment),
            {},
        )

        if not isinstance(segment_data, dict):
            raise RuntimeError(
                "Dhan LTP segment response is invalid."
            )

        instrument_data = segment_data.get(
            str(security_id)
        )

        if not isinstance(instrument_data, dict):
            raise RuntimeError(
                "Requested instrument LTP was not returned."
            )

        ltp = instrument_data.get("last_price")

        if ltp is None:
            ltp = instrument_data.get("ltp")

        try:
            ltp = float(ltp)
        except (TypeError, ValueError):
            raise RuntimeError(
                "Dhan returned invalid LTP."
            )

        if ltp <= 0:
            raise RuntimeError(
                "Dhan returned non-positive LTP."
            )

        return ltp

    # ======================================================
    # ORDER PLACEMENT - LOCKED
    # ======================================================

    def place_order(self, payload):

        raise RuntimeError(
            "Order placement is locked in this build. "
            "No broker order was submitted."
        )

    # ======================================================
    # ORDER MODIFICATION - LOCKED
    # ======================================================

    def modify_order(self, order_id, payload):

        raise RuntimeError(
            "Order modification is locked in this build. "
            "No broker modification was submitted."
        )

    # ======================================================
    # ORDER CANCELLATION - LOCKED
    # ======================================================

    def cancel_order(self, order_id):

        raise RuntimeError(
            "Order cancellation is locked in this build. "
            "No broker cancellation was submitted."
        )

    # ======================================================
    # POSITION CONVERSION - LOCKED
    # ======================================================

    def convert_position(self, payload):

        if self.position_conversion_enabled is not True:
            raise RuntimeError(
                "Position conversion is disabled."
            )

        raise RuntimeError(
            "Position conversion is not released in this build."
        )
