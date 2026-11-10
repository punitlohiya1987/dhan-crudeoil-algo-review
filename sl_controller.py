
# ==========================================================
# DHAN CRUDEOILM - STOP LOSS CONTROLLER
# VERSION 4.0 - STATE STORE V5 COMPATIBLE
#
# COMMON SL PRICE VALIDATION
# MARGIN / INTRADAY SEPARATE RECONCILIATION
# REGISTERED SL ORDER MATCHING
# REMAINING QUANTITY VALIDATION
# TRIGGER PRICE VALIDATION
# DUPLICATE SL DETECTION
# UNKNOWN SL DETECTION
# MANUAL CANCELLATION LOCK AWARE
#
# READ ONLY
# NO ORDER PLACEMENT
# NO ORDER MODIFICATION
# NO ORDER CANCELLATION
# NO CANCEL AND REPLACE
# ==========================================================

from datetime import datetime


class StopLossController:

    ACTIVE_STATUSES = {
        "PENDING",
        "TRANSIT",
        "PART_TRADED",
        "OPEN",
    }

    TERMINAL_STATUSES = {
        "TRADED",
        "CANCELLED",
        "REJECTED",
        "EXPIRED",
    }

    STOP_ORDER_TYPES = {
        "STOP_LOSS",
        "STOP_LOSS_MARKET",
    }

    def __init__(
        self,
        state_store,
        state,
    ):

        self.state_store = state_store
        self.state = state

        if not isinstance(self.state, dict):
            raise RuntimeError(
                "StopLossController requires valid state."
            )

    # ======================================================
    # HELPERS
    # ======================================================

    def _now(self):

        return datetime.now().isoformat()

    def _integer(self, value, name):

        if isinstance(value, bool):
            raise RuntimeError(
                "Invalid integer: " + name
            )

        try:
            result = int(value)
        except (TypeError, ValueError):
            raise RuntimeError(
                "Invalid integer: " + name
            )

        if result < 0 or result != value:
            raise RuntimeError(
                "Invalid integer: " + name
            )

        return result

    def _price(self, value, name):

        try:
            result = float(value)
        except (TypeError, ValueError):
            raise RuntimeError(
                "Invalid price: " + name
            )

        if result <= 0:
            raise RuntimeError(
                "Invalid price: " + name
            )

        return result

    def _status(self, order):

        return str(
            order.get("orderStatus")
            or order.get("status")
            or ""
        ).upper().strip()

    def _order_id(self, order):

        value = (
            order.get("orderId")
            or order.get("order_id")
        )

        return str(value) if value is not None else None

    def _correlation_id(self, order):

        value = (
            order.get("correlationId")
            or order.get("correlation_id")
        )

        return str(value) if value is not None else None

    # ======================================================
    # RESPONSE NORMALISATION
    # ======================================================

    def _response_orders(self, response):

        if isinstance(response, str):

            import json

            try:
                response = json.loads(response)
            except Exception:
                raise RuntimeError(
                    "Invalid broker orders JSON."
                )

        if isinstance(response, list):
            orders = response

        elif isinstance(response, dict):

            status = response.get("status")

            if status is not None:

                if str(status).lower() not in (
                    "success",
                    "true",
                    "200",
                    "ok",
                ):
                    raise RuntimeError(
                        "Broker orders API returned failure."
                    )

            data = response.get("data")

            if data is None:
                data = response.get("orders")

            if isinstance(data, list):
                orders = data

            elif isinstance(data, dict):

                nested = data.get("orders")

                if isinstance(nested, list):
                    orders = nested
                else:
                    raise RuntimeError(
                        "Unsupported nested broker order response."
                    )

            else:
                raise RuntimeError(
                    "Broker order list is missing."
                )

        else:

            raise RuntimeError(
                "Unsupported broker order response."
            )

        for order in orders:

            if not isinstance(order, dict):
                raise RuntimeError(
                    "Invalid broker order record."
                )

        return orders

    # ======================================================
    # CONTRACT CHECK
    # ======================================================

    def _is_active_contract(self, order):

        active = self.state.get(
            "active_contract",
            {},
        )

        security_id = (
            order.get("securityId")
            or order.get("security_id")
        )

        segment = (
            order.get("exchangeSegment")
            or order.get("exchange_segment")
        )

        return (
            str(security_id) == str(active.get("security_id"))
            and
            str(segment) == str(active.get("exchange_segment"))
        )

    # ======================================================
    # REGISTERED OPEN QUANTITY BY PRODUCT
    # ======================================================

    def _registered_quantities(self):

        positions = self.state.get(
            "positions",
            {},
        )

        registered = positions.get(
            "registered_positions",
            {},
        )

        if not isinstance(registered, dict):
            raise RuntimeError(
                "Registered positions are invalid."
            )

        totals = {
            "MARGIN": 0,
            "INTRADAY": 0,
        }

        for position_id, record in registered.items():

            if not isinstance(record, dict):
                raise RuntimeError(
                    "Invalid position record: "
                    + str(position_id)
                )

            filled = self._integer(
                record.get("filled_qty"),
                "filled quantity",
            )

            closed = self._integer(
                record.get("closed_qty", 0),
                "closed quantity",
            )

            if closed > filled:
                raise RuntimeError(
                    "Position closed quantity exceeds filled quantity."
                )

            product = str(
                record.get("product_type", "")
            ).upper()

            if product not in totals:
                raise RuntimeError(
                    "Unsupported position product type."
                )

            totals[product] += filled - closed

        return totals

    # ======================================================
    # REGISTERED SL ORDER LOOKUP
    # ======================================================

    def _registered_sl_orders(self):

        orders = self.state.get(
            "orders",
            {},
        )

        group = orders.get(
            "stop_loss_orders",
            {},
        )

        if not isinstance(group, dict):
            raise RuntimeError(
                "Registered SL order group is invalid."
            )

        result = []

        for key, record in group.items():

            if not isinstance(record, dict):
                raise RuntimeError(
                    "Invalid registered SL record."
                )

            payload = record.get("payload", {})

            if not isinstance(payload, dict):
                raise RuntimeError(
                    "Registered SL payload is invalid."
                )

            result.append({
                "key": key,
                "record": record,
                "payload": payload,
                "order_id": str(
                    record.get("order_id") or ""
                ),
                "correlation_id": str(
                    record.get("correlationId")
                    or record.get("correlation_id")
                    or payload.get("correlationId")
                    or ""
                ),
                "product_type": str(
                    record.get("product_type")
                    or payload.get("productType")
                    or ""
                ).upper(),
            })

        return result

    # ======================================================
    # STOP ORDER DETECTION
    # ======================================================

    def _is_stop_order(self, order):

        order_type = str(
            order.get("orderType")
            or order.get("order_type")
            or ""
        ).upper()

        return order_type in self.STOP_ORDER_TYPES

    def _active_contract_stop_orders(
        self,
        broker_orders,
    ):

        result = []

        for order in broker_orders:

            if not self._is_active_contract(order):
                continue

            if not self._is_stop_order(order):
                continue

            status = self._status(order)

            if status in self.ACTIVE_STATUSES:
                result.append(order)

        return result

    # ======================================================
    # MANUAL CANCELLATION LOCK
    # ======================================================

    def _check_cancellation_lock(self):

        if self.state_store.is_locked(
            self.state,
            "STOP_LOSS",
        ):
            raise RuntimeError(
                "SL management blocked by cancellation lock."
            )

    # ======================================================
    # SL TRIGGER VALIDATION
    # ======================================================

    def _expected_trigger(self):

        prices = self.state.get(
            "prices",
            {},
        )

        trigger = prices.get(
            "common_stop_loss"
        )

        if trigger is None:
            raise RuntimeError(
                "Common stop loss price is not available."
            )

        return self._price(
            trigger,
            "common stop loss",
        )

    # ======================================================
    # MATCH REGISTERED ORDER
    # ======================================================

    def _match_registered_order(
        self,
        broker_order,
        registered_orders,
    ):

        broker_id = self._order_id(
            broker_order
        )

        broker_correlation = self._correlation_id(
            broker_order
        )

        matches = []

        for registered in registered_orders:

            id_match = (
                broker_id is not None
                and registered["order_id"]
                and broker_id == registered["order_id"]
            )

            correlation_match = (
                broker_correlation is not None
                and registered["correlation_id"]
                and broker_correlation == registered["correlation_id"]
            )

            if id_match or correlation_match:
                matches.append(registered)

        if len(matches) > 1:
            raise RuntimeError(
                "Broker SL matches multiple registered orders."
            )

        return matches[0] if matches else None

    # ======================================================
    # VALIDATE ONE SL
    # ======================================================

    def _validate_one_sl(
        self,
        broker_order,
        registered,
        product_type,
        expected_quantity,
        expected_trigger,
    ):

        record = registered["record"]
        payload = registered["payload"]

        status = self._status(
            broker_order
        )

        if status not in self.ACTIVE_STATUSES:
            raise RuntimeError(
                "Registered SL is not active."
            )

        broker_id = self._order_id(
            broker_order
        )

        if not broker_id:
            raise RuntimeError(
                "Broker SL order ID is missing."
            )

        if (
            registered["order_id"]
            and broker_id != registered["order_id"]
        ):
            raise RuntimeError(
                "Registered SL order ID mismatch."
            )

        broker_correlation = self._correlation_id(
            broker_order
        )

        if (
            registered["correlation_id"]
            and broker_correlation
            != registered["correlation_id"]
        ):
            raise RuntimeError(
                "Registered SL correlation ID mismatch."
            )

        if not self._is_active_contract(broker_order):
            raise RuntimeError(
                "SL contract mismatch."
            )

        broker_product = str(
            broker_order.get("productType")
            or broker_order.get("product_type")
            or ""
        ).upper()

        if broker_product != product_type:
            raise RuntimeError(
                "SL product type mismatch: "
                + product_type
            )

        broker_transaction = str(
            broker_order.get("transactionType")
            or broker_order.get("transaction_type")
            or ""
        ).upper()

        direction = str(
            self.state["strategy"].get("direction", "")
        ).upper()

        expected_transaction = (
            "BUY"
            if direction == "SELL"
            else "SELL"
        )

        if broker_transaction != expected_transaction:
            raise RuntimeError(
                "SL transaction direction mismatch."
            )

        order_type = str(
            broker_order.get("orderType")
            or ""
        ).upper()

        if order_type not in self.STOP_ORDER_TYPES:
            raise RuntimeError(
                "Broker order is not a supported stop order."
            )

        original_quantity = self._integer(
            broker_order.get("quantity"),
            "broker SL order quantity",
        )

        filled_value = (
            broker_order.get("filledQty")
            if broker_order.get("filledQty") is not None
            else broker_order.get("filledQuantity", 0)
        )

        filled_quantity = self._integer(
            filled_value,
            "broker SL filled quantity",
        )

        if filled_quantity > original_quantity:
            raise RuntimeError(
                "SL filled quantity exceeds original order quantity."
            )

        remaining_quantity = (
            original_quantity - filled_quantity
        )

        if remaining_quantity != expected_quantity:
            raise RuntimeError(
                "SL remaining quantity mismatch for "
                + product_type
                + ". Expected "
                + str(expected_quantity)
                + ", broker reports "
                + str(remaining_quantity)
            )

        trigger_value = (
            broker_order.get("triggerPrice")
            if broker_order.get("triggerPrice") is not None
            else broker_order.get("trigger_price")
        )

        broker_trigger = self._price(
            trigger_value,
            "broker SL trigger",
        )

        if broker_trigger != expected_trigger:
            raise RuntimeError(
                "SL trigger price mismatch for "
                + product_type
            )

        saved_quantity = payload.get("quantity")

        if saved_quantity is not None:

            if int(saved_quantity) != original_quantity:
                raise RuntimeError(
                    "Saved original SL quantity mismatch."
                )

        return {
            "product_type": product_type,
            "order_id": broker_id,
            "correlation_id": broker_correlation,
            "original_quantity": original_quantity,
            "filled_quantity": filled_quantity,
            "remaining_quantity": remaining_quantity,
            "trigger_price": broker_trigger,
            "status": status,
            "required": False,
            "confirmed": True,
        }

    # ======================================================
    # BUILD PLAN
    # ======================================================

    def build_plan(self, broker_orders):

        orders = self._response_orders(
            broker_orders
        )

        self._check_cancellation_lock()

        quantities = self._registered_quantities()

        expected_trigger = self._expected_trigger()

        registered_sl = self._registered_sl_orders()

        active_sl_orders = self._active_contract_stop_orders(
            orders
        )

        direction = str(
            self.state["strategy"].get("direction", "")
        ).upper()

        if direction not in ("BUY", "SELL"):
            raise RuntimeError(
                "Invalid strategy direction."
            )

        plans = []

        matched_broker_ids = set()

        for broker_order in active_sl_orders:

            matched = self._match_registered_order(
                broker_order,
                registered_sl,
            )

            if matched is None:
                raise RuntimeError(
                    "Unknown active SL order found on active contract. "
                    "Automatic management is prohibited."
                )

            broker_id = self._order_id(
                broker_order
            )

            if broker_id in matched_broker_ids:
                raise RuntimeError(
                    "Duplicate broker SL order ID."
                )

            matched_broker_ids.add(broker_id)

            product_type = matched["product_type"]

            if product_type not in quantities:
                raise RuntimeError(
                    "Unknown registered SL product type."
                )

            expected_quantity = quantities[product_type]

            if expected_quantity <= 0:
                raise RuntimeError(
                    "SL exists for a product with no registered open quantity."
                )

            result = self._validate_one_sl(
                broker_order=broker_order,
                registered=matched,
                product_type=product_type,
                expected_quantity=expected_quantity,
                expected_trigger=expected_trigger,
            )

            plans.append(result)

        # Verify that every non-zero registered product
        # has exactly one confirmed active SL.
        for product_type, expected_quantity in quantities.items():

            if expected_quantity == 0:
                continue

            matches = [
                plan
                for plan in plans
                if plan["product_type"] == product_type
            ]

            if len(matches) == 0:
                raise RuntimeError(
                    "Missing registered SL for "
                    + product_type
                    + " quantity "
                    + str(expected_quantity)
                )

            if len(matches) > 1:
                raise RuntimeError(
                    "Multiple active SL orders for "
                    + product_type
                )

        # Every registered active SL must have been found
        # at the broker.
        for registered in registered_sl:

            record_status = str(
                registered["record"].get("status", "")
            ).upper()

            if record_status in self.TERMINAL_STATUSES:
                continue

            if registered["order_id"]:

                found = any(
                    plan["order_id"] == registered["order_id"]
                    for plan in plans
                )

                if not found:

                    # A saved active SL missing from the
                    # broker response must block management.
                    raise RuntimeError(
                        "Registered active SL missing from broker response: "
                        + registered["order_id"]
                    )

        result = {
            "status": "PROTECTION_CONFIRMED",
            "required": False,
            "confirmed": True,
            "direction": direction,
            "common_trigger_price": expected_trigger,
            "total_registered_quantity": (
                quantities["MARGIN"]
                + quantities["INTRADAY"]
            ),
            "product_quantities": dict(quantities),
            "stop_loss_orders": plans,
            "read_only": True,
            "timestamp": self._now(),
        }

        # Save the read-only assessment.
        self.state.setdefault(
            "reconciliation",
            {},
        )["last_sl_assessment"] = result

        self.state_store.save(self.state)

        return result

    # ======================================================
    # PROTECTION CONFIRMATION
    # ======================================================

    def is_protection_confirmed(self, plan):

        if not isinstance(plan, dict):
            return False

        if plan.get("status") != "PROTECTION_CONFIRMED":
            return False

        if plan.get("confirmed") is not True:
            return False

        if plan.get("read_only") is not True:
            return False

        expected_total = (
            plan.get("product_quantities", {}).get("MARGIN", 0)
            +
            plan.get("product_quantities", {}).get("INTRADAY", 0)
        )

        if expected_total != plan.get("total_registered_quantity"):
            return False

        for product_type, quantity in plan.get(
            "product_quantities",
            {},
        ).items():

            if quantity <= 0:
                continue

            matches = [
                order
                for order in plan.get("stop_loss_orders", [])
                if order.get("product_type") == product_type
                and order.get("confirmed") is True
                and order.get("remaining_quantity") == quantity
            ]

            if len(matches) != 1:
                return False

        return True
