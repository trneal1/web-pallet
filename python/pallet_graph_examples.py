#!/usr/bin/env python3
"""
pallet_graph_examples.py
========================
Example graphs for ``pallet.html``.

Start the bridge and connect the browser first:

    python python/bridge.py

Then open ``pallet.html`` and connect it to ``ws://localhost:8080``. Finally:

    python python/pallet_graph_examples.py --bridge-host 127.0.0.1 --demo 1
    python python/pallet_graph_examples.py --bridge-host 192.168.1.50
"""
from __future__ import annotations

import argparse
import math
import random
import sys
import time

from pallet import DEFAULT_BRIDGE_HOST, DEFAULT_BRIDGE_PORT, Pallet
from pallet_graph_lib import Graph


def print_pallet_size_info(pallet: Pallet) -> None:
    print(f"Using pallet drawing size {pallet.width}x{pallet.height}")
    if pallet.css_width and pallet.css_height:
        print(f"Browser CSS size {pallet.css_width}x{pallet.css_height}")
    if pallet.canvas_width and pallet.canvas_height:
        print(f"Browser canvas buffer {pallet.canvas_width}x{pallet.canvas_height}")
    if pallet.max_css_width and pallet.max_css_height:
        print(f"Browser max CSS size {pallet.max_css_width}x{pallet.max_css_height}")
    if pallet.screen_width and pallet.screen_height:
        print(f"Screen size {pallet.screen_width}x{pallet.screen_height}")
    if pallet.screen_avail_width and pallet.screen_avail_height:
        print(f"Screen available {pallet.screen_avail_width}x{pallet.screen_avail_height}")
    if pallet.device_pixel_ratio:
        print(f"Device pixel ratio {pallet.device_pixel_ratio}")


def start_demo_page(pallet: Pallet, color: str = "white") -> None:
    pallet.clear(color)


def demo_sine_cosine(pallet: Pallet) -> None:
    start_demo_page(pallet)
    xs = [i * 0.2 for i in range(40)]
    g = Graph(pallet, title="sin / cos", x_label="Radians", y_label="Amp")
    g.add_series(xs, [math.sin(x) for x in xs], color="#06B6D4", label="sin")
    g.add_series(xs, [math.cos(x) for x in xs], color="#F97316", label="cos")
    g.draw()


def demo_quadratic(pallet: Pallet) -> None:
    start_demo_page(pallet)
    xs = list(range(-10, 11))
    g = Graph(pallet, title="y = x^2", x_label="x", y_label="y")
    g.add_series(xs, [x * x for x in xs], color="#EAB308", label="x^2")
    g.draw()


def demo_random_scatter(pallet: Pallet) -> None:
    start_demo_page(pallet)
    rng = random.Random(42)
    n = 30
    g = Graph(pallet, title="Scatter", x_label="x", y_label="y")
    g.add_series(
        [rng.uniform(0, 100) for _ in range(n)],
        [rng.uniform(-50, 50) for _ in range(n)],
        color="#EC4899",
        label="pts",
        draw_line=False,
        draw_markers=True,
        marker_radius=5,
    )
    g.draw()


def demo_multi_series(pallet: Pallet) -> None:
    start_demo_page(pallet)
    xs = [i * 0.25 for i in range(34)]
    g = Graph(pallet, title="3 series", x_label="t", y_label="val")
    g.add_series(xs, [math.sin(x) * 10 for x in xs], color="#06B6D4", label="A")
    g.add_series(xs, [math.cos(x) * 8 for x in xs], color="#F97316", label="B")
    g.add_series(xs, [math.sin(2 * x) * 5 for x in xs], color="#22C55E", label="C")
    g.draw()


