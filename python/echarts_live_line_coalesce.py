#!/usr/bin/env python3
"""Live ECharts 2x2 line dashboard using coalesced chart_option updates."""
from __future__ import annotations

import argparse
import math
import time

from echarts_graph_lib import EChartsPallet
from pallet import DEFAULT_BRIDGE_HOST, DEFAULT_BRIDGE_PORT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", nargs="?", default=None, help="bridge TCP host")
    parser.add_argument("--bridge-host", default=DEFAULT_BRIDGE_HOST)
    parser.add_argument("--bridge-port", type=int, default=DEFAULT_BRIDGE_PORT)
    parser.add_argument("--port", type=int, default=None, help="alias for --bridge-port")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--page", default="live-line")
    args = parser.parse_args()

    bridge_host = args.host or args.bridge_host
    bridge_port = args.port if args.port is not None else args.bridge_port

    pallet = EChartsPallet(host=bridge_host, port=bridge_port)
    pallet.start(timeout=args.timeout)
    pallet.clear(color="#0f172a", page=args.page)

    main_points = 90
    fast_points = 70
    dual_points = 80
    drift_points = 110

    main_xs = list(range(main_points))
    fast_xs = list(range(fast_points))
    dual_xs = list(range(dual_points))
    drift_xs = list(range(drift_points))

    main_chart = pallet.line_chart(
        id="live-main",
        x=24,
        y=24,
        width=560,
        height=300,
        x_data=main_xs,
        y_data=[0.0 for _ in main_xs],
        title="Signal",
        series_names=["Signal"],
        smooth=True,
        y_axis_name="value",
        x_axis_name="sample",
        page=args.page,
        extra_option={
            "backgroundColor": "#111827",
            "animationDurationUpdate": 120,
            "yAxis": {"type": "value", "name": "value", "min": -1.4, "max": 1.4},
        },
    )

    two_trace_chart = pallet.line_chart(
        id="live-two-trace",
        x=620,
        y=24,
        width=720,
        height=360,
        x_data=fast_xs,
        y_data=[
            [0.0 for _ in fast_xs],
            [0.0 for _ in fast_xs],
        ],
        title="Two Traces",
        series_names=["Carrier", "Envelope"],
        smooth=True,
        y_axis_name="amplitude",
        x_axis_name="sample",
        page=args.page,
        extra_option={
            "backgroundColor": "#111827",
            "animationDurationUpdate": 120,
            "legend": {"top": 28, "textStyle": {"color": "#CBD5E1"}},
            "yAxis": {"type": "value", "name": "amplitude", "min": -1.8, "max": 1.8},
        },
    )

    dual_axis_chart = pallet.chart(
        id="live-dual-axis",
        x=24,
        y=420,
        width=660,
        height=430,
        title="Two Traces / Two Y Axes",
        page=args.page,
        titlebar="Two Traces / Two Y Axes",
        option={
            "backgroundColor": "#111827",
            "animationDurationUpdate": 120,
            "title": {"text": "Two Traces / Two Y Axes", "textStyle": {"color": "#E5E7EB"}},
            "tooltip": {"trigger": "axis"},
            "legend": {"top": 28, "textStyle": {"color": "#CBD5E1"}},
            "grid": {"left": 70, "right": 78, "top": 78, "bottom": 48},
            "xAxis": {
                "type": "category",
                "name": "sample",
                "boundaryGap": False,
                "data": dual_xs,
                "axisLine": {"lineStyle": {"color": "#94A3B8"}},
                "axisLabel": {"color": "#CBD5E1"},
            },
            "yAxis": [
                {
                    "type": "value",
                    "name": "temperature",
                    "min": 68,
                    "max": 78,
                    "axisLine": {"lineStyle": {"color": "#38BDF8"}},
                    "axisLabel": {"color": "#BAE6FD"},
                    "splitLine": {"lineStyle": {"color": "#334155"}},
                },
                {
                    "type": "value",
                    "name": "voltage",
                    "min": 3.05,
                    "max": 3.45,
                    "axisLine": {"lineStyle": {"color": "#F59E0B"}},
                    "axisLabel": {"color": "#FDE68A"},
                    "splitLine": {"show": False},
                },
            ],
            "series": [
                {
                    "name": "Temperature",
                    "type": "line",
                    "smooth": True,
                    "showSymbol": False,
                    "yAxisIndex": 0,
                    "data": [72.0 for _ in dual_xs],
                    "lineStyle": {"color": "#38BDF8", "width": 3},
                },
                {
                    "name": "Voltage",
                    "type": "line",
                    "smooth": True,
                    "showSymbol": False,
                    "yAxisIndex": 1,
                    "data": [3.25 for _ in dual_xs],
                    "lineStyle": {"color": "#F59E0B", "width": 3},
                },
            ],
        },
    )

    drift_chart = pallet.line_chart(
        id="live-drift",
        x=720,
        y=470,
        width=520,
        height=330,
        x_data=drift_xs,
        y_data=[0.0 for _ in drift_xs],
        title="Slow Drift Area",
        series_names=["Drift"],
        smooth=True,
        area=True,
        y_axis_name="offset",
        x_axis_name="sample",
        page=args.page,
        extra_option={
            "backgroundColor": "#111827",
            "animationDurationUpdate": 120,
            "yAxis": {"type": "value", "name": "offset", "min": -1.0, "max": 1.0},
        },
    )
    pallet.show_page(args.page)

    print(f"Live 2x2 line dashboard running on page {args.page!r}. Press Ctrl+C to stop.")
    try:
        step = 0
        while True:
            main_xs = list(range(step, step + main_points))
            fast_xs = list(range(step, step + fast_points))
            dual_xs = list(range(step, step + dual_points))
            drift_xs = list(range(step, step + drift_points))

            main_ys = [
                round(
                    math.sin((step + index) * 0.18)
                    + 0.25 * math.sin((step + index) * 0.73),
                    3,
                )
                for index in range(main_points)
            ]
            carrier = [
                round(math.sin((step + index) * 0.32), 3)
                for index in range(fast_points)
            ]
            envelope = [
                round(1.25 * math.sin((step + index) * 0.08), 3)
                for index in range(fast_points)
            ]
            temperature = [
                round(
                    73.0
                    + 2.1 * math.sin((step + index) * 0.055)
                    + 0.4 * math.sin((step + index) * 0.31),
                    2,
                )
                for index in range(dual_points)
            ]
            voltage = [
                round(
                    3.24
                    + 0.12 * math.cos((step + index) * 0.065)
                    + 0.025 * math.sin((step + index) * 0.43),
                    3,
                )
                for index in range(dual_points)
            ]
            drift = [
                round(
                    0.65 * math.sin((step + index) * 0.035)
                    + 0.18 * math.sin((step + index) * 0.16),
                    3,
                )
                for index in range(drift_points)
            ]

            main_chart.set_option(
                {
                    "xAxis": {"data": main_xs},
                    "series": [{"name": "Signal", "data": main_ys}],
                },
                coalesce=True,
            )
            two_trace_chart.set_option(
                {
                    "xAxis": {"data": fast_xs},
                    "series": [
                        {"name": "Carrier", "data": carrier},
                        {"name": "Envelope", "data": envelope},
                    ],
                },
                coalesce=True,
            )
            dual_axis_chart.set_option(
                {
                    "xAxis": {"data": dual_xs},
                    "series": [
                        {"name": "Temperature", "data": temperature},
                        {"name": "Voltage", "data": voltage},
                    ],
                },
                coalesce=True,
            )
            drift_chart.set_option(
                {
                    "xAxis": {"data": drift_xs},
                    "series": [{"name": "Drift", "data": drift}],
                },
                coalesce=True,
            )
            step += 1
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("Stopping live 2x2 line dashboard.")
    finally:
        pallet.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
