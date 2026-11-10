
# ==========================================================
# DHAN CRUDEOILM - MAIN ENGINE
# VERSION 5.1 - CLOUDHQ SECURITY COMPATIBLE
#
# CENTRAL ENGINE ORCHESTRATOR
# STATE LOAD AND VALIDATION
# BROKER ORDER MONITORING
# FILL RECONCILIATION
# STOP LOSS PROTECTION ASSESSMENT
# LIVE LTP MONITORING
# EXECUTION TIME LIMIT
#
# NO AUTOMATIC CYCLE START
# NO ORDER PLACEMENT
# NO ORDER MODIFICATION
# NO ORDER CANCELLATION
# NO AUTOMATIC RETRY
# ==========================================================

import time
import traceback
from datetime import datetime, time as datetime_time
from zoneinfo import ZoneInfo

import config

# Dhan Cloud Global Variables are injected into the strategy entry-point.
# Keep these references in main.py (the configured entry point), then pass
# them to the shared config module. Never log credential contents.
config.DHAN_CLIENT_ID = "{{DHAN_CLIENT_ID}}"
config.DHAN_ACCESS_TOKEN = "{{DHAN_ACCESS_TOKEN}}"

from dhan_client import DhanClient
from state_store import StateStore
from execution_guard import ExecutionGuard
from fill_tracker import FillTracker
from order_monitor import OrderMonitor
from sl_controller import StopLossController
from order_manager import OrderManager
from sl_executer import StopLossExecutor


# ==========================================================
# ENGINE SETTINGS
# ==========================================================

POLL_INTERVAL_SECONDS = max(
    15,
    int(config.POLL_INTERVAL_SECONDS),
)

MAX_EXECUTION_HOURS = min(
    9.8,
    float(config.MAX_EXECUTION_HOURS),
)

MAX_EXECUTION_SECONDS = int(
    MAX_EXECUTION_HOURS * 60 * 60
)


