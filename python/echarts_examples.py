"""
example_echarts_gallery_helpers.py

Demonstrates higher-level helper functions inspired by the Apache ECharts
example gallery. These helpers avoid writing most ECharts option JSON.

Run bridge.py, open pallet.html and connect it, then run:
    python echarts_examples.py

Chart commands are sent through the existing bridge TCP connection.
"""

import argparse
import math
import time

from echarts_graph_lib import EChartsPallet
from pallet import DEFAULT_BRIDGE_HOST, DEFAULT_BRIDGE_PORT


def main():
    parser = argparse.ArgumentParser(description="Apache ECharts pallet examples")
    parser.add_argument("host", nargs="?", default=None, help="bridge TCP host")
    parser.add_argument("--bridge-host", default=DEFAULT_BRIDGE_HOST, help="bridge TCP host or IP address")
    parser.add_argument("--bridge-port", type=int, default=DEFAULT_BRIDGE_PORT, help="bridge TCP port")
    parser.add_argument("--port", type=int, default=None, help="alias for --bridge-port")
    parser.add_argument("--timeout", type=float, default=5.0, help="bridge connection timeout in seconds")
    args = parser.parse_args()

    bridge_host = args.host or args.bridge_host
    bridge_port = args.port if args.port is not None else args.bridge_port
    print(f"Connecting to bridge TCP server at {bridge_host}:{bridge_port}")

    pallet = EChartsPallet(host=bridge_host, port=bridge_port)
    pallet.start(timeout=args.timeout)
    pallet.clear(color="#0f172a")

    voltage_chart = pallet.progress_gauge(
        id="voltage",
        x=24,
        y=24,
        width=180,
        height=180,
        title="Supply Voltage",
        name="Voltage",
        value=12.4,
        min=0,
        max=15,
        units="V",
    )

    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    stacked_chart = pallet.stacked_line_chart(
        id="stacked",
        x=410,
        y=24,
        width=650,
        height=320,
        title="Stacked Area",
        x_data=weekdays,
        series={
            "A": [120, 132, 101, 134, 90, 230, 210],
            "B": [220, 182, 191, 234, 290, 330, 310],
            "C": [150, 232, 201, 154, 190, 330, 410],
        },
    )

    donut_chart = pallet.doughnut_chart(
        id="donut",
        x=24,
        y=370,
        width=360,
        height=320,
        title="Power Budget",
        data=[("Logic", 42), ("RF", 28), ("Display", 18), ("Other", 12)],
    )

    heat_x_labels = ["T0", "T1", "T2", "T3", "T4"]
    heat_y_labels = ["CH1", "CH2", "CH3", "CH4"]
    heatmap_chart = pallet.heatmap_chart(
        id="heat",
        x=410,
        y=370,
        width=650,
        height=320,
        title="Channel Heatmap",
        x_labels=heat_x_labels,
        y_labels=heat_y_labels,
        values=[
            (0, 0, 5), (1, 0, 7), (2, 0, 3), (3, 0, 8), (4, 0, 6),
            (0, 1, 2), (1, 1, 4), (2, 1, 6), (3, 1, 5), (4, 1, 7),
            (0, 2, 8), (1, 2, 3), (2, 2, 4), (3, 2, 9), (4, 2, 5),
            (0, 3, 1), (1, 3, 6), (2, 3, 7), (3, 3, 4), (4, 3, 2),
        ],
    )

    print("Charts are displayed in pallet.html through bridge.py")
    print("Press Ctrl+C to stop.")

    t = 0
    try:
        while True:
            voltage = 12.0 + 0.6 * math.sin(t / 10.0)
            voltage_chart.set_option(
                {
                    "series": [
                        {
                            "data": [{"value": round(voltage, 2), "name": "Voltage"}],
                        },
                    ],
                },
                coalesce=True,
            )

            stacked_series = []
            for offset, name in enumerate(("A", "B", "C")):
                stacked_series.append({
                    "name": name,
                    "data": [
                        round(150 + offset * 55 + 80 * math.sin((t + day * 2 + offset * 3) / 9.0))
                        for day in range(len(weekdays))
                    ],
                })
            stacked_chart.set_option({"series": stacked_series}, coalesce=True)

            donut_values = [
                ("Logic", 42 + 6 * math.sin(t / 13.0)),
                ("RF", 28 + 4 * math.cos(t / 11.0)),
                ("Display", 18 + 3 * math.sin(t / 17.0 + 1.0)),
                ("Other", 12 + 2 * math.cos(t / 19.0 + 0.5)),
            ]
            donut_chart.set_option(
                {
                    "series": [
                        {
                            "data": [
                                {"name": name, "value": round(value, 1)}
                                for name, value in donut_values
                            ],
                        },
                    ],
                },
                coalesce=True,
            )

            heat_values = []
            for y_index, _label in enumerate(heat_y_labels):
                for x_index, _label in enumerate(heat_x_labels):
                    value = 5 + 4 * math.sin((t + x_index * 2 + y_index * 3) / 8.0)
                    heat_values.append([x_index, y_index, round(value, 1)])
            heatmap_chart.set_option(
                {
                    "visualMap": {"min": 1, "max": 9},
                    "series": [{"data": heat_values}],
                },
                coalesce=True,
            )

            t += 1
            time.sleep(0.25)
    except KeyboardInterrupt:
        pallet.stop()


if __name__ == "__main__":
    main()
