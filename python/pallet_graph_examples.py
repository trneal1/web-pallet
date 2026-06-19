#!/usr/bin/env python3
"""
pallet_graph_examples.py
========================
Example graphs for ``pallet.html``.

Start the bridge and connect the browser first:

    python python/bridge.py

Then open ``pallet.html`` and connect it to ``ws://localhost:8080``. Finally:

    python python/pallet_graph_examples.py --bridge-host 127.0.0.1 --demo 1
    python python/pallet_graph_examples.py --bridge-host 127.0.0.1 --demo 18
    python python/pallet_graph_examples.py --bridge-host 127.0.0.1 --demo 20
    python python/pallet_graph_examples.py --bridge-host 127.0.0.1 --demo 21
    python python/pallet_graph_examples.py --bridge-host 127.0.0.1 --demo 22
    python python/pallet_graph_examples.py --bridge-host 127.0.0.1 --demo 23
    python python/pallet_graph_examples.py --bridge-host 127.0.0.1 --demo 24
    python python/pallet_graph_examples.py --bridge-host 127.0.0.1 --demo 25
    python python/pallet_graph_examples.py --bridge-host 127.0.0.1 --demo 26
    python python/pallet_graph_examples.py --bridge-host 127.0.0.1 --demo 1 --page 2
    python python/pallet_graph_examples.py --bridge-host 192.168.1.50
"""
from __future__ import annotations

import argparse
import math
import random
import sys
import time

from pallet import DEFAULT_BRIDGE_HOST, DEFAULT_BRIDGE_PORT, Pallet
from pallet_graph_lib import ArcGauge, BarGauge, CircularMeter, GaugeStyle, Graph


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


def demo_histogram(pallet: Pallet) -> None:
    start_demo_page(pallet)
    rng = random.Random(123)
    samples = [
        rng.gauss(0, 1.0) if index < 420 else rng.gauss(2.4, 0.55)
        for index in range(520)
    ]
    g = Graph(
        pallet,
        title="Histogram",
        x_label="value",
        y_label="count",
        x_min=-4,
        x_max=5,
        y_min=0,
    )
    g.add_histogram(
        samples,
        bins=18,
        value_range=(-4, 5),
        color="#8B5CF6",
        outline_color="#5B21B6",
        label="samples",
    )
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


def demo_update_point(pallet: Pallet) -> None:
    start_demo_page(pallet)
    xs = list(range(20))
    ys = [40 + 12 * math.sin(x * 0.45) for x in xs]
    g = Graph(
        pallet,
        title="Update one point",
        x_label="sample",
        y_label="value",
        y_min=15,
        y_max=70,
        graph_id="update-point",
    )
    g.add_series(xs, ys, color="#06B6D4", label="live")
    g.draw()

    for step in range(36):
        point = step % len(xs)
        ys[point] = 40 + 22 * math.sin(step * 0.55)
        g.set_point("live", point, y=ys[point])
        time.sleep(0.08)


def demo_update_series(pallet: Pallet) -> None:
    start_demo_page(pallet)
    xs = [i * 0.25 for i in range(40)]
    baseline = [math.sin(x) for x in xs]
    g = Graph(
        pallet,
        title="Replace whole series",
        x_label="seconds",
        y_label="amplitude",
        y_min=-1.4,
        y_max=1.4,
        graph_id="update-series",
    )
    g.add_series(xs, baseline, color="#22C55E", label="wave")
    g.add_series(xs, [0.35 * math.cos(x * 1.6) for x in xs], color="#F97316", label="reference", draw_markers=False)
    g.draw()

    for frame in range(32):
        phase = frame * 0.22
        updated = [math.sin(x + phase) * (0.75 + 0.25 * math.cos(phase)) for x in xs]
        g.set_series("wave", xs, updated)
        time.sleep(0.08)


def demo_live_append(pallet: Pallet) -> None:
    start_demo_page(pallet)
    start_points = 40
    end_points = 120
    xs = list(range(start_points))
    ys = [35 + 10 * math.sin(x * 0.24) for x in xs]
    g = Graph(
        pallet,
        title="Live append",
        x_label="sample",
        y_label="value",
        x_min=0,
        x_max=end_points - 1,
        y_min=10,
        y_max=65,
        graph_id="live-append",
    )
    g.add_series(xs, ys, color="#0EA5E9", label="sensor", draw_markers=False)
    g.draw()

    for step in range(start_points, end_points):
        next_y = 35 + 14 * math.sin(step * 0.24) + 5 * math.sin(step * 0.9)
        g.append_point("sensor", step, next_y, max_points=end_points, redraw_axes=False)
        time.sleep(0.05)


