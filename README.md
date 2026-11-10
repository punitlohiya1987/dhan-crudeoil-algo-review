# Dhan CRUDEOILM Algo — Clean Python Package

This branch contains the Python modules with correct .py filenames for CloudHQ project upload.

## Files
- main.py (entry point)
- config.py
- dhan_client.py
- execution_guard.py
- fill_tracker.py
- init_state.py
- order_manager.py
- order_monitor.py
- sl_controller.py
- sl_executer.py
- state_store.py
- strategy.py
- state.json

## Safety status — NOT LIVE READY
- Trading mode remains PAPER.
- Order placement and live trading switches remain OFF.
- Durable state is not verified.
- main.py still contains the intentional credential diagnostic stop.
- The current CloudHQ credential substitution failure is not fixed by renaming files.
- Do not enable live orders or treat this package as a live deployment.

This branch is isolated. The original integration-review-2026-11-07 branch is unchanged.
