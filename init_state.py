import json
import hashlib
from datetime import datetime

def generate_initial_state():
    state = {
        "state_version": 5,
        "active_contract": {
            "symbol": "CRUDEOILM-18Dec2026-FUT",
            "security_id": "576265",
            "expiry": "2026-12-18",
            "exchange_segment": "MCX_COMM"
        },
        "strategy": {
            "direction": "SELL",
            "cycle_active": False,
            "cycle_closed": True,
            "execution_id": None,
            "lots_per_entry": 1,
            "lot_size": 10,
            "quantity_per_entry": 10,
            "grid_points": 100,
            "stop_loss_points": 100,
            "maximum_entries": 10,
            "maximum_overnight_lots": 3
        },
        "prices": {
            "initial_entry": None,
            "last_entry": None,
            "next_grid": None,
            "common_stop_loss": None
        },
        "positions": {
            "total_quantity": 0,
            "margin_quantity": 0,
            "intraday_quantity": 0,
            "common_stop_loss_quantity": 0,
            "registered_positions": {}
        },
        "orders": {
            "pending_entry_orders": {},
            "stop_loss_orders": {},
            "order_fill_totals": {},
            "manual_cancelled_orders": {}
        },
        "manual_cancel_locks": {
            "ENTRY_LIMIT": False,
            "STOP_LOSS": False,
            "records": []
        },
        "reconciliation": {
            "positions_checked": False,
            "orders_checked": False
        },
        "updated_at": datetime.now().isoformat()
    }

    # Calculate Checksum
    payload = dict(state)
    payload.pop("checksum", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    checksum = hashlib.sha256(encoded).hexdigest()
    state["checksum"] = checksum

    with open("state.json", "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True, ensure_ascii=False)

    print("Successfully generated fresh state.json with valid SHA-256 checksum!")

if __name__ == "__main__":
    generate_initial_state()