def demo_annotations(pallet: Pallet) -> None:
    start_demo_page(pallet)
    xs = [i * 0.25 for i in range(50)]
    ys = [45 + 18 * math.sin(x) + 6 * math.sin(x * 2.8) for x in xs]
    peak_index = max(range(len(ys)), key=lambda index: ys[index])
    g = Graph(
        pallet,
        title="Annotations",
        x_label="seconds",
        y_label="value",
        y_min=15,
        y_max=75,
    )
    g.add_y_span(58, 75, fill="rgba(248, 113, 113, 0.20)", text="warning")
    g.add_x_span(4.0, 5.5, fill="rgba(250, 204, 21, 0.22)", text="event")
    g.add_series(xs, ys, color="#2563EB", label="signal")
    g.add_hline(58, text="limit", color="#DC2626")
    g.add_vline(5.0, text="trigger", color="#A16207")
    g.add_point_label(xs[peak_index], ys[peak_index], "peak", color="#0F172A")
    g.draw()


def demo_heatmap(pallet: Pallet) -> None:
    start_demo_page(pallet)
    columns = 18
    rows = 12
    matrix = []
    for y in range(rows):
        row = []
        for x in range(columns):
            cx = (x - columns / 2) / columns
            cy = (y - rows / 2) / rows
            value = math.sin(x * 0.75) * math.cos(y * 0.65) + 2.4 * math.exp(-(cx * cx + cy * cy) * 18)
            row.append(value)
        matrix.append(row)

    g = Graph(
        pallet,
        title="Heatmap / matrix",
        x_label="column",
        y_label="row",
        x_min=0,
        x_max=columns,
        y_min=0,
        y_max=rows,
    )
    g.add_heatmap(
        matrix,
        color_map=["#F8FAFC", "#67E8F9", "#2563EB", "#7F1D1D"],
        label="intensity",
    )
    g.add_vline(columns / 2, text="mid", color="#111827")
    g.add_hline(rows / 2, color="#111827")
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