def demo_linear_with_noise(pallet: Pallet) -> None:
    start_demo_page(pallet)
    rng = random.Random(7)
    xs = [i * 2.0 for i in range(25)]
    ys = [0.5 * x - 10 + rng.gauss(0, 3) for x in xs]
    g = Graph(pallet, title="Linear trend", x_label="x", y_label="y")
    g.add_series(xs, ys, color="#818CF8", label="data")
    g.add_series([xs[0], xs[-1]], [0.5 * xs[0] - 10, 0.5 * xs[-1] - 10], color="#EF4444", label="trend", draw_markers=False)
    g.draw()


def demo_log_x(pallet: Pallet) -> None:
    start_demo_page(pallet)
    fc = 1000.0
    freqs = [10.0 * (10 ** (i * 4 / 24)) for i in range(25)]
    gains = [-20 * math.log10(math.sqrt(1 + (f / fc) ** 2)) for f in freqs]
    g = Graph(pallet, title="Low-pass (1 kHz)", x_label="Hz", y_label="dB", log_x=True, x_min=10, x_max=100_000)
    g.add_series(freqs, gains, color="#06B6D4", label="gain")
    g.draw()


def demo_log_y(pallet: Pallet) -> None:
    start_demo_page(pallet)
    xs = list(range(0, 11))
    g = Graph(pallet, title="2^x (log Y)", x_label="x", y_label="2^x", log_y=True)
    g.add_series(xs, [2.0 ** x for x in xs], color="#EAB308", label="2^x")
    g.draw()


def demo_log_xy(pallet: Pallet) -> None:
    start_demo_page(pallet)
    xs = [10.0 ** (i * 0.25) for i in range(17)]
    g = Graph(pallet, title="y=x^1.5 (log-log)", x_label="x", y_label="y", log_x=True, log_y=True)
    g.add_series(xs, [x ** 1.5 for x in xs], color="#EC4899", label="x^1.5")
    g.draw()


def demo_dual_y(pallet: Pallet) -> None:
    start_demo_page(pallet)
    times = list(range(0, 25))
    temps = [15 + 8 * math.sin((t - 6) * math.pi / 12) for t in times]
    humidity = [75 - 20 * math.sin((t - 6) * math.pi / 12) for t in times]
    g = Graph(pallet, title="Temp & Humidity", x_label="Hour", y_label="degC", y2_label="%RH", y_min=0, y_max=30, y2_min=40, y2_max=100)
    g.add_series(times, temps, color="#EF4444", label="T", y_axis=1)
    g.add_series(times, humidity, color="#0EA5E9", label="RH", y_axis=2)
    g.draw()


def demo_dual_y_log(pallet: Pallet) -> None:
    start_demo_page(pallet)
    ts = [i * 0.5 for i in range(21)]
    volts = [5 * math.exp(-t / 5) for t in ts]
    amps = [0.01 * math.exp(-t / 5) + 1e-4 for t in ts]
    g = Graph(pallet, title="RC discharge", x_label="sec", y_label="V", y2_label="A", log_y2=True, y_min=0, y_max=6)
    g.add_series(ts, volts, color="#EAB308", label="V", y_axis=1)
    g.add_series(ts, amps, color="#F97316", label="I", y_axis=2)
    g.draw()


def demo_bar_basic(pallet: Pallet) -> None:
    start_demo_page(pallet)
    months = list(range(1, 13))
    rain = [45, 38, 52, 67, 80, 55, 30, 28, 48, 72, 60, 50]
    g = Graph(pallet, title="Monthly Rainfall", x_label="Month", y_label="mm", y_min=0, y_max=100)
    g.add_bar_series(months, rain, color="#3B82F6", outline_color="#1D4ED8", label="rain")
    g.draw()


def demo_bar_grouped(pallet: Pallet) -> None:
    start_demo_page(pallet)
    quarters = [1, 2, 3, 4]
    sales_a = [120, 150, 130, 180]
    sales_b = [90, 110, 160, 140]
    g = Graph(pallet, title="Quarterly Sales", x_label="Quarter", y_label="Units", y_min=0, y_max=200)
    g.add_bar_series(quarters, sales_a, color="#14B8A6", outline_color="#0F766E", label="Product A")
    g.add_bar_series(quarters, sales_b, color="#F97316", outline_color="#C2410C", label="Product B")
    g.draw()


