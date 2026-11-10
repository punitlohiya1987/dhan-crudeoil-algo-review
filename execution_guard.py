
# ==========================================================
# DHAN EXECUTION GUARD
# VERSION 6.0 - STATE STORE V5 COMPATIBLE
#
# FAIL-CLOSED EXECUTION PERMISSION
# CONTRACT VALIDATION
# REGISTERED POSITION VALIDATION
# COMMON SL QUANTITY VALIDATION
# MANUAL CANCELLATION LOCK PROTECTION
# RECONCILIATION REQUIRED
# UNRESOLVED INTENT PROTECTION
#
# NO BROKER API CALLS
# NO ORDER PLACEMENT
# NO ORDER MODIFICATION
# NO ORDER CANCELLATION
# ==========================================================


class ExecutionGuard:

    REQUIRED_STATE_VERSION = 5

    LOCK_ROLES = (
        "ENTRY_LIMIT",
        "STOP_LOSS",
    )

    def __init__(
        self,
        config,
        state,
        live_engine_released=False,
        durable_state_verified=False,
    ):

        self.config = config or {}
        self.state = state or {}

        self.live_engine_released = bool(
            live_engine_released
        )

        self.durable_state_verified = bool(
            durable_state_verified
        )

    # ======================================================
    # RESULT
    # ======================================================

    def _result(
        self,
        allowed,
        status,
        reason,
    ):

        return {
            "allowed": bool(allowed),
            "status": str(status),
            "reason": str(reason),
        }

    # ======================================================
    # BASIC VALIDATION
    # ======================================================

    def _validate_state_version(self):

        if not isinstance(self.state, dict):
            return False, "State is not a dictionary."

        if (
            self.state.get("state_version")
            != self.REQUIRED_STATE_VERSION
        ):
            return False, "State version is not 5."

        return True, "State version accepted."

    def _validate_contract(self):

        active = self.state.get(
            "active_contract",
            {},
        )

        if not isinstance(active, dict):
            return False, "Active contract section is invalid."

        expected = {
            "symbol": self.config.get("ACTIVE_SYMBOL"),
            "security_id": self.config.get("ACTIVE_SECURITY_ID"),
            "expiry": self.config.get("ACTIVE_EXPIRY"),
            "exchange_segment": self.config.get("EXCHANGE_SEGMENT"),
        }

        for field, configured_value in expected.items():

            if configured_value is None:
                return False, (
                    "Missing configured contract field: "
                    + field
                )

            saved_value = active.get(field)

            if str(saved_value) != str(configured_value):
                return False, (
                    "Active contract mismatch: "
                    + field
                )

        return True, "Active contract matches configuration."

    # ======================================================
    # STRATEGY VALIDATION
    # ======================================================

    def _validate_strategy(self):

        strategy = self.state.get(
            "strategy",
            {},
        )

        if not isinstance(strategy, dict):
            return False, "Strategy section is invalid."

        if strategy.get("cycle_active") is not True:
            return False, "No active algo execution cycle."

        if strategy.get("cycle_closed") is not False:
            return False, "Algo execution cycle is closed."

        execution_id = strategy.get("execution_id")

        if (
            not isinstance(execution_id, str)
            or not execution_id.strip()
        ):
            return False, "Execution ID is missing."

        direction = str(
            strategy.get("direction", "")
        ).upper()

        configured_direction = str(
            self.config.get("DIRECTION", "")
        ).upper()

        if direction not in ("BUY", "SELL"):
            return False, "Invalid saved strategy direction."

        if direction != configured_direction:
            return False, "Strategy direction mismatch."

        return True, "Strategy cycle is valid."

    # ======================================================
    # POSITION VALIDATION
    # ======================================================

    def _validate_positions(self):

        positions = self.state.get(
            "positions",
            {},
        )

        if not isinstance(positions, dict):
            return False, "Positions section is invalid."

        registered = positions.get(
            "registered_positions",
            {},
        )

        if not isinstance(registered, dict):
            return False, "Registered positions are invalid."

        total = 0
        margin = 0
        intraday = 0

        for position_id, record in registered.items():

            if not isinstance(record, dict):
                return False, (
                    "Invalid registered position: "
                    + str(position_id)
                )

            try:

                filled = int(record.get("filled_qty"))
                closed = int(record.get("closed_qty", 0))

            except (TypeError, ValueError):

                return False, (
                    "Invalid position quantity: "
                    + str(position_id)
                )

            if filled < 0 or closed < 0 or closed > filled:
                return False, (
                    "Invalid filled/closed quantity: "
                    + str(position_id)
                )

            if (
                isinstance(record.get("filled_qty"), bool)
                or isinstance(record.get("closed_qty", 0), bool)
            ):
                return False, (
                    "Boolean quantity is invalid: "
                    + str(position_id)
                )

            product_type = str(
                record.get("product_type", "")
            ).upper()

            if product_type not in ("MARGIN", "INTRADAY"):
                return False, (
                    "Unknown product type: "
                    + str(position_id)
                )

            open_quantity = filled - closed

            total += open_quantity

            if product_type == "MARGIN":
                margin += open_quantity
            else:
                intraday += open_quantity

        try:

            saved_total = int(
                positions.get("total_quantity")
            )

            saved_margin = int(
                positions.get("margin_quantity")
            )

            saved_intraday = int(
                positions.get("intraday_quantity")
            )

            saved_sl_quantity = int(
                positions.get("common_stop_loss_quantity")
            )

        except (TypeError, ValueError):

            return False, "Saved position totals are invalid."

        if total != saved_total:
            return False, "Total registered quantity mismatch."

        if margin != saved_margin:
            return False, "MARGIN quantity mismatch."

        if intraday != saved_intraday:
            return False, "INTRADAY quantity mismatch."

        if total != margin + intraday:
            return False, "Product quantity reconciliation failed."

        if saved_sl_quantity != total:
            return False, (
                "Common SL quantity does not equal "
                "registered open quantity."
            )

        return True, "Registered positions and SL quantity match."

    # ======================================================
    # MANUAL CANCELLATION LOCKS
    # ======================================================

    def _validate_manual_cancel_locks(self):

        if self.config.get(
            "MANUAL_CANCEL_PROTECTION"
        ) is not True:

            return False, "Manual cancellation protection is disabled."

        locks = self.state.get(
            "manual_cancel_locks",
            {},
        )

        if not isinstance(locks, dict):
            return False, "Manual cancellation lock state is invalid."

        for role in self.LOCK_ROLES:

            # Missing lock is treated as locked.
            if locks.get(role) is not False:

                return False, (
                    "Execution blocked by cancellation lock: "
                    + role
                )

        return True, "Manual cancellation locks are clear."

    # ======================================================
    # RECONCILIATION
    # ======================================================

    def _validate_reconciliation(self):

        if self.config.get(
            "FRESH_EXECUTION_REQUIRES_RECONCILIATION"
        ) is not True:

            return False, "Fresh execution reconciliation requirement is disabled."

        reconciliation = self.state.get(
            "reconciliation",
            {},
        )

        if not isinstance(reconciliation, dict):
            return False, "Reconciliation section is invalid."

        if reconciliation.get("positions_checked") is not True:
            return False, "Broker positions have not been reconciled."

        if reconciliation.get("orders_checked") is not True:
            return False, "Broker orders have not been reconciled."

        return True, "Broker reconciliation flags are confirmed."

    # ======================================================
    # UNRESOLVED ORDER INTENTS
    # ======================================================

    def _validate_order_intents(self):

        orders = self.state.get(
            "orders",
            {},
        )

        if not isinstance(orders, dict):
            return False, "Orders section is invalid."

        unresolved_statuses = {
            "SUBMISSION_PENDING",
            "SUBMISSION_UNCERTAIN",
            "VERIFICATION_REQUIRED",
            "MODIFICATION_PENDING",
            "MODIFICATION_UNCERTAIN",
        }

        for group_name in (
            "pending_entry_orders",
            "stop_loss_orders",
        ):

            group = orders.get(group_name, {})

            if not isinstance(group, dict):
                return False, (
                    "Invalid order group: "
                    + group_name
                )

            for order_key, record in group.items():

                if not isinstance(record, dict):
                    return False, (
                        "Invalid saved order: "
                        + str(order_key)
                    )

                status = str(
                    record.get("status", "")
                ).upper()

                if status in unresolved_statuses:

                    return False, (
                        "Unresolved order intent: "
                        + str(order_key)
                        + " / "
                        + status
                    )

        return True, "No unresolved order intents found."

    # ======================================================
    # COMPLETE VALIDATION
    # ======================================================

    def validate(self):

        checks = (
            self._validate_state_version,
            self._validate_contract,
            self._validate_strategy,
            self._validate_positions,
            self._validate_manual_cancel_locks,
            self._validate_reconciliation,
            self._validate_order_intents,
        )

        for check in checks:

            try:
                passed, reason = check()

            except Exception as error:

                return self._result(
                    False,
                    "VALIDATION_ERROR",
                    str(error),
                )

            if not passed:

                return self._result(
                    False,
                    "BLOCKED",
                    reason,
                )

        return self._result(
            True,
            "VALIDATION_PASSED",
            "All execution safety checks passed.",
        )

    # ======================================================
    # LIVE RELEASE GATES
    # ======================================================

    def require_release(self):

        result = self.validate()

        if not result["allowed"]:
            raise RuntimeError(
                "EXECUTION BLOCKED: "
                + result["reason"]
            )

        if self.config.get(
            "LIVE_TRADING_ENABLED"
        ) is not True:

            raise RuntimeError(
                "LIVE_TRADING_ENABLED is OFF."
            )

        if self.config.get(
            "ORDER_PLACEMENT_ENABLED"
        ) is not True:

            raise RuntimeError(
                "ORDER_PLACEMENT_ENABLED is OFF."
            )

        if self.config.get(
            "REQUIRE_DURABLE_STATE_FOR_LIVE"
        ) is True:

            if not self.durable_state_verified:

                raise RuntimeError(
                    "Durable state persistence is not verified."
                )

        if not self.live_engine_released:

            raise RuntimeError(
                "Live engine release has not been authorized."
            )

        return True
