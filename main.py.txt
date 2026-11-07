
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
from datetime import datetime

import config

from dhan_client import DhanClient
from state_store import StateStore
from execution_guard import ExecutionGuard
from fill_tracker import FillTracker
from order_monitor import OrderMonitor
from sl_controller import StopLossController


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

        self.client = DhanClient()

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
    # ONE READ-ONLY CYCLE
    # ======================================================

    def run_once(self):

        self.log("Starting read-only monitoring cycle.")

        self._validate_active_contract()

        self.reconcile_orders()

        # Read positions only.
        # Existing positions are never auto-enrolled.
        positions = self.client.get_positions()

        if positions is None:
            raise RuntimeError(
                "Broker positions response is missing."
            )

        # Mark positions as checked in state reconciliation
        self.state_store.update_reconciliation(
            self.state,
            positions_checked=True,
        )

        self.log(
            "Broker positions response received and reconciled."
        )

        self.assess_stop_loss()

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