def demo_terminal_regions(pallet: Pallet) -> None:
    start_demo_page(pallet, "#E5E7EB")
    gap = max(16, min(pallet.width, pallet.height) // 36)
    left_w = max(320, (pallet.width - gap * 3) // 2)
    right_w = max(320, pallet.width - left_w - gap * 3)
    region_h = max(220, pallet.height - gap * 2)

    log = pallet.terminal_region(
        "system-log",
        x=gap,
        y=gap,
        width=left_w,
        height=region_h,
        title="System Log",
        background="#020617",
        color="#CBD5E1",
        border="#475569",
    )
    metrics = pallet.terminal_region(
        "metrics",
        x=gap * 2 + left_w,
        y=gap,
        width=right_w,
        height=region_h,
        title="Metrics",
        background="#111827",
        color="#E5E7EB",
        border="#374151",
    )

    events = [
        ("boot sequence started", "#93C5FD"),
        ("loading graph renderer", "#CBD5E1"),
        ("bridge connected on tcp/9000", "#86EFAC"),
        ("browser status received", "#86EFAC"),
        ("warming cache", "#FDE68A"),
        ("ready", "#86EFAC"),
    ]
    for index, (message, color) in enumerate(events, 1):
        log.writeln(f"{index:02d}: {message}", color=color)

    for index in range(18):
        cpu = 34 + round(18 * math.sin(index * 0.45))
        mem = 410 + index * 9
        metrics.writeln(f"sample={index:02d}  cpu={cpu:02d}%  mem={mem:04d} MB")

    log.writeln("")
    log.writeln("Long lines wrap inside the region without changing the rest of the canvas.", color="#C4B5FD")


def demo_graph_with_terminal(pallet: Pallet) -> None:
    start_demo_page(pallet, "#F8FAFC")
    gap = max(16, min(pallet.width, pallet.height) // 40)
    log_w = max(300, min(380, pallet.width // 3))
    graph_w = max(360, pallet.width - log_w - gap * 3)
    graph_h = max(260, pallet.height - gap * 2)

    xs = [i * 0.4 for i in range(36)]
    ys = [50 + 20 * math.sin(x) + 8 * math.sin(x * 2.7) for x in xs]
    Graph(
        pallet,
        x=gap,
        y=gap,
        width=graph_w,
        height=graph_h,
        title="Sensor Stream",
        x_label="sec",
        y_label="value",
        y_min=15,
        y_max=85,
    ).add_area_series(
        xs,
        ys,
        color="#BAE6FD",
        outline_color="#0284C7",
        label="sensor",
    ).draw()

    log = pallet.terminal_region(
        "stream-log",
        x=gap * 2 + graph_w,
        y=gap,
        width=log_w,
        height=graph_h,
        title="Stream Log",
        background="#0F172A",
        color="#E2E8F0",
        border="#334155",
    )

    for index, value in enumerate(ys[-20:], 1):
        color = "#FCA5A5" if value > 70 else "#86EFAC" if value < 35 else "#E2E8F0"
        label = "high" if value > 70 else "low" if value < 35 else "ok"
        log.writeln(f"{index:02d}  value={value:05.2f}  {label}", color=color)


def demo_gauges(pallet: Pallet) -> None:
    start_demo_page(pallet, "#EEF2F7")
    gap = max(14, min(pallet.width, pallet.height) // 42)
    top_h = max(210, (pallet.height - gap * 3) // 2)
    bottom_h = max(160, pallet.height - top_h - gap * 3)
    cell_w = max(220, (pallet.width - gap * 3) // 2)
    right_x = gap * 2 + cell_w
    bottom_y = gap * 2 + top_h
    thresholds = [(70, "#F59E0B"), (90, "#EF4444")]

    cool = GaugeStyle(fill_color="#0EA5E9", value_color="#0F172A")
    warm = GaugeStyle(fill_color="#22C55E", value_color="#0F172A")

    ArcGauge(
        pallet,
        x=gap,
        y=gap,
        width=cell_w,
        height=top_h,
        title="Arc Gauge",
        label="CPU load",
        value=76,
        units="%",
        style=cool,
        thresholds=thresholds,
    ).draw()

    CircularMeter(
        pallet,
        x=right_x,
        y=gap,
        width=cell_w,
        height=top_h,
        title="Circular Meter",
        label="Storage",
        value=63,
        units="%",
        style=warm,
        thresholds=[(80, "#F59E0B"), (95, "#EF4444")],
    ).draw()

    BarGauge(
        pallet,
        x=gap,
        y=bottom_y,
        width=cell_w,
        height=bottom_h,
        title="Bar Gauge",
        label="Tank level",
        value=58,
        units="%",
        style=GaugeStyle(fill_color="#14B8A6"),
        thresholds=[(75, "#F59E0B"), (92, "#EF4444")],
    ).draw()

    BarGauge(
        pallet,
        x=right_x,
        y=bottom_y,
        width=cell_w,
        height=bottom_h,
        title="Vertical Meter",
        label="Pressure",
        value=132,
        minimum=0,
        maximum=180,
        units=" psi",
        orientation="vertical",
        style=GaugeStyle(fill_color="#8B5CF6"),
        thresholds=[(120, "#F59E0B"), (155, "#EF4444")],
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
    (18, "Terminal regions", demo_terminal_regions),
    (19, "Graph + terminal log", demo_graph_with_terminal),
    (20, "Gauges and meters", demo_gauges),
    (21, "Update one point", demo_update_point),
    (22, "Replace whole series", demo_update_series),
    (23, "Histogram", demo_histogram),
    (24, "Live append helper", demo_live_append),
    (25, "Annotations", demo_annotations),
    (26, "Heatmap / matrix", demo_heatmap),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Pallet graph examples")
    parser.add_argument("host", nargs="?", default=None, help="bridge TCP host, kept for compatibility")
    parser.add_argument("--bridge-host", default=DEFAULT_BRIDGE_HOST, help="bridge TCP host or IP address")
    parser.add_argument("--bridge-port", type=int, default=DEFAULT_BRIDGE_PORT, help="bridge TCP port")
    parser.add_argument("--port", type=int, default=None, help="alias for --bridge-port")
    parser.add_argument("--width", type=int, default=None, help="override browser-reported CSS drawing width")
    parser.add_argument("--height", type=int, default=None, help="override browser-reported CSS drawing height")
    parser.add_argument("--page", default=None, help="pallet page to draw on")
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
            page=args.page,
        ) as pallet:
            print_pallet_size_info(pallet)
            for index, (number, name, draw) in enumerate(to_run, 1):
                print(f"[{index}/{len(to_run)}] Demo {number}: {name}")
                draw(pallet)
                if index < len(to_run):
                    time.sleep(args.pause)
    except Exception as exc:
        print(f"Failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