def demo_bar_negative(pallet: Pallet) -> None:
    start_demo_page(pallet)
    months = list(range(1, 9))
    profit = [20, -10, 35, 15, -5, 40, 25, -8]
    g = Graph(pallet, title="Profit / Loss", x_label="Month", y_label="$k", y_min=-20, y_max=50)
    g.add_bar_series(months, profit, color="#22C55E", outline_color="#15803D", label="profit")
    g.draw()


def demo_area_basic(pallet: Pallet) -> None:
    start_demo_page(pallet)
    ts = [i * 0.5 for i in range(24)]
    cpu = [30 + 20 * math.sin(t * 0.8) + 10 * math.sin(t * 2.1) for t in ts]
    g = Graph(pallet, title="CPU Usage", x_label="sec", y_label="%", y_min=0, y_max=80)
    g.add_area_series(ts, cpu, color="#93C5FD", outline_color="#2563EB", label="CPU")
    g.draw()


def demo_area_stacked(pallet: Pallet) -> None:
    start_demo_page(pallet)
    ts = list(range(24))
    rx = [max(0, 5 + 8 * math.sin(t * math.pi / 6) + 3 * math.sin(t * math.pi / 2)) for t in ts]
    tx = [max(0, 3 + 4 * math.cos(t * math.pi / 6) + 2 * math.cos(t * math.pi / 3)) for t in ts]
    g = Graph(pallet, title="Network Traffic", x_label="Hour", y_label="MB/s", y_min=0, y_max=20)
    g.add_area_series(ts, rx, color="#BAE6FD", outline_color="#0284C7", label="RX")
    g.add_area_series(ts, tx, color="#FBCFE8", outline_color="#DB2777", label="TX")
    g.draw()


def demo_bar_and_line(pallet: Pallet) -> None:
    start_demo_page(pallet)
    months = list(range(1, 13))
    rainfall = [45, 38, 52, 67, 80, 55, 30, 28, 48, 72, 60, 50]
    temp = [5, 6, 9, 13, 17, 21, 23, 22, 18, 14, 9, 6]
    g = Graph(pallet, title="Rain & Temp", x_label="Month", y_label="mm", y2_label="degC", y_min=0, y_max=100, y2_min=0, y2_max=30)
    g.add_bar_series(months, rainfall, color="#3B82F6", outline_color="#1D4ED8", label="Rain", y_axis=1)
    g.add_series(months, temp, color="#EF4444", label="Temp", y_axis=2)
    g.draw()


