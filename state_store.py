
# ==========================================================
# DHAN COMMON STATE STORE
# VERSION 5.1 - CLOUDHQ COMPATIBLE
#
# CANONICAL POSITION SCHEMA
# filled_qty / closed_qty
#
# CHECKSUM VALIDATION
# MANUAL CANCELLATION LOCKS
# WRITE-AHEAD INTENT CHECK
# FAIL-CLOSED VALIDATION
#
# NO os MODULE
# NO TEMP FILE OPERATIONS
# NO BROKER API CALLS
# ==========================================================

import json
import hashlib
from datetime import datetime


class StateStore:

    STATE_VERSION = 5

    REQUIRED_SECTIONS = (
        "active_contract",
        "strategy",
        "prices",
        "positions",
        "orders",
        "manual_cancel_locks",
        "reconciliation",
    )

    REQUIRED_ORDER_GROUPS = (
        "pending_entry_orders",
        "stop_loss_orders",
        "order_fill_totals",
        "manual_cancelled_orders",
    )

    LOCK_ROLES = (
        "ENTRY_LIMIT",
        "STOP_LOSS",
    )

    UNRESOLVED_ORDER_STATUSES = {
        "SUBMISSION_PENDING",
        "SUBMISSION_UNCERTAIN",
        "VERIFICATION_REQUIRED",
        "MODIFICATION_PENDING",
        "MODIFICATION_UNCERTAIN",
    }

    def __init__(self, file_path="state.json"):

        self.file_path = str(file_path).strip()

        if not self.file_path:
            raise ValueError("State file path is required.")

    # ======================================================
    # HELPERS
    # ======================================================

    def _now(self):
        return datetime.now().isoformat()

    def _require_dict(self, value, name):

        if not isinstance(value, dict):
            raise RuntimeError(
                "Invalid state section: " + str(name)
            )

    def _integer(self, value, name, minimum=0):

        if isinstance(value, bool):
            raise RuntimeError(
                "Invalid integer field: " + str(name)
            )

        try:
            number = int(value)
        except (TypeError, ValueError):
            raise RuntimeError(
                "Invalid integer field: " + str(name)
            )

        if number != value or number < minimum:
            raise RuntimeError(
                "Invalid integer field: " + str(name)
            )

        return number

    def _number(self, value, name, minimum=0):

        try:
            number = float(value)
        except (TypeError, ValueError):
            raise RuntimeError(
                "Invalid numeric field: " + str(name)
            )

        if number != number or number in (
            float("inf"),
            float("-inf"),
        ):
            raise RuntimeError(
                "Invalid numeric field: " + str(name)
            )

        if number < minimum:
            raise RuntimeError(
                "Invalid numeric field: " + str(name)
            )

        return number

    def _canonical_json(self, state):

        return json.dumps(
            state,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def _calculate_checksum(self, state):

        payload = dict(state)
        payload.pop("checksum", None)

        encoded = self._canonical_json(
            payload
        ).encode("utf-8")

        return hashlib.sha256(encoded).hexdigest()

    # ======================================================
    # VALIDATION
    # ======================================================

    def validate(self, state, verify_checksum=True):

        self._require_dict(state, "root")

        if state.get("state_version") != self.STATE_VERSION:
            raise RuntimeError(
                "State version mismatch. Expected version 5."
            )

        for section in self.REQUIRED_SECTIONS:
            self._require_dict(
                state.get(section),
                section,
            )

        active = state["active_contract"]
        strategy = state["strategy"]
        prices = state["prices"]
        positions = state["positions"]
        orders = state["orders"]
        locks = state["manual_cancel_locks"]
        reconciliation = state["reconciliation"]

        # ACTIVE CONTRACT

        for field in (
            "symbol",
            "security_id",
            "expiry",
            "exchange_segment",
        ):

            if not str(active.get(field, "")).strip():
                raise RuntimeError(
                    "Missing active contract field: " + field
                )

        # STRATEGY

        direction = str(
            strategy.get("direction", "")
        ).upper()

        if direction not in ("BUY", "SELL"):
            raise RuntimeError("Invalid strategy direction.")

        execution_id = strategy.get("execution_id")

        if execution_id is not None:

            if (
                not isinstance(execution_id, str)
                or not execution_id.strip()
            ):
                raise RuntimeError("Invalid execution ID.")

        for field in (
            "cycle_active",
            "cycle_closed",
        ):

            if not isinstance(strategy.get(field), bool):
                raise RuntimeError(
                    "Invalid strategy flag: " + field
                )

        for field in (
            "lots_per_entry",
            "lot_size",
            "quantity_per_entry",
            "grid_points",
            "stop_loss_points",
            "maximum_entries",
            "maximum_overnight_lots",
        ):

            self._integer(
                strategy.get(field),
                "strategy." + field,
                minimum=1,
            )

        if (
            strategy["lots_per_entry"]
            * strategy["lot_size"]
            != strategy["quantity_per_entry"]
        ):
            raise RuntimeError(
                "Strategy entry quantity does not match lot configuration."
            )

        # PRICES

        for field in (
            "initial_entry",
            "last_entry",
            "next_grid",
            "common_stop_loss",
        ):

            value = prices.get(field)

            if value is not None:
                self._number(
                    value,
                    "prices." + field,
                    minimum=0,
                )

        # REGISTERED POSITIONS

        registered = positions.get(
            "registered_positions"
        )

        self._require_dict(
            registered,
            "positions.registered_positions",
        )

        calculated_total = 0
        calculated_margin = 0
        calculated_intraday = 0

        for position_id, position in registered.items():

            self._require_dict(
                position,
                "registered position " + str(position_id),
            )

            filled = self._integer(
                position.get("filled_qty"),
                "position.filled_qty",
            )

            closed = self._integer(
                position.get("closed_qty", 0),
                "position.closed_qty",
            )

            if closed > filled:
                raise RuntimeError(
                    "Closed quantity exceeds filled quantity."
                )

            product_type = str(
                position.get("product_type", "")
            ).upper()

            if product_type not in ("MARGIN", "INTRADAY"):
                raise RuntimeError(
                    "Invalid registered position product type."
                )

            self._number(
                position.get("average_price"),
                "position.average_price",
                minimum=0.000001,
            )

            open_quantity = filled - closed

            calculated_total += open_quantity

            if product_type == "MARGIN":
                calculated_margin += open_quantity
            else:
                calculated_intraday += open_quantity

        stored_total = self._integer(
            positions.get("total_quantity"),
            "positions.total_quantity",
        )

        stored_margin = self._integer(
            positions.get("margin_quantity"),
            "positions.margin_quantity",
        )

        stored_intraday = self._integer(
            positions.get("intraday_quantity"),
            "positions.intraday_quantity",
        )

        stored_sl_quantity = self._integer(
            positions.get("common_stop_loss_quantity"),
            "positions.common_stop_loss_quantity",
        )

        if calculated_total != stored_total:
            raise RuntimeError(
                "Registered position total mismatch."
            )

        if calculated_margin != stored_margin:
            raise RuntimeError(
                "Registered MARGIN quantity mismatch."
            )

        if calculated_intraday != stored_intraday:
            raise RuntimeError(
                "Registered INTRADAY quantity mismatch."
            )

        if calculated_total != (
            calculated_margin + calculated_intraday
        ):
            raise RuntimeError(
                "Registered product quantities do not reconcile."
            )

        if stored_sl_quantity > calculated_total:
            raise RuntimeError(
                "Common SL quantity exceeds registered open quantity."
            )

        # ORDER GROUPS

        for group in self.REQUIRED_ORDER_GROUPS:

            self._require_dict(
                orders.get(group),
                "orders." + group,
            )

        # MANUAL CANCELLATION LOCKS

        for role in self.LOCK_ROLES:

            if not isinstance(locks.get(role), bool):
                raise RuntimeError(
                    "Invalid manual cancellation lock: " + role
                )

        lock_records = locks.get("records", [])

        if not isinstance(lock_records, list):
            raise RuntimeError(
                "Invalid manual cancellation records."
            )

        for record in lock_records:
            self._require_dict(
                record,
                "manual cancellation record",
            )

        # RECONCILIATION

        for field in (
            "positions_checked",
            "orders_checked",
        ):

            if not isinstance(reconciliation.get(field), bool):
                raise RuntimeError(
                    "Invalid reconciliation flag: " + field
                )

        # CHECKSUM

        if verify_checksum:

            saved_checksum = state.get("checksum")

            if (
                not isinstance(saved_checksum, str)
                or not saved_checksum
            ):
                raise RuntimeError("State checksum is missing.")

            if saved_checksum != self._calculate_checksum(state):
                raise RuntimeError(
                    "State checksum validation failed."
                )

        return True

    # ======================================================
    # LOAD
    # ======================================================

    def load(self):

        try:

            with open(
                self.file_path,
                "r",
                encoding="utf-8",
            ) as file:

                state = json.load(file)

        except FileNotFoundError:

            raise RuntimeError(
                "State file does not exist. "
                "Automatic state creation is prohibited."
            )

        except Exception as error:

            raise RuntimeError(
                "Unable to read saved state: " + str(error)
            )

        self.validate(
            state,
            verify_checksum=True,
        )

        return state

    # ======================================================
    # SAVE
    # ======================================================

    def save(self, state):

        self._require_dict(state, "root")

        state["updated_at"] = self._now()
        state.pop("checksum", None)

        self.validate(
            state,
            verify_checksum=False,
        )

        state["checksum"] = self._calculate_checksum(state)

        try:

            with open(
                self.file_path,
                "w",
                encoding="utf-8",
            ) as file:

                json.dump(
                    state,
                    file,
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                )

                file.flush()

        except Exception as error:

            raise RuntimeError(
                "State save failed. Execution must stop: "
                + str(error)
            )

        # READ-BACK VALIDATION

        try:

            with open(
                self.file_path,
                "r",
                encoding="utf-8",
            ) as file:

                saved_state = json.load(file)

        except Exception as error:

            raise RuntimeError(
                "State read-back failed: " + str(error)
            )

        self.validate(
            saved_state,
            verify_checksum=True,
        )

        return True

    # ======================================================
    # MANUAL CANCELLATION LOCK
    # ======================================================

    def set_manual_cancel_lock(
        self,
        state,
        role,
        active=True,
        record=None,
    ):

        role = str(role).upper()

        if role not in self.LOCK_ROLES:
            raise ValueError("Unknown cancellation lock role.")

        if not isinstance(active, bool):
            raise ValueError("Lock state must be boolean.")

        locks = state.setdefault(
            "manual_cancel_locks",
            {},
        )

        locks[role] = active

        if active:

            locks["status"] = "LOCKED"
            locks["updated_at"] = self._now()

            if record is not None:

                if not isinstance(record, dict):
                    raise ValueError(
                        "Cancellation record must be a dictionary."
                    )

                records = locks.setdefault("records", [])

                if not isinstance(records, list):
                    raise RuntimeError(
                        "Invalid cancellation record list."
                    )

                saved_record = dict(record)

                saved_record["role"] = role
                saved_record["source"] = (
                    "EXTERNAL_OR_BROKER_UNCONFIRMED"
                )
                saved_record["recorded_at"] = self._now()

                records.append(saved_record)

        else:

            locks["status"] = (
                "LOCKED"
                if any(
                    locks.get(item) is True
                    for item in self.LOCK_ROLES
                )
                else "UNLOCKED"
            )

            locks["updated_at"] = self._now()

        self.save(state)

        return True

    def register_cancelled_order(
        self,
        state,
        record,
        role,
    ):

        if not isinstance(record, dict):
            raise ValueError(
                "Cancelled order record is required."
            )

        return self.set_manual_cancel_lock(
            state=state,
            role=role,
            active=True,
            record=record,
        )

    def is_locked(self, state, role):

        role = str(role).upper()

        if role not in self.LOCK_ROLES:
            raise ValueError("Unknown cancellation lock role.")

        locks = state.get("manual_cancel_locks", {})

        if not isinstance(locks, dict):
            raise RuntimeError(
                "Invalid manual cancellation lock state."
            )

        return locks.get(role) is not False

    # ======================================================
    # RECONCILIATION
    # ======================================================

    def begin_fresh_execution(
        self,
        state,
        execution_id,
        broker_positions_flat=False,
        broker_open_orders_clear=False,
    ):
        """
        Release cancellation locks only for an explicit new execution,
        after broker checks confirm this contract is flat and has no
        working orders. Never call automatically on process restart.
        """
        self.validate(state, verify_checksum=True)

        execution_id = str(execution_id or "").strip()
        if not execution_id:
            raise ValueError("A new execution ID is required.")

        strategy = state["strategy"]
        positions = state["positions"]
        orders = state["orders"]

        if strategy.get("cycle_active") is not False:
            raise RuntimeError("Cannot begin a fresh execution while a cycle is active.")
        if strategy.get("cycle_closed") is not True:
            raise RuntimeError("Previous cycle is not confirmed closed.")
        if strategy.get("execution_id") == execution_id:
            raise RuntimeError("Fresh execution ID must be new and unique.")
        if positions.get("total_quantity") != 0:
            raise RuntimeError("Registered positions remain; fresh execution denied.")

        for record in positions.get("registered_positions", {}).values():
            if int(record.get("filled_qty", 0)) != int(record.get("closed_qty", 0)):
                raise RuntimeError("Registered open quantity remains; fresh execution denied.")

        if broker_positions_flat is not True:
            raise RuntimeError("Fresh broker position-flat confirmation is required.")
        if broker_open_orders_clear is not True:
            raise RuntimeError("Fresh broker no-working-orders confirmation is required.")

        terminal = {"TRADED", "FILLED", "CANCELLED", "REJECTED", "EXPIRED"}
        for group_name in ("pending_entry_orders", "stop_loss_orders"):
            group = orders.get(group_name, {})
            if not isinstance(group, dict):
                raise RuntimeError("Invalid saved order group: " + group_name)
            for key, record in group.items():
                status = str(record.get("status", "")).upper()
                if status not in terminal:
                    raise RuntimeError(
                        "Saved order is not terminal; fresh execution denied: "
                        + group_name + "/" + str(key)
                    )

        # Persist a copy first: a failed save must not clear in-memory locks.
        candidate = json.loads(self._canonical_json(state))
        candidate_strategy = candidate["strategy"]
        candidate_strategy["execution_id"] = execution_id
        candidate_strategy["cycle_active"] = False
        candidate_strategy["cycle_closed"] = False
        candidate_strategy["fresh_execution_authorized_at"] = self._now()

        candidate["manual_cancel_locks"]["ENTRY_LIMIT"] = False
        candidate["manual_cancel_locks"]["STOP_LOSS"] = False
        candidate["manual_cancel_locks"]["status"] = "UNLOCKED"
        candidate["manual_cancel_locks"]["updated_at"] = self._now()

        # Preserve old cancellation records as an audit trail.
        candidate["reconciliation"]["positions_checked"] = False
        candidate["reconciliation"]["orders_checked"] = False
        candidate["reconciliation"]["fresh_execution_authorized_at"] = self._now()

        self.save(candidate)
        state.clear()
        state.update(candidate)
        return {
            "authorized": True,
            "execution_id": execution_id,
            "locks_reset": True,
            "historical_cancellation_records_preserved": True,
        }

    def update_reconciliation(
        self,
        state,
        positions_checked=None,
        orders_checked=None,
    ):

        reconciliation = state.setdefault(
            "reconciliation",
            {},
        )

        if positions_checked is not None:

            if not isinstance(positions_checked, bool):
                raise ValueError(
                    "positions_checked must be boolean."
                )

            reconciliation["positions_checked"] = positions_checked

        if orders_checked is not None:

            if not isinstance(orders_checked, bool):
                raise ValueError(
                    "orders_checked must be boolean."
                )

            reconciliation["orders_checked"] = orders_checked

        reconciliation["updated_at"] = self._now()

        self.save(state)

        return True

    # ======================================================
    # UNRESOLVED INTENT CHECK
    # ======================================================

    def has_unresolved_intents(self, state):

        orders = state.get("orders", {})

        if not isinstance(orders, dict):
            raise RuntimeError("Invalid order state.")

        for group_name in (
            "pending_entry_orders",
            "stop_loss_orders",
        ):

            group = orders.get(group_name, {})

            if not isinstance(group, dict):
                raise RuntimeError(
                    "Invalid order group: " + group_name
                )

            for record in group.values():

                if not isinstance(record, dict):
                    raise RuntimeError(
                        "Invalid saved order record."
                    )

                status = str(
                    record.get("status", "")
                ).upper()

                if status in self.UNRESOLVED_ORDER_STATUSES:
                    return True

        reconciliation = state.get("reconciliation", {})

        modification = reconciliation.get(
            "sl_modification_intent"
        )

        if isinstance(modification, dict):

            status = str(
                modification.get("status", "")
            ).upper()

            if status in self.UNRESOLVED_ORDER_STATUSES:
                return True

        return False
