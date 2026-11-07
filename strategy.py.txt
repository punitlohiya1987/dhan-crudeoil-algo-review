
# ==========================================================
# DHAN CRUDEOILM - GRID STRATEGY
# VERSION 4.1 - CLOUDHQ SECURITY COMPATIBLE
#
# BUY / SELL GRID
# FIRST ENTRY PRICE CALCULATION
# ONE LOT PER ENTRY
# GRID LEVEL GENERATION
# COMMON SL TIGHTENING
# CUMULATIVE FILL DELTA CALCULATION
# MAXIMUM ENTRY PROTECTION
#
# NO BROKER API CALLS
# NO ORDER PLACEMENT
# NO ORDER MODIFICATION
# NO AUTOMATIC RETRY
# ==========================================================

from datetime import datetime

import config


class CrudeOilGridStrategy:

    def __init__(self):

        self.direction = str(
            config.DIRECTION
        ).upper()

        self.grid_points = int(
            config.GRID_POINTS
        )

        self.stop_loss_points = int(
            config.STOP_LOSS_POINTS
        )

        self.maximum_entries = int(
            config.MAX_ENTRIES
        )

        self.quantity_per_entry = int(
            config.QUANTITY_PER_ENTRY
        )

        self.lot_size = int(
            config.LOT_SIZE
        )

        self.lots_per_entry = int(
            config.LOTS_PER_ENTRY
        )

        self.reset()
        self._validate_configuration()

    # ======================================================
    # VALIDATION
    # ======================================================

    def _validate_configuration(self):

        if self.direction not in ("BUY", "SELL"):
            raise RuntimeError(
                "Direction must be BUY or SELL."
            )

        if self.grid_points <= 0:
            raise RuntimeError(
                "Grid points must be positive."
            )

        if self.stop_loss_points <= 0:
            raise RuntimeError(
                "Stop loss points must be positive."
            )

        if self.maximum_entries <= 0:
            raise RuntimeError(
                "Maximum entries must be positive."
            )

        if self.lot_size <= 0 or self.lots_per_entry <= 0:
            raise RuntimeError(
                "Lot configuration is invalid."
            )

        expected_quantity = (
            self.lot_size * self.lots_per_entry
        )

        if self.quantity_per_entry != expected_quantity:
            raise RuntimeError(
                "Quantity per entry must equal lot size "
                "multiplied by lots per entry."
            )

    # ======================================================
    # RESET
    # ======================================================

    def reset(self):

        self.cycle_active = False
        self.cycle_closed = False

        self.initial_entry_price = None
        self.common_stop_loss = None
        self.next_grid_price = None

        self.entry_count = 0
        self.positions = {}

        self.total_quantity = 0
        self.total_margin_quantity = 0
        self.total_intraday_quantity = 0

        self.last_entry_price = None
        self.last_entry_average = None

        self.created_at = None

    # ======================================================
    # PRICE HELPERS
    # ======================================================

    def _valid_price(self, value, name):

        try:
            price = float(value)
        except (TypeError, ValueError):
            raise RuntimeError(
                "Invalid " + name
            )

        if price <= 0:
            raise RuntimeError(
                name + " must be positive."
            )

        return price

    def _round_sell_entry(self, ltp):

        return (
            int(
                (ltp + self.grid_points - 0.0000001)
                // self.grid_points
            )
            * self.grid_points
        )

    def _round_buy_entry(self, ltp):

        return (
            int(ltp // self.grid_points)
            * self.grid_points
        )

    # ======================================================
    # FIRST CYCLE CALCULATION
    # ======================================================

    def calculate_first_cycle(self, ltp):

        ltp = self._valid_price(
            ltp,
            "LTP",
        )

        if self.direction == "SELL":

            entry = self._round_sell_entry(ltp)

            stop_loss = (
                entry + self.stop_loss_points
            )

            next_grid = (
                entry - self.grid_points
            )

        else:

            entry = self._round_buy_entry(ltp)

            if entry <= 0:
                raise RuntimeError(
                    "Calculated BUY entry is invalid."
                )

            stop_loss = (
                entry - self.stop_loss_points
            )

            if stop_loss <= 0:
                raise RuntimeError(
                    "Calculated BUY stop loss is invalid."
                )

            next_grid = (
                entry + self.grid_points
            )

        return {
            "entry_price": float(entry),
            "stop_loss": float(stop_loss),
            "next_grid": float(next_grid),
            "direction": self.direction,
            "quantity": self.quantity_per_entry,
            "lots": self.lots_per_entry,
        }

    # ======================================================
    # START CYCLE
    # ======================================================

    def start_cycle(self, ltp):

        if self.cycle_active:
            raise RuntimeError(
                "A strategy cycle is already active."
            )

        if self.cycle_closed:
            raise RuntimeError(
                "Closed cycle requires an explicit fresh reset."
            )

        plan = self.calculate_first_cycle(ltp)

        self.cycle_active = True
        self.cycle_closed = False

        self.initial_entry_price = plan["entry_price"]
        self.common_stop_loss = plan["stop_loss"]
        self.next_grid_price = plan["next_grid"]

        self.entry_count = 0
        self.positions = {}

        self.total_quantity = 0
        self.total_margin_quantity = 0
        self.total_intraday_quantity = 0

        self.last_entry_price = None
        self.last_entry_average = None

        self.created_at = datetime.now().isoformat()

        return plan

    # ======================================================
    # GRID TRIGGER
    # ======================================================

    def check_grid_trigger(self, ltp):

        if not self.cycle_active or self.cycle_closed:
            return None

        if self.next_grid_price is None:
            return None

        ltp = self._valid_price(ltp, "LTP")

        if self.entry_count >= self.maximum_entries:
            return None

        # This reports a price condition only.
        # It does not submit an order.

        if self.direction == "SELL":

            if ltp >= self.next_grid_price:

                return {
                    "triggered": True,
                    "direction": "SELL",
                    "order_type": "LIMIT",
                    "limit_price": float(self.next_grid_price),
                    "sequence": self.entry_count + 1,
                    "quantity": self.quantity_per_entry,
                }

        else:

            if ltp <= self.next_grid_price:

                return {
                    "triggered": True,
                    "direction": "BUY",
                    "order_type": "LIMIT",
                    "limit_price": float(self.next_grid_price),
                    "sequence": self.entry_count + 1,
                    "quantity": self.quantity_per_entry,
                }

        return None

    # ======================================================
    # CUMULATIVE FILL DELTA
    # ======================================================

    def calculate_fill_delta(
        self,
        previous_quantity,
        previous_average,
        current_quantity,
        current_average,
    ):

        previous_quantity = int(previous_quantity)
        current_quantity = int(current_quantity)

        previous_average = float(previous_average or 0)
        current_average = float(current_average or 0)

        if previous_quantity < 0 or current_quantity < 0:
            raise RuntimeError(
                "Fill quantity cannot be negative."
            )

        if current_quantity < previous_quantity:
            raise RuntimeError(
                "Cumulative fill quantity moved backwards."
            )

        delta_quantity = (
            current_quantity - previous_quantity
        )

        if delta_quantity == 0:
            return {
                "delta_quantity": 0,
                "incremental_average": 0.0,
            }

        if current_average <= 0:
            raise RuntimeError(
                "Current cumulative average is invalid."
            )

        if previous_quantity == 0:
            incremental_average = current_average
        else:
            incremental_value = (
                current_quantity * current_average
                - previous_quantity * previous_average
            )

            incremental_average = (
                incremental_value / delta_quantity
            )

        if incremental_average <= 0:
            raise RuntimeError(
                "Calculated incremental fill average is invalid."
            )

        return {
            "delta_quantity": delta_quantity,
            "incremental_average": incremental_average,
        }

    # ======================================================
    # POSITION QUANTITY RECALCULATION
    # ======================================================

    def _recalculate_quantities(self):

        total = 0
        margin = 0
        intraday = 0

        for position in self.positions.values():

            filled = int(position.get("filled_qty", 0))
            closed = int(position.get("closed_qty", 0))

            if filled < 0 or closed < 0 or closed > filled:
                raise RuntimeError(
                    "Position quantity integrity failure."
                )

            remaining = filled - closed

            product = str(
                position.get("product_type", "")
            ).upper()

            if product not in ("MARGIN", "INTRADAY"):
                raise RuntimeError(
                    "Unsupported position product type."
                )

            total += remaining

            if product == "MARGIN":
                margin += remaining
            else:
                intraday += remaining

        self.total_quantity = total
        self.total_margin_quantity = margin
        self.total_intraday_quantity = intraday

        return {
            "total_quantity": total,
            "margin_quantity": margin,
            "intraday_quantity": intraday,
        }

    # ======================================================
    # REGISTER ENTRY FILL
    # ======================================================

    def register_entry_fill(
        self,
        order_id,
        cumulative_filled_qty,
        cumulative_average_price,
        product_type="INTRADAY",
    ):

        if not self.cycle_active or self.cycle_closed:
            raise RuntimeError(
                "No active strategy cycle."
            )

        if not order_id:
            raise RuntimeError(
                "Entry order ID is required."
            )

        order_id = str(order_id)

        cumulative_filled_qty = int(
            cumulative_filled_qty
        )

        cumulative_average_price = self._valid_price(
            cumulative_average_price,
            "cumulative average price",
        )

        product_type = str(product_type).upper()

        if product_type not in ("MARGIN", "INTRADAY"):
            raise RuntimeError(
                "Unsupported product type."
            )

        if cumulative_filled_qty <= 0:
            raise RuntimeError(
                "Cumulative fill quantity must be positive."
            )

        # Validate total cumulative quantity, not only
        # the latest incremental fill.
        if cumulative_filled_qty > self.quantity_per_entry:
            raise RuntimeError(
                "Cumulative entry fill exceeds one-entry quantity."
            )

        position = self.positions.get(order_id)

        if position is None:

            position = {
                "filled_qty": 0,
                "closed_qty": 0,
                "average_price": 0.0,
                "product_type": product_type,
            }

            self.positions[order_id] = position

        if position["product_type"] != product_type:
            raise RuntimeError(
                "Entry order product type changed."
            )

        previous_quantity = int(position["filled_qty"])
        previous_average = float(position["average_price"])

        delta = self.calculate_fill_delta(
            previous_quantity,
            previous_average,
            cumulative_filled_qty,
            cumulative_average_price,
        )

        delta_quantity = delta["delta_quantity"]

        if delta_quantity == 0:
            return {
                "new_fill": False,
                "delta_quantity": 0,
                "positions": self._recalculate_quantities(),
            }

        if previous_quantity == 0:

            if self.entry_count >= self.maximum_entries:
                del self.positions[order_id]

                raise RuntimeError(
                    "Maximum entry count exceeded."
                )

            self.entry_count += 1

        position["filled_qty"] = cumulative_filled_qty
        position["average_price"] = cumulative_average_price

        position["last_fill_price"] = delta[
            "incremental_average"
        ]

        self.last_entry_price = delta[
            "incremental_average"
        ]

        self.last_entry_average = cumulative_average_price

        self._recalculate_quantities()

        self._tighten_common_sl(
            delta["incremental_average"]
        )

        return {
            "new_fill": True,
            "delta_quantity": delta_quantity,
            "incremental_average": delta["incremental_average"],
            "common_stop_loss": self.common_stop_loss,
            "positions": self._recalculate_quantities(),
        }

    # ======================================================
    # COMMON SL TIGHTENING
    # ======================================================

    def _tighten_common_sl(self, latest_entry_average):

        latest_entry_average = self._valid_price(
            latest_entry_average,
            "latest entry average",
        )

        if self.direction == "SELL":

            candidate = (
                latest_entry_average + self.stop_loss_points
            )

            if self.common_stop_loss is None:
                self.common_stop_loss = candidate
            else:
                self.common_stop_loss = min(
                    self.common_stop_loss,
                    candidate,
                )

        else:

            candidate = (
                latest_entry_average - self.stop_loss_points
            )

            if candidate <= 0:
                raise RuntimeError(
                    "Calculated BUY common SL is invalid."
                )

            if self.common_stop_loss is None:
                self.common_stop_loss = candidate
            else:
                self.common_stop_loss = max(
                    self.common_stop_loss,
                    candidate,
                )

        return self.common_stop_loss

    # ======================================================
    # REGISTER EXIT FILL
    # ======================================================

    def register_exit_fill(
        self,
        cumulative_exit_qty,
        previous_exit_qty=0,
    ):

        if not self.cycle_active:
            raise RuntimeError(
                "No active cycle."
            )

        cumulative_exit_qty = int(cumulative_exit_qty)
        previous_exit_qty = int(previous_exit_qty)

        if cumulative_exit_qty < previous_exit_qty:
            raise RuntimeError(
                "Exit cumulative quantity moved backwards."
            )

        delta = cumulative_exit_qty - previous_exit_qty

        if delta == 0:
            return {
                "closed_quantity": 0,
                "cycle_closed": self.cycle_closed,
            }

        # Pre-check before changing any position.
        total_open_quantity = 0

        for position in self.positions.values():

            open_quantity = (
                int(position["filled_qty"])
                - int(position["closed_qty"])
            )

            if open_quantity < 0:
                raise RuntimeError(
                    "Position quantity integrity failure."
                )

            total_open_quantity += open_quantity

        if delta > total_open_quantity:
            raise RuntimeError(
                "Exit fill exceeds registered open quantity."
            )

        remaining_exit = delta

        for position_id in list(self.positions.keys()):

            if remaining_exit <= 0:
                break

            position = self.positions[position_id]

            open_quantity = (
                int(position["filled_qty"])
                - int(position["closed_qty"])
            )

            if open_quantity <= 0:
                continue

            allocated = min(
                open_quantity,
                remaining_exit,
            )

            position["closed_qty"] += allocated
            remaining_exit -= allocated

        if remaining_exit != 0:
            raise RuntimeError(
                "Exit allocation integrity failure."
            )

        totals = self._recalculate_quantities()

        if totals["total_quantity"] == 0:

            self.cycle_active = False
            self.cycle_closed = True
            self.next_grid_price = None

        return {
            "closed_quantity": delta,
            "cycle_closed": self.cycle_closed,
            "positions": totals,
        }

    # ======================================================
    # NEXT GRID AFTER FILL
    # ======================================================

    def advance_grid_after_fill(self, filled_price):

        filled_price = self._valid_price(
            filled_price,
            "filled price",
        )

        if self.entry_count >= self.maximum_entries:
            self.next_grid_price = None
            return None

        if self.direction == "SELL":
            self.next_grid_price = (
                filled_price - self.grid_points
            )
        else:
            self.next_grid_price = (
                filled_price + self.grid_points
            )

        return self.next_grid_price

    # ======================================================
    # SNAPSHOT
    # ======================================================

    def snapshot(self):

        return {
            "cycle_active": self.cycle_active,
            "cycle_closed": self.cycle_closed,
            "direction": self.direction,
            "initial_entry_price": self.initial_entry_price,
            "common_stop_loss": self.common_stop_loss,
            "next_grid_price": self.next_grid_price,
            "entry_count": self.entry_count,
            "maximum_entries": self.maximum_entries,
            "quantity_per_entry": self.quantity_per_entry,
            "positions": self.positions,
            "total_quantity": self.total_quantity,
            "total_margin_quantity": self.total_margin_quantity,
            "total_intraday_quantity": self.total_intraday_quantity,
            "last_entry_price": self.last_entry_price,
            "created_at": self.created_at,
        }