class CrudeOilMainEngine:

    def __init__(self):

        self.started_at = None
        self.running = False
        self.last_ltp = None

        self.client = None
        self.state_store = None
        self.state = None

        self.fill_tracker = None
        self.order_monitor = None
        self.sl_controller = None
        self.execution_guard = None
        self.order_manager = None
        self.sl_executor = None

    # ======================================================
    # LOGGING
    # ======================================================

    def log(self, message):

        timestamp = datetime.now().isoformat(
            timespec="seconds"
        )

        print(
            "[" + timestamp + "] " + str(message),
            flush=True,
        )

    # ======================================================
    # INITIALIZATION
    # ======================================================

    def initialize(self):

        self.log("Initializing CRUDEOILM engine.")

        self.state_store = StateStore(
            str(config.STATE_FILE)
        )

        # Missing or invalid state must stop execution.
        self.state = self.state_store.load()

        if not isinstance(self.state, dict):
            raise RuntimeError(
                "State file did not return a valid state."
            )

        # Credential preflight diagnostic.
        # Never print or persist credential values.
        configured_client_id = str(
            config.DHAN_CLIENT_ID or ""
        ).strip()
        configured_access_token = str(
            config.DHAN_ACCESS_TOKEN or ""
        ).strip()

        client_id_status = (
            "EMPTY" if not configured_client_id
            else "UNRESOLVED_PLACEHOLDER"
            if configured_client_id.startswith("{{")
            and configured_client_id.endswith("}}")
            else "VALUE_PRESENT"
        )
        access_token_status = (
            "EMPTY" if not configured_access_token
            else "UNRESOLVED_PLACEHOLDER"
            if configured_access_token.startswith("{{")
            and configured_access_token.endswith("}}")
            else "VALUE_PRESENT"
        )

        self.log(
            "Credential preflight (values hidden): "
            "config.DHAN_CLIENT_ID=" + client_id_status
            + "; config.DHAN_ACCESS_TOKEN=" + access_token_status
        )

        self.client = DhanClient()

        # TEMPORARY SAFETY STOP: verify credential injection only.
        # Do not start monitoring, poll broker APIs, or touch order workflows.
        self.log(
            "Credential diagnostic completed; monitoring intentionally not started."
        )
        raise RuntimeError(
            "CREDENTIAL_DIAGNOSTIC_ONLY: remove this temporary stop only after "
            "credential loading has been verified."
        )

        self.fill_tracker = FillTracker(
            self.state_store,
            self.state,
        )

        self.order_monitor = OrderMonitor(
            self.state_store,
            self.state,
            self.client,
            self.fill_tracker,
        )

        self.sl_controller = StopLossController(
            self.state_store,
            self.state,
        )

        self.execution_guard = ExecutionGuard(
            config,
            self.state,
            live_engine_released=False,
            durable_state_verified=False,
        )

        self.order_manager = OrderManager(
            self.client,
            self.state_store,
            self.state,
        )

        self.sl_executor = StopLossExecutor(
            self.client,
            self.state_store,
            self.state,
        )

        self.log("State loaded and components initialized.")

        self.log(
            "Live trading remains disabled."
        )

    # ======================================================
    # ACTIVE CONTRACT
    # ======================================================

    def _validate_active_contract(self):

        active = self.state.get(
            "active_contract",
            {},
        )

        if not isinstance(active, dict):
            raise RuntimeError(
                "Active contract configuration is invalid."
            )

        expected_security_id = str(
            config.SECURITY_ID
        )

        expected_segment = str(
            config.EXCHANGE_SEGMENT
        )

        expected_symbol = str(
            config.ACTIVE_SYMBOL
        )

        expected_expiry = str(config.ACTIVE_EXPIRY)

        if str(active.get("expiry")) != expected_expiry:
            raise RuntimeError(
                "State contract expiry does not match config."
            )

        if str(active.get("security_id")) != expected_security_id:
            raise RuntimeError(
                "State security ID does not match config."
            )

        if str(active.get("exchange_segment")) != expected_segment:
            raise RuntimeError(
                "State exchange segment does not match config."
            )

        if str(active.get("symbol")) != expected_symbol:
            raise RuntimeError(
                "State active symbol does not match config."
            )

        return True

    # ======================================================
    # NEW-ENTRY RISK WINDOW
    # ======================================================

    def _validate_new_entry_window(self):
        """
        Prevent fresh entries too close to configured futures expiry
        and after the configured India-time entry cut-off. This does
        not perform an automatic square-off or contract rollover.
        """
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        expiry = datetime.strptime(
            str(config.ACTIVE_EXPIRY),
            "%Y-%m-%d",
        ).date()
        days_to_expiry = (expiry - now.date()).days
        rollover_days = int(config.EXPIRY_ROLLOVER_DAYS)
        if days_to_expiry <= rollover_days:
            raise RuntimeError(
                "New entry blocked: contract is within configured expiry-rollover window."
            )

        square_off = datetime.strptime(
            str(config.SQUARE_OFF_TIME),
            "%H:%M",
        ).time()
        if now.time() >= square_off:
            raise RuntimeError(
                "New entry blocked after configured square-off time. "
                "Existing broker SL protection remains responsible; "
                "automatic square-off is not implemented."
            )
        return True

    # ======================================================
    # MARKET DATA
    # ======================================================

    def read_ltp(self):

        self._validate_active_contract()

        active = self.state["active_contract"]

        ltp = self.client.get_ltp(
            active["exchange_segment"],
            active["security_id"],
        )

        self.last_ltp = float(ltp)

        prices = self.state.setdefault(
            "prices",
            {},
        )

        prices["last_ltp"] = self.last_ltp
        prices["last_ltp_timestamp"] = datetime.now().isoformat()

        self.log(
            "CRUDEOILM LTP: " + str(self.last_ltp)
        )

        return self.last_ltp

    # ======================================================
    # ORDER MONITOR
    # ======================================================

    def reconcile_orders(self):

        result = self.order_monitor.poll_once()

        if result is False:
            raise RuntimeError(
                "Order reconciliation failed."
            )

        self.log(
            "Broker order reconciliation completed."
        )

        return result

    # ======================================================
    # COMMON SL PROTECTION ORCHESTRATION
    # ======================================================

    def ensure_stop_loss_protection(self):
        """
        Reconcile each product bucket against the registered SL order.
        Missing SLs are submitted only through OrderManager's write-ahead
        and release gates. Existing SLs are modified in place only through
        StopLossExecutor's strict release gates. Never cancel/replace.
        """
        if not self.order_manager or not self.sl_executor:
            raise RuntimeError("Order and SL execution components are not initialized.")

        positions = self.state.get("positions", {})
        quantities = {
            "MARGIN": int(positions.get("margin_quantity", 0) or 0),
            "INTRADAY": int(positions.get("intraday_quantity", 0) or 0),
        }
        total = quantities["MARGIN"] + quantities["INTRADAY"]

        if total == 0:
            return {"status": "NO_OPEN_POSITION", "actions": []}

        trigger = self.state.get("prices", {}).get("common_stop_loss")
        if trigger is None:
            raise RuntimeError("Open exposure has no persisted common SL trigger.")
        trigger = float(trigger)
        if trigger <= 0:
            raise RuntimeError("Persisted common SL trigger is invalid.")

        broker_orders = self.order_monitor._extract_orders(
            self.client.get_orders()
        )
        active_contract_orders = [
            order for order in broker_orders
            if self.order_monitor._is_active_contract_order(order)
        ]

        registered_group = self.state.get("orders", {}).get("stop_loss_orders", {})
        actions = []
        sequence = int(
            self.state.get("strategy", {}).get("last_entry_sequence")
            or self.state.get("strategy", {}).get("entry_count")
            or 1
        )

        for product_type, open_quantity in quantities.items():
            if open_quantity == 0:
                continue

            registered = [
                (key, record)
                for key, record in registered_group.items()
                if str(record.get("product_type", "")).upper() == product_type
                and str(record.get("status", "")).upper()
                    in self.order_manager.ACTIVE_STATUSES
            ]

            if len(registered) > 1:
                raise RuntimeError(
                    "Multiple active registered SL intents exist for " + product_type
                )

            if not registered:
                # The order manager writes the intent to state before
                # any broker request. All live and durable-state gates
                # remain authoritative inside OrderManager and DhanClient.
                result = self.order_manager.submit_stop_loss(
                    sequence=sequence,
                    quantity=open_quantity,
                    trigger_price=trigger,
                    product_type=product_type,
                )
                actions.append({
                    "product_type": product_type,
                    "action": "SL_SUBMISSION_RECORDED",
                    "result": result,
                })
                continue

            key, saved = registered[0]
            correlation_id = str(
                saved.get("correlationId")
                or saved.get("correlation_id")
                or ""
            )
            if not correlation_id:
                raise RuntimeError("Registered SL has no correlation ID: " + str(key))

            matches = [
                order for order in active_contract_orders
                if str(
                    order.get("correlationId")
                    or order.get("correlation_id")
                    or ""
                ) == correlation_id
            ]
            if len(matches) != 1:
                raise RuntimeError(
                    "Registered active SL must match exactly one broker order for "
                    + product_type
                )

            broker_order = matches[0]
            broker_quantity = int(broker_order.get("quantity", 0))
            broker_filled = int(
                broker_order.get("filledQty")
                if broker_order.get("filledQty") is not None
                else broker_order.get("filledQuantity", 0)
            )
            broker_remaining = broker_quantity - broker_filled
            broker_trigger = float(broker_order.get("triggerPrice", 0) or 0)

            if broker_remaining == open_quantity and broker_trigger == trigger:
                actions.append({
                    "product_type": product_type,
                    "action": "EXISTING_SL_ALREADY_MATCHES",
                    "order_id": str(broker_order.get("orderId") or ""),
                })
                continue

            # A trigger may only tighten. Equal trigger is permitted by
            # the executor only when quantity must be increased after a
            # new partial/complete entry fill; the executor still blocks
            # every broker modification until its hard release is enabled.
            desired = {
                "required": True,
                "confirmed": False,
                "quantity": open_quantity,
                "trigger_price": trigger,
            }
            result = self.sl_executor.modify_existing_sl(
                broker_order,
                desired,
            )
            actions.append({
                "product_type": product_type,
                "action": "SL_MODIFICATION_RECORDED",
                "result": result,
            })

        return {
            "status": "PROTECTION_ACTIONS_RECONCILED",
            "actions": actions,
            "registered_open_quantity": total,
        }

    # ======================================================
    # NEXT GRID LIMIT ORCHESTRATION
    # ======================================================

    def submit_next_grid_entry_if_ready(self):
        """
        Submit the next resting LIMIT only after the preceding entry is
        completely TRADED and all registered open quantity has confirmed
        common-SL protection. Existing/uncertain intents are never retried.
        """
        strategy = self.state.get("strategy", {})
        if strategy.get("cycle_active") is not True or strategy.get("cycle_closed") is not False:
            return {"status": "CYCLE_NOT_ACTIVE"}

        if self.state_store.is_locked(self.state, "ENTRY_LIMIT"):
            raise RuntimeError("Next grid entry blocked by manual-cancellation lock.")

        sequence = strategy.get("next_entry_sequence")
        if sequence is None:
            return {"status": "MAX_ENTRIES_OR_NO_NEXT_ENTRY"}
        try:
            sequence = int(sequence)
        except (TypeError, ValueError):
            raise RuntimeError("Saved next entry sequence is invalid.")
        if sequence <= 1:
            return {"status": "FIRST_ENTRY_NOT_YET_COMPLETED"}

        entry_group = self.state.get("orders", {}).get("pending_entry_orders", {})
        if not isinstance(entry_group, dict):
            raise RuntimeError("Saved entry-order group is invalid.")

        same_sequence = [
            record for record in entry_group.values()
            if isinstance(record, dict)
            and int(record.get("sequence", 0) or 0) == sequence
        ]
        if same_sequence:
            # Any prior intent for this sequence, including uncertain or
            # terminal, is a hard no-resubmit condition.
            return {
                "status": "ENTRY_INTENT_ALREADY_EXISTS",
                "sequence": sequence,
            }

        previous = [
            record for record in entry_group.values()
            if isinstance(record, dict)
            and int(record.get("sequence", 0) or 0) == sequence - 1
        ]
        if len(previous) != 1:
            raise RuntimeError("Exactly one preceding entry record is required.")
        previous_record = previous[0]
        if (
            str(previous_record.get("status", "")).upper() != "TRADED"
            or previous_record.get("entry_complete") is not True
        ):
            return {"status": "PREVIOUS_ENTRY_NOT_FULLY_TRADED"}

        for record in entry_group.values():
            if not isinstance(record, dict):
                raise RuntimeError("Invalid saved entry order record.")
            if str(record.get("status", "")).upper() in (
                "PENDING", "TRANSIT", "PART_TRADED", "OPEN"
            ):
                raise RuntimeError("Another entry order is still working; overlap is prohibited.")

        positions = self.state.get("positions", {})
        total_open = int(positions.get("total_quantity", 0) or 0)
        protected = int(positions.get("common_stop_loss_quantity", 0) or 0)
        if total_open <= 0 or protected != total_open:
            return {"status": "WAITING_FOR_CONFIRMED_SL_PROTECTION"}

        try:
            self._validate_new_entry_window()
        except RuntimeError as error:
            self.log("Next grid entry held by risk window: " + str(error))
            return {"status": "NEW_ENTRY_WINDOW_CLOSED", "reason": str(error)}

        next_price = self.state.get("prices", {}).get("next_grid")
        if next_price is None:
            return {"status": "NO_NEXT_GRID_PRICE"}

        result = self.order_manager.submit_entry(
            sequence=sequence,
            price=float(next_price),
        )
        self.log(
            "Next grid LIMIT submitted and recorded: sequence="
            + str(sequence)
            + " order_id="
            + str(result.get("order_id"))
        )
        return {
            "status": "NEXT_GRID_LIMIT_SUBMITTED",
            "sequence": sequence,
            "price": float(next_price),
            "order": result,
        }

    # ======================================================
    # STOP LOSS ASSESSMENT
    # ======================================================

    def assess_stop_loss(self):

        # Use the controller's explicit public method.
        result = self.sl_controller.build_plan(
            self.client.get_orders()
        )

        if not isinstance(result, dict):
            raise RuntimeError(
                "SL controller returned an invalid assessment."
            )

        status = str(
            result.get("status", "")
        ).upper()

        if status not in (
            "PROTECTION_CONFIRMED",
            "NO_OPEN_POSITION",
        ):
            raise RuntimeError(
                "SL protection is not confirmed: "
                + str(result)
            )

        self.log(
            "SL assessment: " + status
        )

        return result

    # ======================================================
    # BROKER POSITION RECONCILIATION
    # ======================================================

    def reconcile_positions(self, response):
        """Compare broker net positions with this algo's registered cycle only."""
        if isinstance(response, str):
            import json
            try:
                response = json.loads(response)
            except Exception:
                raise RuntimeError("Broker positions response is invalid JSON.")

        if isinstance(response, dict):
            status = response.get("status")
            if status is not None and str(status).lower() not in (
                "success", "true", "200", "ok"
            ):
                raise RuntimeError("Broker positions API reported failure.")
            data = response.get("data")
            if data is None:
                data = response.get("positions")
            if isinstance(data, dict):
                data = data.get("positions")
            response = data

        if not isinstance(response, list):
            raise RuntimeError("Broker positions response is not a supported list.")

        active = self.state["active_contract"]
        broker_qty = {
            "MARGIN": {"LONG": 0, "SHORT": 0},
            "INTRADAY": {"LONG": 0, "SHORT": 0},
        }

        for item in response:
            if not isinstance(item, dict):
                raise RuntimeError("Broker returned an invalid position record.")
            security_id = item.get("securityId") or item.get("security_id")
            segment = item.get("exchangeSegment") or item.get("exchange_segment")
            if str(security_id) != str(active["security_id"]) or str(segment) != str(active["exchange_segment"]):
                continue

            product = str(item.get("productType") or item.get("product_type") or "").upper()
            if product not in broker_qty:
                raise RuntimeError("Unknown product type in active-contract broker position.")

            raw_qty = item.get("netQty")
            if raw_qty is None:
                raw_qty = item.get("netQuantity")
            if isinstance(raw_qty, bool) or raw_qty is None:
                raise RuntimeError("Broker position quantity is missing or invalid.")
            try:
                numeric_qty = float(str(raw_qty).strip())
            except (TypeError, ValueError):
                raise RuntimeError("Broker position quantity is missing or invalid.")
            if not numeric_qty.is_integer():
                raise RuntimeError("Broker position quantity is not an integer.")
            qty = int(numeric_qty)
            if qty == 0:
                continue

            side = str(item.get("positionType") or "").upper()
            if side not in ("LONG", "SHORT"):
                if qty > 0:
                    side = "LONG"
                else:
                    side = "SHORT"
            broker_qty[product][side] += abs(qty)

        local_qty = {
            "MARGIN": {"LONG": 0, "SHORT": 0},
            "INTRADAY": {"LONG": 0, "SHORT": 0},
        }
        direction = str(self.state["strategy"].get("direction", "")).upper()
        if direction not in ("BUY", "SELL"):
            raise RuntimeError("Saved cycle direction is invalid.")
        side = "LONG" if direction == "BUY" else "SHORT"

        registered = self.state["positions"].get("registered_positions", {})
        if not isinstance(registered, dict):
            raise RuntimeError("Registered algo positions are invalid.")

        for position_id, record in registered.items():
            if not isinstance(record, dict):
                raise RuntimeError("Invalid registered position: " + str(position_id))
            product = str(record.get("product_type", "")).upper()
            if product not in local_qty:
                raise RuntimeError("Unsupported registered product type.")
            try:
                filled = int(record.get("filled_qty"))
                closed = int(record.get("closed_qty", 0))
            except (TypeError, ValueError):
                raise RuntimeError("Invalid registered position quantities.")
            if filled < 0 or closed < 0 or closed > filled:
                raise RuntimeError("Registered position quantities are inconsistent.")
            local_qty[product][side] += filled - closed

        if broker_qty != local_qty:
            raise RuntimeError(
                "Broker/algo position mismatch. Broker=" + str(broker_qty)
                + " Algo=" + str(local_qty)
                + ". Existing positions will not be enrolled or modified."
            )

        self.state_store.update_reconciliation(
            self.state,
            positions_checked=True,
        )
        self.log("Broker positions exactly match registered algo quantities.")
        return True

    # ======================================================
    # EXPLICIT FRESH EXECUTION AUTHORIZATION (NO ORDER WRITES)
    # ======================================================

    def authorize_fresh_execution(self, execution_id):
        """
        Deliberate operator-invoked reset only. Verifies broker positions
        and working orders for the active contract before releasing the
        previous execution's cancellation locks. This method never places,
        modifies, or cancels an order and is not called by run()/restart.
        """
        if not self.state_store or not self.state or not self.client:
            raise RuntimeError("Engine must be initialized before fresh authorization.")

        execution_id = str(execution_id or "").strip()
        if not execution_id:
            raise ValueError("A unique execution ID must be supplied explicitly.")

        self._validate_active_contract()

        # Position check: any non-flat broker position must match the
        # previous registered cycle; begin_fresh_execution then requires
        # that registered cycle itself is flat.
        broker_positions = self.client.get_positions()
        if broker_positions is None:
            raise RuntimeError("Broker positions response is missing.")
        self.reconcile_positions(broker_positions)

        # Check every broker order for this exact contract, including
        # orders not registered by this algo. Unknown working orders block.
        broker_orders = self.order_monitor._extract_orders(
            self.client.get_orders()
        )
        active_orders = [
            order for order in broker_orders
            if self.order_monitor._is_active_contract_order(order)
        ]
        working_statuses = self.order_monitor.ACTIVE_STATUSES
        working = [
            order for order in active_orders
            if self.order_monitor._normalise_status(order) in working_statuses
        ]
        if working:
            raise RuntimeError(
                "Fresh execution denied: active-contract broker working orders exist."
            )

        self.state_store.update_reconciliation(
            self.state,
            orders_checked=True,
        )

        # Only registered order history in terminal states can pass the
        # state-store gate. Broker reconciliation is checked again there.
        result = self.state_store.begin_fresh_execution(
            state=self.state,
            execution_id=execution_id,
            broker_positions_flat=True,
            broker_open_orders_clear=True,
        )

        self.log(
            "Fresh execution authorized (no order placed): "
            + execution_id
        )
        return result

    # ======================================================
    # EXPLICIT FIRST-ENTRY START (NO RESTART AUTO-START)
    # ======================================================

    def start_authorized_cycle(self):
        """
        Start only after authorize_fresh_execution() has been explicitly
        completed for this execution ID. Rechecks flat positions and
        absence of working active-contract orders immediately before the
        first LIMIT. All release switches and durable-state verification
        must be enabled deliberately; defaults remain OFF.
        """
        if not self.state or not self.client or not self.order_manager:
            raise RuntimeError("Engine must be initialized before starting a cycle.")

        strategy = self.state.get("strategy", {})
        execution_id = strategy.get("execution_id")
        if not isinstance(execution_id, str) or not execution_id.strip():
            raise RuntimeError("No explicitly authorized fresh execution exists.")
        if not strategy.get("fresh_execution_authorized_at"):
            raise RuntimeError("Fresh execution authorization timestamp is missing.")
        if strategy.get("cycle_active") is not False or strategy.get("cycle_closed") is not False:
            raise RuntimeError("State is not waiting for an authorized first-cycle start.")

        if self.state.get("manual_cancel_locks", {}).get("ENTRY_LIMIT") is True:
            raise RuntimeError("Entry start blocked by manual-cancellation lock.")
        if self.state.get("manual_cancel_locks", {}).get("STOP_LOSS") is True:
            raise RuntimeError("Entry start blocked by stop-loss cancellation lock.")

        release_checks = {
            "TRADING_MODE": str(config.TRADING_MODE).upper() == "LIVE",
            "LIVE_TRADING_ENABLED": config.LIVE_TRADING_ENABLED is True,
            "ORDER_PLACEMENT_ENABLED": config.ORDER_PLACEMENT_ENABLED is True,
            "LIVE_ENGINE_RELEASED": config.LIVE_ENGINE_RELEASED is True,
            "DURABLE_STATE_VERIFIED": config.DURABLE_STATE_VERIFIED is True,
        }
        failed = [name for name, passed in release_checks.items() if not passed]
        if failed:
            raise RuntimeError(
                "First entry blocked; release requirements are OFF/unverified: "
                + ", ".join(failed)
            )

        self._validate_active_contract()
        self._validate_new_entry_window()

        broker_positions = self.client.get_positions()
        if broker_positions is None:
            raise RuntimeError("Broker positions response is missing.")
        self.reconcile_positions(broker_positions)

        broker_orders = self.order_monitor._extract_orders(self.client.get_orders())
        active_orders = [
            order for order in broker_orders
            if self.order_monitor._is_active_contract_order(order)
        ]
        working = [
            order for order in active_orders
            if self.order_monitor._normalise_status(order)
            in self.order_monitor.ACTIVE_STATUSES
        ]
        if working:
            raise RuntimeError(
                "First entry blocked: active-contract working broker orders exist."
            )

        if self.state["positions"].get("total_quantity") != 0:
            raise RuntimeError("First entry requires zero registered open quantity.")
        if self.state_store.has_unresolved_intents(self.state):
            raise RuntimeError("First entry blocked by an unresolved saved order intent.")

        # Populate the persisted strategy parameters BEFORE calculating
        # the first cycle. OrderManager.calculate_first_cycle() reads
        # direction/grid/SL distance from this state; calculating first
        # against a fresh state would otherwise fail on blank defaults.
        strategy["direction"] = str(config.DIRECTION).upper()
        strategy["grid_points"] = int(config.GRID_POINTS)
        strategy["stop_loss_points"] = int(config.STOP_LOSS_POINTS)
        strategy["maximum_entries"] = int(config.MAX_ENTRIES)
        strategy["quantity_per_entry"] = int(config.QUANTITY_PER_ENTRY)
        strategy["lot_size"] = int(config.LOT_SIZE)
        strategy["lots_per_entry"] = int(config.LOTS_PER_ENTRY)

        ltp = self.read_ltp()
        plan = self.order_manager.calculate_first_cycle(ltp)

        # Persist cycle state before the write-ahead order intent. If the
        # broker outcome is uncertain, a restart must not submit a duplicate.
        strategy["cycle_active"] = True
        strategy["cycle_closed"] = False
        strategy["initial_entry"] = plan["entry_price"]
        strategy["last_entry"] = None
        strategy["next_grid"] = plan["next_grid"]
        strategy["common_stop_loss"] = plan["stop_loss"]
        strategy["entry_count"] = 0
        strategy["next_entry_sequence"] = 1

        prices = self.state["prices"]
        prices["initial_entry"] = plan["entry_price"]
        prices["last_entry"] = None
        prices["next_grid"] = plan["next_grid"]
        prices["common_stop_loss"] = plan["stop_loss"]

        self.state["reconciliation"]["positions_checked"] = True
        self.state["reconciliation"]["orders_checked"] = True
        self.state_store.save(self.state)

        result = self.order_manager.submit_entry(
            sequence=1,
            price=plan["entry_price"],
        )

        self.log("First LIMIT entry submitted and recorded: " + str(result.get("order_id")))
        return {
            "started": True,
            "execution_id": execution_id,
            "entry": plan,
            "order": result,
        }

    # ======================================================
    # RECONCILIATION CHECK
    # ======================================================

    def check_reconciliation(self):

        reconciliation = self.state.get(
            "reconciliation",
            {},
        )

        if reconciliation.get("positions_checked") is not True:
            raise RuntimeError(
                "Broker positions have not been reconciled."
            )

        if reconciliation.get("orders_checked") is not True:
            raise RuntimeError(
                "Broker orders have not been reconciled."
            )

        if self.state_store.has_unresolved_intents(
            self.state
        ):
            raise RuntimeError(
                "Unresolved broker order intent exists."
            )

        return True

    # ======================================================
    # CLOSED-CYCLE PENDING ENTRY SAFETY
    # ======================================================

    def assert_no_entry_after_cycle_close(self):
        strategy = self.state.get("strategy", {})
        if strategy.get("cycle_closed") is not True:
            return True

        group = self.state.get("orders", {}).get("pending_entry_orders", {})
        working = []
        for correlation_id, record in group.items():
            if not isinstance(record, dict):
                raise RuntimeError("Invalid saved entry order record.")
            status = str(record.get("status", "")).upper()
            if status in ("PENDING", "TRANSIT", "PART_TRADED", "OPEN"):
                working.append({
                    "correlation_id": str(correlation_id),
                    "order_id": str(record.get("order_id") or ""),
                    "status": status,
                })

        if working:
            raise RuntimeError(
                "Cycle is closed but a resting grid LIMIT remains at Dhan: "
                + str(working)
                + ". Automatic cancellation is disabled. Manually cancel "
                "the broker order before authorizing another execution."
            )
        return True

    # ======================================================
    # ONE GUARDED MONITORING / ORCHESTRATION CYCLE
    # ======================================================

    def run_once(self):

        self.log("Starting read-only monitoring cycle.")

        self._validate_active_contract()

        self.reconcile_orders()

        # A filled SL closes the registered cycle. If a later grid LIMIT
        # is still resting, stop and require operator cancellation rather
        # than leave a post-stop entry armed.
        self.assert_no_entry_after_cycle_close()

        # Read positions only.
        # Existing positions are never auto-enrolled.
        positions = self.client.get_positions()

        if positions is None:
            raise RuntimeError(
                "Broker positions response is missing."
            )

        # Response receipt alone is not reconciliation.
        self.reconcile_positions(positions)

        self.ensure_stop_loss_protection()

        self.assess_stop_loss()

        # Only after the broker order book confirms complete SL coverage
        # may the next resting grid LIMIT be submitted.
        self.submit_next_grid_entry_if_ready()

        self.read_ltp()

        self.check_reconciliation()

        self.log(
            "Read-only monitoring cycle completed."
        )

        return True

    # ======================================================
    # MAIN LOOP
    # ======================================================

    def run(self):

        self.initialize()

        self.started_at = time.monotonic()
        self.running = True

        self.log(
            "Monitoring started. No trading writes are enabled."
        )

        try:

            while self.running:

                elapsed = (
                    time.monotonic()
                    - self.started_at
                )

                if elapsed >= MAX_EXECUTION_SECONDS:

                    self.log(
                        "Maximum execution duration reached."
                    )

                    break

                try:

                    self.run_once()

                except Exception as error:

                    self.log(
                        "ENGINE SAFETY STOP: " + str(error)
                    )

                    self.log(
                        traceback.format_exc()
                    )

                    # No automatic restart or retry.
                    break

                time.sleep(
                    POLL_INTERVAL_SECONDS
                )

        finally:

            self.running = False

            self.log(
                "Engine stopped. No automatic restart."
            )


# ==========================================================
# ENTRY POINT
# ==========================================================

def main():

    engine = CrudeOilMainEngine()

    engine.run()


if __name__ == "__main__":

    main()
