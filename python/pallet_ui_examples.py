#!/usr/bin/env python3
"""Interactive controls, responsive cards, and live-table demo for Pallet."""
from __future__ import annotations

import argparse
import time

from pallet import DEFAULT_BRIDGE_HOST, DEFAULT_BRIDGE_PORT, Pallet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge-host", default=DEFAULT_BRIDGE_HOST)
    parser.add_argument("--bridge-port", type=int, default=DEFAULT_BRIDGE_PORT)
    parser.add_argument("--page", default=None)
    args = parser.parse_args()

    with Pallet.for_bridge(args.bridge_host, args.bridge_port, page=args.page) as pallet:
        pallet.clear("#E2E8F0")
        pallet.define_grid("dashboard", columns=2, min_column_width=300, gap=16, padding=16)
        pallet.define_card("controls", grid="dashboard", title="Interactive controls")
        pallet.define_card("status", grid="dashboard", title="System status")
        pallet.define_card("readings", grid="dashboard", title="Live readings")

        pallet.control("start", card="controls", kind="button", label="Add reading")
        pallet.control("enabled", card="controls", kind="toggle", label="Enabled", value=True)
        pallet.control("level", card="controls", kind="slider", label="Level", value=50, minimum=0, maximum=100, step=1, live=True)
        pallet.control("mode", card="controls", kind="select", label="Mode", value="auto", options=["auto", "manual", "safe"])
        pallet.control("name", card="controls", kind="text", label="Name", value="sensor-a", placeholder="Sensor name")
        pallet.control("last-event", card="controls", kind="text", label="Last event", value="Waiting", disabled=True)

        online = pallet.status_widget("online", card="status", kind="led", label="Connection", value="Online", status="success")
        load = pallet.status_widget("load", card="status", kind="progress", label="Load", value=50, units="%")
        count = pallet.status_widget("count", card="status", kind="kpi", label="Readings", value=0, status="info")
        mode_badge = pallet.status_widget("mode-status", card="status", kind="badge", label="Mode", value="auto", status="neutral")
        activity = pallet.status_widget("activity", card="status", kind="spinner", label="Activity", value="Idle", active=False)
        alert = pallet.status_widget("health-alert", card="status", kind="alert", message="All systems normal", status="success")

        table = pallet.table(
            "readings-table",
            [
                {"key": "id", "label": "#", "align": "right"},
                {"key": "sensor", "label": "Sensor"},
                {"key": "value", "label": "Value", "align": "right"},
                {"key": "time", "label": "Time"},
            ],
            card="readings",
            key_field="id",
            filterable=True,
            selectable=True,
            max_rows=100,
            height=320,
        )

        state = {"next_id": 1, "name": "sensor-a", "level": 50, "count": 0}

        def handle_event(event: dict) -> None:
            control_id = event.get("id")
            value = event.get("value")
            pallet.update_control("last-event", value=f"{control_id}: {value}")
            if control_id == "name":
                state["name"] = str(value)
            elif control_id == "level":
                state["level"] = value
                load.set(value, status="danger" if value >= 90 else "warning" if value >= 70 else "info")
            elif control_id == "mode":
                mode_badge.set(value)
            elif control_id == "enabled":
                online.set("Online" if value else "Offline", active=bool(value), status="success" if value else "neutral")
                alert.set(message="All systems normal" if value else "Collection is disabled", status="success" if value else "warning")
            elif control_id == "start":
                activity.set("Updating", active=True)
                row_id = state["next_id"]
                state["next_id"] += 1
                table.upsert({
                    "id": row_id,
                    "sensor": state["name"],
                    "value": state["level"],
                    "time": time.strftime("%H:%M:%S"),
                })
                state["count"] += 1
                count.set(state["count"])
                activity.set("Idle", active=False)

        pallet.on_ui_event("*", handle_event)
        print("Interactive dashboard running. Press Ctrl+C to stop.")
        try:
            pallet.run_event_loop()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
