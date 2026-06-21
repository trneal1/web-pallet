"""Live grouped ECharts bar chart with a rolling time axis.

Run:
    1. python bridge.py
    2. Open pallet.html and connect it to ws://localhost:8080
    3. python echarts_live_grouped_bar.py
"""

import argparse
import math
import time
from collections import deque

from echarts_graph_lib import EChartsPallet
from pallet import DEFAULT_BRIDGE_HOST, DEFAULT_BRIDGE_PORT


PAGE = "live-bars"
CHART_ID = "live-grouped-bars"


def sample_values(sample_number: int) -> tuple[float, float]:
    """Return two changing, deterministic demo values."""
    north = 55 + 18 * math.sin(sample_number / 3.0)
    south = 48 + 15 * math.cos(sample_number / 4.0)
    return round(north, 1), round(south, 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Live rolling grouped ECharts bar chart")
    parser.add_argument("host", nargs="?", default=None, help="bridge TCP host")
    parser.add_argument("--bridge-host", default=DEFAULT_BRIDGE_HOST)
    parser.add_argument("--bridge-port", type=int, default=DEFAULT_BRIDGE_PORT)
    parser.add_argument("--port", type=int, default=None, help="alias for --bridge-port")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--interval", type=float, default=5.0, help="seconds between samples")
    parser.add_argument("--points", type=int, default=12, help="samples visible in the rolling window")
    args = parser.parse_args()

    if args.interval <= 0:
        parser.error("--interval must be greater than zero")
    if args.points < 2:
        parser.error("--points must be at least 2")

    bridge_host = args.host or args.bridge_host
    bridge_port = args.port if args.port is not None else args.bridge_port
    pallet = EChartsPallet(host=bridge_host, port=bridge_port)
    pallet.start(timeout=args.timeout)

    north_data: deque[list[float]] = deque(maxlen=args.points)
    south_data: deque[list[float]] = deque(maxlen=args.points)

    # Start with one full window so the shifting time range is visible at once.
    now_ms = int(time.time() * 1000)
    interval_ms = int(args.interval * 1000)
    for index in range(args.points):
        timestamp = now_ms - (args.points - 1 - index) * interval_ms
        north, south = sample_values(index)
        north_data.append([timestamp, north])
        south_data.append([timestamp, south])

    pallet.clear(color="#0f172a", page=PAGE)
    pallet.chart(
        id=CHART_ID,
        x=24,
        y=24,
        width=1050,
        height=560,
        title="Live Grouped Throughput",
        page=PAGE,
        background="#ffffff",
        option={
            "animationDurationUpdate": 500,
            "legend": {"top": 34},
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "grid": {"left": 70, "right": 30, "top": 85, "bottom": 75},
            "xAxis": {
                "type": "time",
                "name": "Time",
                "nameLocation": "middle",
                "nameGap": 48,
                "boundaryGap": ["8%", "8%"],
                "axisLabel": {"hideOverlap": True},
            },
            "yAxis": {
                "type": "value",
                "name": "Requests / second",
                "min": 0,
            },
            "series": [
                {
                    "id": "north",
                    "name": "North",
                    "type": "bar",
                    "barMaxWidth": 24,
                    "data": list(north_data),
                },
                {
                    "id": "south",
                    "name": "South",
                    "type": "bar",
                    "barMaxWidth": 24,
                    "data": list(south_data),
                },
            ],
        },
    )
    pallet.show_page(PAGE)

    print(f"Live grouped bars are displayed on page {PAGE!r}.")
    print(f"Adding a sample every {args.interval:g} seconds; press Ctrl+C to stop.")

    sample_number = args.points
    try:
        while True:
            time.sleep(args.interval)
            timestamp = int(time.time() * 1000)
            north, south = sample_values(sample_number)
            north_data.append([timestamp, north])
            south_data.append([timestamp, south])

            # Existing series are matched by id, so only this chart is updated.
            # The bounded deques drop the oldest timestamp as the newest arrives.
            pallet.set_option(
                CHART_ID,
                {
                    "series": [
                        {"id": "north", "data": list(north_data)},
                        {"id": "south", "data": list(south_data)},
                    ]
                },
                lazy_update=True,
                page=PAGE,
            )
            sample_number += 1
    except KeyboardInterrupt:
        pallet.stop()


if __name__ == "__main__":
    main()
