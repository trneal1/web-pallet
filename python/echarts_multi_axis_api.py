"""echarts_multi_axis_api.py

Demonstrates the multi-axis helper and builder APIs in the bridge-based web
pallet.

Run:
    1. python bridge.py
    2. Open pallet.html and connect it to ws://localhost:8080
    3. python echarts_multi_axis_api.py --bridge-port 9001
"""

import argparse
import math
import time

from echarts_graph_lib import EChartsPallet
from pallet import DEFAULT_BRIDGE_HOST, DEFAULT_BRIDGE_PORT


PAGE = "multi-axis"


def simple_2x2y_example(pallet: EChartsPallet):
    # Shortest API for the common case: 2 x axes and 2 y axes.
    return pallet.line_chart_2x2y(
        id="simple_2x2y",
        x=20,
        y=30,
        width=590,
        height=480,
        title="Simple 2 X / 2 Y Line Chart",

        bottom_x=["0s", "1s", "2s", "3s", "4s", "5s"],
        top_x=[0, 1, 2, 3, 4, 5],

        left_series=[72.0, 72.5, 73.0, 73.4, 73.2, 73.8],
        right_series=[3.20, 3.23, 3.25, 3.24, 3.28, 3.30],

        bottom_x_name="Time",
        top_x_name="Sample",
        left_y_name="Temperature",
        left_y_units="°F",
        right_y_name="Voltage",
        right_y_units="V",

        left_series_name="Temperature",
        right_series_name="Voltage",
        data_zoom=True,
        page=PAGE,
    )


def builder_example(pallet: EChartsPallet):
    # Builder API for arbitrary multi-axis line charts.
    chart = pallet.multi_axis_line_chart(
        id="builder_multi_axis",
        x=630,
        y=30,
        width=590,
        height=480,
        title="Builder API Multi-Axis Chart",
        data_zoom=True,
        page=PAGE,
    )

    chart.add_x_axis("Time", data=["0s", "1s", "2s", "3s", "4s"], position="bottom")
    chart.add_x_axis("Sample", data=[0, 1, 2, 3, 4], position="top")

    chart.add_y_axis("Temperature", units="°F", position="left")
    chart.add_y_axis("Voltage", units="V", position="right")

    chart.add_line(
        "Temperature",
        [72.0, 72.4, 72.9, 73.1, 73.5],
        x_axis="Time",
        y_axis="Temperature",
        smooth=True,
        area=True,
    )

    chart.add_line(
        "Voltage",
        [3.20, 3.24, 3.25, 3.28, 3.30],
        x_axis="Sample",
        y_axis="Voltage",
        smooth=True,
    )

    chart.render()
    return chart


def main():
    parser = argparse.ArgumentParser(description="ECharts multi-axis API examples")
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
    pallet.clear(color="#0f172a", page=PAGE)

    simple_handle = simple_2x2y_example(pallet)
    builder_chart = builder_example(pallet)

    pallet.gauge(
        id="cpu",
        x=1240,
        y=30,
        width=240,
        height=320,
        title="CPU Load",
        value=35,
        units="%",
        page=PAGE,
        extra_series={
            "detail": {
                "valueAnimation": True,
                "formatter": "{value}%",
                "fontSize": 18,
            },
        },
    )

    pallet.show_page(PAGE)

    print(f"Multi-axis demo is running on pallet page {PAGE!r}")
    print("Press Ctrl+C to stop.")

    try:
        i = 0
        while True:
            simple_bottom_x = [f"{i + step}s" for step in range(6)]
            simple_top_x = [i + step for step in range(6)]
            simple_temperature = [
                round(72.8 + math.sin((i + step) / 6) * 1.1, 2)
                for step in range(6)
            ]
            simple_voltage = [
                round(3.24 + math.cos((i + step) / 7) * 0.06, 3)
                for step in range(6)
            ]
            simple_handle.set_option(
                {
                    "xAxis": [
                        {"data": simple_bottom_x},
                        {"data": simple_top_x},
                    ],
                    "series": [
                        {"name": "Temperature", "data": simple_temperature},
                        {"name": "Voltage", "data": simple_voltage},
                    ],
                },
                coalesce=True,
            )

            builder_time = [f"{i + step}s" for step in range(5)]
            builder_sample = [i + step for step in range(5)]
            builder_temperature = [
                round(72.5 + math.sin((i + step) / 5) * 1.4, 2)
                for step in range(5)
            ]
            builder_voltage = [
                round(3.24 + math.cos((i + step) / 6) * 0.05, 3)
                for step in range(5)
            ]
            assert builder_chart.handle is not None
            builder_chart.handle.set_option(
                {
                    "xAxis": [
                        {"data": builder_time},
                        {"data": builder_sample},
                    ],
                    "series": [
                        {"name": "Temperature", "data": builder_temperature},
                        {"name": "Voltage", "data": builder_voltage},
                    ],
                },
                coalesce=True,
            )

            value = 50 + 35 * math.sin(i / 10)
            pallet.update_gauge("cpu", round(value, 1), name="Load", page=PAGE)
            i += 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        pallet.stop()


if __name__ == "__main__":
    main()