def demo_positioned_graphs(pallet: Pallet) -> None:
    start_demo_page(pallet, "#F8FAFC")
    gap = max(12, min(pallet.width, pallet.height) // 40)
    cell_w = max(240, (pallet.width - gap * 3) // 2)
    cell_h = max(180, (pallet.height - gap * 3) // 2)
    left_x = gap
    right_x = gap * 2 + cell_w
    top_y = gap
    bottom_y = gap * 2 + cell_h

    xs = [i * 0.3 for i in range(24)]
    Graph(
        pallet,
        x=left_x,
        y=top_y,
        width=cell_w,
        height=cell_h,
        title="Wave A",
        x_label="t",
        y_label="amp",
    ).add_series(
        xs,
        [math.sin(x) for x in xs],
        color="#06B6D4",
        label="sin",
    ).draw()

    Graph(
        pallet,
        x=right_x,
        y=top_y,
        width=cell_w,
        height=cell_h,
        title="Wave B",
        x_label="t",
        y_label="amp",
    ).add_series(
        xs,
        [math.cos(x) for x in xs],
        color="#F97316",
        label="cos",
    ).draw()

    quarters = [1, 2, 3, 4]
    Graph(
        pallet,
        x=left_x,
        y=bottom_y,
        width=cell_w,
        height=cell_h,
        title="Sales",
        x_label="Q",
        y_label="units",
        y_min=0,
        y_max=200,
    ).add_bar_series(
        quarters,
        [120, 150, 130, 180],
        color="#14B8A6",
        outline_color="#0F766E",
        label="A",
    ).draw()

    ts = list(range(18))
    Graph(
        pallet,
        x=right_x,
        y=bottom_y,
        width=cell_w,
        height=cell_h,
        title="CPU",
        x_label="sec",
        y_label="%",
        y_min=0,
        y_max=80,
    ).add_area_series(
        ts,
        [30 + 20 * math.sin(t * 0.45) + 8 * math.sin(t * 1.3) for t in ts],
        color="#BAE6FD",
        outline_color="#0284C7",
        label="load",
    ).draw()


DEMOS = [
    (1, "Sine / Cosine", demo_sine_cosine),
    (2, "Quadratic y=x^2", demo_quadratic),
    (3, "Random scatter", demo_random_scatter),
    (4, "Three series", demo_multi_series),
    (5, "Linear with noise", demo_linear_with_noise),
    (6, "Log X  (Bode plot)", demo_log_x),
    (7, "Log Y  (exponential)", demo_log_y),
    (8, "Log X+Y (power law)", demo_log_xy),
    (9, "Dual Y axes", demo_dual_y),
    (10, "Dual Y + log Y2", demo_dual_y_log),
    (11, "Bar chart (basic)", demo_bar_basic),
    (12, "Bar chart (grouped)", demo_bar_grouped),
    (13, "Bar chart (neg values)", demo_bar_negative),
    (14, "Area chart (CPU)", demo_area_basic),
    (15, "Area chart (network)", demo_area_stacked),
    (16, "Bar + line overlay", demo_bar_and_line),
    (17, "Positioned graphs", demo_positioned_graphs),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Pallet graph examples")
    parser.add_argument("host", nargs="?", default=None, help="bridge TCP host, kept for compatibility")
    parser.add_argument("--bridge-host", default=DEFAULT_BRIDGE_HOST, help="bridge TCP host or IP address")
    parser.add_argument("--bridge-port", type=int, default=DEFAULT_BRIDGE_PORT, help="bridge TCP port")
    parser.add_argument("--port", type=int, default=None, help="alias for --bridge-port")
    parser.add_argument("--width", type=int, default=None, help="override browser-reported CSS drawing width")
    parser.add_argument("--height", type=int, default=None, help="override browser-reported CSS drawing height")
    parser.add_argument("--timeout", type=float, default=5.0, help="bridge connection timeout in seconds")
    parser.add_argument("--pause", type=float, default=2.5, help="seconds between demos")
    parser.add_argument("--demo", type=int, default=None, help="run only demo N")
    parser.add_argument("--list", action="store_true", help="list demos and exit")
    args = parser.parse_args()
    bridge_host = args.host or args.bridge_host
    bridge_port = args.port if args.port is not None else args.bridge_port

    if args.list:
        for number, name, _ in DEMOS:
            print(f"{number:2d}  {name}")
        return 0

    to_run = DEMOS if args.demo is None else [demo for demo in DEMOS if demo[0] == args.demo]
    if not to_run:
        print(f"No demo {args.demo}. Use --list to see valid demos.", file=sys.stderr)
        return 1

    try:
        print(f"Connecting to bridge TCP server at {bridge_host}:{bridge_port}")
        with Pallet.for_bridge(
            bridge_host,
            bridge_port,
            width=args.width,
            height=args.height,
            timeout=args.timeout,
        ) as pallet:
            print_pallet_size_info(pallet)
            for index, (number, name, draw) in enumerate(to_run, 1):
                print(f"[{index}/{len(to_run)}] Demo {number}: {name}")
                draw(pallet)
                pallet.save_page()
                if index < len(to_run):
                    time.sleep(args.pause)
    except Exception as exc:
        print(f"Failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
