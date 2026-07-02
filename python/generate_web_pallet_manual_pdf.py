#!/usr/bin/env python3
"""Generate the Web Pallet feature manual as a PDF."""
from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "pdf" / "web_pallet_manual.pdf"
TITLE = "Web Pallet Manual"
SUBTITLE = "Bridge-driven graphics, dashboards, terminals, and ECharts"


def wrap_text(text: str, font: str, size: int, max_width: float) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = word if not current else f"{current} {word}"
        if pdfmetrics.stringWidth(test, font, size) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def clean(text: str) -> str:
    return dedent(text).strip()


def p(*items: str) -> list[dict[str, str]]:
    return [{"kind": "p", "text": clean(item)} for item in items if clean(item)]


def bullets(*items: str) -> list[dict[str, str]]:
    return [{"kind": "bullet", "text": clean(item)} for item in items]


def code(text: str) -> list[dict[str, str]]:
    return [{"kind": "code", "text": dedent(text).strip("\n")}]


def callout(text: str) -> list[dict[str, str]]:
    return [{"kind": "callout", "text": clean(text)}]


def page(title: str, blocks: list[dict[str, str]], chapter: str = "") -> dict[str, object]:
    return {"title": title, "chapter": chapter, "blocks": blocks}


def draw_wrapped(
    c: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    width: float,
    *,
    font: str = "Helvetica",
    size: int = 9,
    leading: float = 12,
    color: colors.Color = colors.HexColor("#1F2937"),
) -> float:
    c.setFillColor(color)
    c.setFont(font, size)
    for line in wrap_text(text, font, size, width):
        c.drawString(x, y, line)
        y -= leading
    return y


def draw_code(c: canvas.Canvas, text: str, x: float, y: float, width: float) -> float:
    font = "Courier"
    size = 7.4
    leading = 9.3
    lines: list[str] = []
    for raw in text.splitlines():
        if not raw:
            lines.append("")
            continue
        lines.extend(wrap_text(raw, font, size, width - 16) or [""])
    height = max(22, 13 + leading * len(lines))
    c.setFillColor(colors.HexColor("#F8FAFC"))
    c.roundRect(x, y - height + 5, width, height, 5, stroke=0, fill=1)
    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.roundRect(x, y - height + 5, width, height, 5, stroke=1, fill=0)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.setFont(font, size)
    yy = y - 10
    for line in lines:
        c.drawString(x + 8, yy, line)
        yy -= leading
    return y - height - 7


def draw_callout(c: canvas.Canvas, text: str, x: float, y: float, width: float) -> float:
    lines = wrap_text(text, "Helvetica", 8.6, width - 20)
    height = 16 + 11.5 * len(lines)
    c.setFillColor(colors.HexColor("#ECFEFF"))
    c.roundRect(x, y - height + 5, width, height, 5, stroke=0, fill=1)
    c.setStrokeColor(colors.HexColor("#67E8F9"))
    c.roundRect(x, y - height + 5, width, height, 5, stroke=1, fill=0)
    c.setFillColor(colors.HexColor("#155E75"))
    c.setFont("Helvetica-Bold", 8.6)
    yy = y - 10
    for line in lines:
        c.drawString(x + 10, yy, line)
        yy -= 11.5
    return y - height - 8


def draw_header_footer(c: canvas.Canvas, page_num: int, page_title: str, chapter: str) -> None:
    w, h = letter
    c.setFillColor(colors.HexColor("#0F172A"))
    c.rect(0, h - 38, w, 38, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(42, h - 24, TITLE)
    c.setFont("Helvetica", 8)
    c.drawRightString(w - 42, h - 24, chapter or page_title)
    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.line(42, 42, w - 42, 42)
    c.setFillColor(colors.HexColor("#64748B"))
    c.setFont("Helvetica", 8)
    c.drawString(42, 28, "Generated from the Web Pallet workspace")
    c.drawRightString(w - 42, 28, f"{page_num}")


def draw_normal_page(c: canvas.Canvas, item: dict[str, object], num: int) -> None:
    w, h = letter
    chapter = str(item.get("chapter") or "")
    title = str(item["title"])
    draw_header_footer(c, num, title, chapter)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.setFont("Helvetica-Bold", 20)
    c.drawString(42, h - 76, title)
    if chapter:
        c.setFillColor(colors.HexColor("#0E7490"))
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(42, h - 91, chapter.upper())
    y = h - 116
    x = 54
    width = w - 108
    for block in item["blocks"]:  # type: ignore[index]
        kind = block["kind"]
        text = block["text"]
        if kind == "p":
            y = draw_wrapped(c, text, x, y, width, size=9.2, leading=12.5)
            y -= 5
        elif kind == "bullet":
            c.setFillColor(colors.HexColor("#0E7490"))
            c.circle(x + 2.5, y + 3, 2, stroke=0, fill=1)
            y = draw_wrapped(c, text, x + 13, y, width - 13, size=8.9, leading=11.8)
            y -= 3
        elif kind == "code":
            y = draw_code(c, text, x, y, width)
        elif kind == "callout":
            y = draw_callout(c, text, x, y, width)
        if y < 72:
            c.setFillColor(colors.HexColor("#B91C1C"))
            c.setFont("Helvetica-Bold", 7)
            c.drawRightString(w - 42, 56, "Continued in the next related section.")
            break
    c.showPage()


def toc_blocks() -> list[dict[str, str]]:
    entries = [
        "1-4 Orientation and setup",
        "5-13 Architecture, bridge behavior, and drawing basics",
        "14-22 UI overlays, cards, controls, events, and tables",
        "23-35 Canvas graph library: axes, series, charts, gauges, and live updates",
        "36-45 Apache ECharts: raw options, helpers, builders, and live dashboards",
        "46-53 Operations: CLI, reconnects, protocol, troubleshooting, performance, and security",
        "54-60 Extension patterns, API references, glossary, and release checklist",
    ]
    return p(
        "This manual is a practical field guide for building with Web Pallet. It explains how the browser, bridge, Python clients, drawing API, UI layer, graph library, terminal regions, and ECharts helper layer fit together."
    ) + bullets(*entries) + callout(
        "The examples assume you run commands from the repository root and open pallet.html in a browser connected to ws://localhost:8080."
    )


PAGES: list[dict[str, object]] = [
    page(
        "Cover",
        p(
            "Web Pallet is a browser-backed drawing and dashboard surface driven from Python or C++ through a local bridge. It is useful for quick visualization, live telemetry, demos, terminal panes, and lightweight operator dashboards.",
            "This manual covers the bridge, the Python client, canvas drawing primitives, UI cards and controls, terminal regions, the Pallet graph library, Apache ECharts support, live updates, replay behavior, and extension patterns.",
        )
        + callout("Output file: output/pdf/web_pallet_manual.pdf"),
        "Orientation",
    ),
    page("How To Use This Manual", toc_blocks(), "Orientation"),
    page(
        "Core Concepts",
        p(
            "Web Pallet has three cooperating pieces: a browser page, a bridge process, and one or more clients. The browser renders commands. The bridge relays commands and keeps compact reconnect state. Clients send drawing, UI, terminal, and chart commands.",
            "The usual Python entry point is Pallet.for_bridge() from python/pallet.py. Canvas charts use python/pallet_graph_lib.py. Apache ECharts dashboards use python/echarts_graph_lib.py."
        )
        + bullets(
            "pallet.html is the visual surface and loads the browser renderer.",
            "python/bridge.py accepts TCP clients and browser WebSocket clients.",
            "python/pallet.py is the general command client.",
            "python/pallet_graph_lib.py adds immediate-mode charts and gauges.",
            "python/echarts_graph_lib.py adds browser-native ECharts charts."
        ),
        "Orientation",
    ),
    page(
        "Quick Start",
        p("Start the bridge, open the browser surface, connect the page, then run a Python client.")
        + code(
            """
            python python/bridge.py
            # Open pallet.html in a browser.
            # Connect the browser to ws://localhost:8080.
            python python/pallet_graph_examples.py --demo 1
            """
        )
        + p(
            "By default the bridge uses TCP port 9000 for drawing clients and WebSocket port 8080 for browser clients. Python examples also accept --bridge-host, --bridge-port, --width, --height, and sometimes --page."
        )
        + callout("Use PALLET_BRIDGE_HOST and PALLET_BRIDGE_PORT to set Python defaults without changing scripts."),
        "Orientation",
    ),
]


def add_runtime_pages() -> None:
    data = [
        ("Browser Surface", "pallet.html loads the renderer, creates the canvas and HTML overlay layers, loads ECharts from the configured CDN, and maintains pages, cards, controls, tables, terminal regions, and chart hosts.", [
            "The browser reports its drawing size during handshake.",
            "Canvas commands draw immediately on the active page.",
            "HTML overlay commands create DOM widgets over the drawing surface.",
            "Chart commands create ECharts hosts that resize independently."
        ], None),
        ("Bridge Process", "The bridge is the traffic controller. Python or C++ clients connect over TCP and browsers connect over WebSocket. The bridge forwards commands, tracks browser status, and can replay compact state to reconnecting browser pages.", [
            "Run python/bridge.py for the Python bridge.",
            "The cpp/bridge.cpp source provides a native bridge implementation.",
            "Use --no-replay-on-connect when replay is not wanted.",
            "Use status commands to inspect web client counts and screen metadata."
        ], None),
        ("Python Client Lifecycle", "A Pallet object owns a TCP connection to the bridge. Use it as a context manager for short scripts or call connect() and close() explicitly for long-running processes.", [], """
            from pallet import Pallet

            with Pallet.for_bridge("127.0.0.1") as pallet:
                pallet.clear("#F8FAFC")
                pallet.text(30, 40, "Hello, Web Pallet")
            """),
        ("Pages And Groups", "Pages let you keep multiple dashboards alive and switch which one the browser shows. Groups let you replace a logical set of commands together, which is especially useful for panels that are rebuilt from scratch.", [
            "set_page(page) sets default page metadata on following commands.",
            "show_page(page) changes the visible browser page.",
            "replace_group(group, commands) swaps a group atomically.",
            "coalesce_group(group) captures commands and replaces the group."
        ], None),
        ("Batches And Metadata", "The Python client can batch commands and attach metadata such as page or group. Batching reduces round trips and keeps related commands ordered.", [], """
            pallet.begin_batch()
            pallet.fill_rect(20, 20, 200, 120, "#DBEAFE")
            pallet.text(36, 58, "Batched")
            pallet.end_batch()

            with pallet.command_metadata(page="demo", group="panel"):
                pallet.fill_rect(20, 20, 240, 140, "#F8FAFC")
            """),
        ("Reconnect Replay", "When replay is enabled, the bridge stores a compact representation of current state. It coalesces high-frequency updates so reconnecting browsers do not receive stale frames.", [
            "clear commands reset replay state for a page.",
            "chart_option with coalesce=True replaces earlier chart options for the same chart.",
            "UI updates and table updates are coalesced by target id.",
            "Page, chart, UI, terminal, and group deletes remove obsolete replay entries."
        ], None),
        ("Coordinates And Sizing", "Canvas coordinates are pixel-like drawing units relative to the browser surface. Most APIs accept x, y, width, and height. If width and height are omitted in Pallet.for_bridge(), the client uses the browser-reported drawing size.", [
            "Keep chart rectangles large enough for labels and legends.",
            "Reserve padding for HTML overlay cards and table filters.",
            "Use fixed dimensions for dashboard regions that should not jump.",
            "For multi-page dashboards, reuse consistent coordinates across pages."
        ], None),
        ("Drawing Primitives", "The core Pallet API exposes immediate-mode primitives for lines, rectangles, circles, arcs, filled shapes, text, and paths. These commands are intentionally small and composable.", [], """
            pallet.clear("#FFFFFF")
            pallet.line(30, 30, 260, 70, "#2563EB", 4)
            pallet.rect(30, 100, 180, 90, "#0F172A", 2)
            pallet.fill_circle(310, 145, 45, "#F97316")
            pallet.arc(440, 145, 55, 20, 300, "#059669", 8)
            pallet.text(30, 230, "Immediate drawing", color="#0F172A", size=2)
            """),
        ("Paths And Stroke Style", "path() is the flexible primitive for polylines and shapes. It supports line caps, joins, and dash arrays. Use it when line(), rect(), and arc() are too limited.", [], """
            pallet.path(
                [(40, 60), (140, 20), (240, 90), (340, 35)],
                color="#DC2626",
                width=4,
                line_cap="round",
                line_join="round",
                dash=[10, 6],
            )
            """),
        ("Text And Color", "The browser accepts CSS color strings, including named colors, hex values, and rgba() values. Text uses a size scale rather than point sizes, so keep labels concise and test on the target display.", [
            "Prefer high-contrast colors for operator dashboards.",
            "Use rgba() fills for annotation bands and translucent overlays.",
            "Use concise labels inside small cards and chart regions.",
            "Avoid relying on long strings in fixed-width controls."
        ], None),
    ]
    for title, text, items, snippet in data:
        blocks = p(text) + bullets(*items)
        if snippet:
            blocks += code(snippet)
        PAGES.append(page(title, blocks, "Runtime And Drawing"))


def add_ui_pages() -> None:
    data = [
        ("Terminal Regions", "Terminal regions are scrollable text panes rendered in the browser. They are useful for logs, subprocess output, status streams, and mixed graph-plus-console demonstrations.", [], """
            term = pallet.terminal_region(
                "log",
                x=24, y=420, width=760, height=180,
                title="Worker log",
            )
            term.writeln("started", color="#16A34A")
            term.write("waiting for samples...")
            """),
        ("Pipe Terminal Example", "python/pallet_pipe_terminal.py runs a command and streams its output into a terminal region. Use it to make command-line tools visible beside charts or UI controls.", [
            "Use --command to select the program to run.",
            "Use --region-id when multiple terminals share a page.",
            "Clear terminal output before a new run when old lines are not useful.",
            "Keep terminal panes tall enough for wrapped output."
        ], None),
        ("Responsive Grids", "The UI overlay can define grids that hold cards. A grid arranges cards into columns with gap and padding values, then adapts when the browser gets narrower.", [], """
            pallet.define_grid(
                "dashboard",
                columns=3,
                min_column_width=280,
                gap=16,
                padding=16,
            )
            """),
        ("Cards", "Cards are named containers in a grid. They can hold controls, status widgets, tables, and ECharts charts. Use cards for repeated dashboard panels and grouped controls.", [], """
            pallet.define_card("controls", grid="dashboard", title="Controls")
            pallet.define_card(
                "results",
                grid="dashboard",
                title="Results",
                column_span=2,
            )
            """),
        ("Controls", "Supported controls include button, toggle, slider, select, text, and number. Controls emit browser events and can be updated from Python without rebuilding the card.", [], """
            level = pallet.control(
                "level",
                card="controls",
                kind="slider",
                label="Level",
                value=50,
                minimum=0,
                maximum=100,
                step=1,
                live=True,
            )
            level.set(75)
            """),
        ("Control Events", "Callbacks run when your client polls events. Sliders with live=True emit input events while moving; other controls usually emit change events after a value is committed. Buttons emit click events.", [], """
            def changed(event):
                print(event["id"], event["event"], event.get("value"))

            pallet.on_ui_event("*", changed)
            while True:
                event = pallet.poll_event(timeout=1.0)
            """),
        ("Status Widgets", "Status widgets provide compact dashboard signals. Available kinds are badge, led, progress, kpi, alert, and spinner. Semantic states include info, success, warning, danger, and neutral.", [], """
            load = pallet.status_widget(
                "load",
                card="results",
                kind="progress",
                label="CPU",
                value=42,
                units="%",
                minimum=0,
                maximum=100,
            )
            load.set(87, status="warning")
            """),
        ("Data Tables", "Tables support keyed rows, live upserts, sorting, optional filtering, row selection, and row-click events. They are useful for recent samples, device lists, alerts, or audit trails.", [], """
            table = pallet.table(
                "sensors",
                [{"key": "id", "label": "#", "align": "right"},
                 {"key": "name", "label": "Sensor"},
                 {"key": "value", "label": "Value", "align": "right"}],
                card="results",
                key_field="id",
                filterable=True,
                selectable=True,
            )
            table.upsert({"id": 1, "name": "A", "value": 43.7})
            """),
        ("Dashboard Patterns", "A durable dashboard separates visual regions, control state, and update loops. Define grids and cards once, create widgets and charts once, then update values and series in place.", [
            "Give every widget, table, terminal, and chart a stable id.",
            "Use pages for major views and cards for local grouping.",
            "Use coalesced updates for streams faster than a few frames per second.",
            "Keep control callbacks small; push heavy work into the main loop."
        ], None),
    ]
    for title, text, items, snippet in data:
        blocks = p(text) + bullets(*items)
        if snippet:
            blocks += code(snippet)
        PAGES.append(page(title, blocks, "UI And Terminals"))


def add_graph_pages() -> None:
    data = [
        ("Graph Library Overview", "pallet_graph_lib.py builds charts by issuing canvas commands through Pallet. It is well suited for deterministic, script-driven visuals that should share the same immediate drawing model as other canvas primitives.", [
            "Graph handles numeric, datetime, log, and dual-y axes.",
            "Series include line, scatter, bar, histogram, area, confidence band, and heatmap.",
            "Other classes include ArcGauge, BarGauge, CircularMeter, and RadarChart.",
            "Graph updates can replace points or series without rebuilding every object."
        ], None),
        ("Graph Quick Start", "Create a Graph, add one or more series, then call draw(). The graph computes ranges, ticks, margins, labels, grid lines, legend placement, and data mapping.", [], """
            import math
            from pallet import Pallet
            from pallet_graph_lib import Graph

            xs = [index * 0.2 for index in range(40)]
            with Pallet.for_bridge("127.0.0.1") as pallet:
                graph = Graph(pallet, title="Sine", x_label="x", y_label="y")
                graph.add_series(xs, [math.sin(x) for x in xs], label="sin")
                graph.draw()
            """),
        ("Axes And Ticks", "Graph chooses rounded bounds and readable intervals using 1, 2, 2.5, and 5 style tick steps. Tick density adapts to available pixel space to reduce label collisions.", [
            "Set x_min, x_max, y_min, and y_max for explicit ranges.",
            "Use y2_label and y_axis=2 for dual-y charts.",
            "Use grid_x and grid_y in GraphStyle to influence target interval counts.",
            "Ensure graph rectangles leave enough space for title, labels, and legend."
        ], None),
        ("Datetime And Log Axes", "Datetime x values are accepted as date or datetime objects. Naive datetimes are interpreted as UTC. Logarithmic x and y axes can be enabled independently, but log values must be positive.", [], """
            from datetime import datetime, timedelta, timezone

            start = datetime(2026, 6, 19, 8, tzinfo=timezone.utc)
            times = [start + timedelta(minutes=30 * i) for i in range(12)]

            graph = Graph(pallet, title="History", x_label="UTC")
            graph.add_series(times, values, label="sensor")
            graph.draw()
            """),
        ("Lines And Scatter", "add_series() supports line charts, scatter charts, or both. Use draw_line and draw_markers to select the visual mode. Use marker_radius, color, label, and line_width for presentation.", [], """
            graph.add_series(
                xs,
                ys,
                label="samples",
                color="#2563EB",
                draw_line=True,
                draw_markers=True,
                marker_radius=4,
            )
            """),
        ("Line Styles And Splines", "Named line styles are solid, dashed, dotted, and dashdot. You can also supply a custom dash_pattern. Spline fitting draws a smooth interpolating curve while markers remain at original samples.", [], """
            graph.add_series(
                xs,
                ys,
                label="estimate",
                draw_markers=False,
                line_style="dashdot",
                line_cap="round",
                spline=True,
                spline_resolution=16,
            )
            """),
        ("Gaps And Confidence Bands", "Use None or NaN for intentional missing values. Lines, splines, areas, and confidence bands do not connect across missing samples. Confidence bands take lower and upper arrays for each x coordinate.", [], """
            graph.add_confidence_band(
                xs,
                lower,
                upper,
                label="95% interval",
                fill="rgba(56, 189, 248, 0.20)",
            )
            graph.add_series(xs, mean, label="estimate", draw_markers=False)
            """),
        ("Bars And Histograms", "Bar series can be grouped or stacked. Series with the same stack name accumulate; different stacks form side-by-side groups. Histograms can use an integer bin count or explicit bin edges.", [], """
            graph.add_bar_series(quarters, retail_a, label="A retail", stack="A")
            graph.add_bar_series(quarters, online_a, label="A online", stack="A")
            graph.add_histogram(samples, bins=20, value_range=(-4, 4))
            graph.draw()
            """),
        ("Areas And Heatmaps", "Area series fill below a line and can be stacked by giving them the same stack name. Heatmaps accept a matrix plus optional x and y edges and a color map.", [], """
            graph.add_area_series(xs, received, label="RX", stack="traffic")
            graph.add_area_series(xs, transmitted, label="TX", stack="traffic")

            graph.add_heatmap(matrix, color_map=["#F8FAFC", "#67E8F9", "#2563EB"])
            """),
        ("Radar And Polar Charts", "RadarChart is an alias of PolarChart. It expects at least three categories and one or more series. Use minimum, maximum, levels, and start_angle to shape the scale.", [], """
            from pallet_graph_lib import RadarChart

            chart = RadarChart(pallet, ["Speed", "Range", "Comfort"], maximum=10)
            chart.add_series([8, 6, 7], label="Model A", fill="rgba(37,99,235,0.18)")
            chart.draw()
            """),
        ("Canvas Gauges", "The canvas graph library includes ArcGauge, CircularMeter, and BarGauge. Use GaugeStyle for reusable colors, labels, units, thresholds, and ticks.", [], """
            from pallet_graph_lib import ArcGauge, GaugeStyle

            ArcGauge(
                pallet,
                value=76,
                minimum=0,
                maximum=100,
                title="CPU",
                units="%",
                style=GaugeStyle(fill_color="#0EA5E9"),
            ).draw()
            """),
        ("Annotations", "Annotations are chainable and render with the graph. Use spans for regions, hline and vline for limits and events, and point labels for individual values.", [], """
            graph.add_y_span(70, 100, fill="rgba(248,113,113,0.20)", text="warning")
            graph.add_x_span(4, 6, fill="rgba(250,204,21,0.22)", text="event")
            graph.add_hline(70, text="limit", color="#DC2626")
            graph.add_point_label(8, 82, "peak")
            """),
        ("Live Canvas Updates", "Label series uniquely when updating by name. Update methods accept redraw_axes='auto', True, or False. Auto redraws axes only when the calculated range changes.", [], """
            graph.set_point("sensor", 4, y=27.5)
            graph.append_point("sensor", 20, 31.2, max_points=100)
            graph.append_points("sensor", [21, 22], [30.8, 29.7])
            graph.shift_series("sensor", dx=1)
            graph.trim_series("sensor", 50)
            """),
    ]
    for title, text, items, snippet in data:
        blocks = p(text) + bullets(*items)
        if snippet:
            blocks += code(snippet)
        PAGES.append(page(title, blocks, "Canvas Graphs"))


def add_echarts_pages() -> None:
    data = [
        ("ECharts Overview", "Apache ECharts support is implemented in echarts_graph_lib.py. It is the best choice when you want browser-native tooltips, legends, data zoom, animated setOption updates, and chart types that ECharts already implements well.", [
            "Use high-level helpers for common chart families.",
            "Use builders for structured multi-axis line charts.",
            "Use raw chart() when you need the complete ECharts option model.",
            "Use ChartHandle methods for incremental updates."
        ], None),
        ("ECharts Quick Start", "Create an EChartsPallet, start it, clear a page, define a chart, show the page, and keep the process alive while the browser displays it.", [], """
            from echarts_graph_lib import EChartsPallet

            pallet = EChartsPallet()
            pallet.start()
            pallet.clear(page="echarts")
            pallet.line_chart(
                id="temperature",
                x=24, y=24, width=720, height=360,
                x_data=["08:00", "09:00", "10:00"],
                y_data=[72.1, 72.8, 73.4],
                title="Temperature",
                smooth=True,
                page="echarts",
            )
            pallet.show_page("echarts")
            """),
        ("Raw ECharts Options", "chart() sends a normal ECharts option dictionary to the browser. This is the escape hatch for chart types, plugins, axes, labels, tooltip formatters, or visual maps not wrapped by helper methods.", [], """
            handle = pallet.chart(
                id="raw-bars",
                x=20, y=20, width=640, height=360,
                option={
                    "tooltip": {"trigger": "axis"},
                    "xAxis": {"type": "category", "data": ["A", "B", "C"]},
                    "yAxis": {"type": "value"},
                    "series": [{"type": "bar", "data": [12, 19, 8]}],
                },
            )
            """),
        ("ChartHandle Updates", "Every ECharts chart returns a ChartHandle. The handle remembers the chart id and page, so update calls can stay concise. Use coalesce=True for high-frequency set_option loops.", [], """
            handle.set_option(
                {"series": [{"name": "Signal", "data": values}]},
                coalesce=True,
            )
            handle.set_data([{"value": 82, "name": "Load"}])
            handle.append_data([[5, 17]])
            handle.resize(width=800, height=420)
            handle.remove()
            """),
        ("High-level ECharts Helpers", "The base helpers cover line_chart, bar_chart, pie_chart, gauge, and update_gauge. They build practical defaults for axes, grid, legends, labels, tooltips, and series data.", [], """
            pallet.bar_chart(
                id="utilization",
                x=20, y=20, width=420, height=300,
                categories=["CPU", "RAM", "Disk"],
                values=[65, 72, 54],
                horizontal=True,
                series_name="Percent",
            )
            """),
        ("Gallery-style Helpers", "Additional helpers mirror common ECharts gallery patterns: progress_gauge, multi_ring_gauge, stacked_line_chart, area_line_chart, stepped_line_chart, bar_race_chart, doughnut_chart, rose_pie_chart, bubble_scatter_chart, heatmap_chart, radar_chart, candlestick_chart, funnel_chart, and treemap_chart.", [
            "Use extra_option when helper defaults need small overrides.",
            "Use raw chart() when the data model differs from the helper.",
            "Keep ids stable so reconnect replay and later updates target the same chart.",
            "Prefer helper methods for prototypes, then drop to raw options only where needed."
        ], None),
        ("Multi-axis Builder", "multi_axis_line_chart() hides ECharts axis indexes. Add named axes, attach named line series to those axes, then render. It is ideal for dashboards with top and bottom x axes or left and right y axes.", [], """
            chart = pallet.multi_axis_line_chart(
                id="plant", x=20, y=20, width=760, height=420,
                title="Plant telemetry", data_zoom=True,
            )
            chart.add_x_axis("Time", data=["0s", "1s"], position="bottom")
            chart.add_y_axis("Temperature", units="deg F", position="left")
            chart.add_line("Temperature", [72.0, 72.5], x_axis="Time", y_axis="Temperature")
            handle = chart.render()
            """),
        ("Two X / Two Y Helper", "line_chart_2x2y() is a compact helper for the common chart with bottom and top x axes plus left and right y axes. It returns a ChartHandle and can enable dataZoom.", [], """
            handle = pallet.line_chart_2x2y(
                id="dual", x=20, y=20, width=700, height=420,
                title="Two X / Two Y",
                bottom_x=["0s", "1s"], top_x=[0, 1],
                left_series=[72.0, 72.4],
                right_series=[3.20, 3.22],
                left_y_name="Temperature",
                right_y_name="Voltage",
                data_zoom=True,
            )
            """),
        ("Live Time Charts", "live_time_chart() creates a rolling time-series chart. It accepts a mapping from series name to ECharts series kind, appends timestamped values, and coalesces browser updates automatically.", [], """
            from datetime import datetime, timezone

            live = pallet.live_time_chart(
                id="live",
                x=20, y=20, width=720, height=360,
                series={"Actual": "line", "Target": "bar"},
                max_points=60,
            )
            live.append(datetime.now(timezone.utc), {"Actual": 42.5, "Target": 40.0})
            """),
        ("ECharts In Cards", "ECharts charts can be positioned directly or hosted inside UI cards. When using cards, the card owns the browser layout while the chart still uses the id, page, and update APIs from EChartsPallet.", [], """
            pallet.define_grid("dashboard", columns=2, gap=16, padding=16, page="dash")
            pallet.define_card("left", grid="dashboard", title="Production", page="dash")
            pallet.line_chart(
                id="production",
                x=0, y=0, width=480, height=300,
                x_data=["A", "B", "C"],
                y_data=[10, 14, 12],
                card="left",
                page="dash",
            )
            """),
    ]
    for title, text, items, snippet in data:
        blocks = p(text) + bullets(*items)
        if snippet:
            blocks += code(snippet)
        PAGES.append(page(title, blocks, "Apache ECharts"))


def add_operations_pages() -> None:
    data = [
        ("Example Programs", "The repository includes runnable examples that exercise the feature set. Use them as smoke tests and as copyable starting points.", [
            "python/pallet_graph_examples.py lists and runs canvas graph demos.",
            "python/pallet_ui_examples.py demonstrates grids, cards, controls, status widgets, and tables.",
            "python/echarts_examples.py shows gallery-style ECharts helpers.",
            "python/echarts_multi_axis_api.py shows the multi-axis builder.",
            "python/echarts_live_line_coalesce.py shows fast coalesced updates.",
            "python/echarts_live_grouped_bar.py is a larger live dashboard example."
        ], None),
        ("Bridge CLI", "The bridge accepts command-line options for host, TCP port, WebSocket port, and reconnect replay behavior. Use explicit ports when running multiple bridge instances.", [], """
            python python/bridge.py --tcp-host 127.0.0.1 --tcp-port 9000 --ws-port 8080
            python python/bridge.py --no-replay-on-connect
            python python/bridge.py --replay-on-connect
            """),
        ("Environment Defaults", "pallet.py reads PALLET_BRIDGE_HOST and PALLET_BRIDGE_PORT for default Python connection values. Command-line examples usually expose --bridge-host, --bridge-port, and --port as an alias.", [], """
            $env:PALLET_BRIDGE_HOST = "127.0.0.1"
            $env:PALLET_BRIDGE_PORT = "9000"
            python python/echarts_examples.py
            """),
        ("Command Protocol", "At the lowest level, clients send JSON command objects. The Pallet class wraps this protocol, but command() and commands() remain available for custom integrations.", [
            "Drawing commands include clear, line, rect, fill_rect, circle, arc, text, and path.",
            "UI commands include ui_grid, ui_card, ui_control, ui_status, and ui_table.",
            "Terminal commands define, write to, and clear terminal regions.",
            "Chart commands define charts, set options, update data, append data, resize, and remove."
        ], None),
        ("Troubleshooting Connections", "Most connection issues come from the bridge not running, the browser not connected to the WebSocket URL, port mismatches, or a firewall blocking local sockets.", [
            "Confirm python/bridge.py is running.",
            "Confirm pallet.html is connected to ws://localhost:8080.",
            "Confirm Python clients are using the bridge TCP port, usually 9000.",
            "Call pallet.status() or check EChartsPallet.client_count when debugging.",
            "If the browser reloads, rely on replay or rerun the client script."
        ], None),
        ("Performance Guidelines", "Use the smallest update that expresses the change. Avoid full redraws for high-frequency streams when a set_data, set_option, or table upsert is enough.", [
            "Use coalesce=True for rapid ECharts set_option updates.",
            "Use Graph append and set methods instead of rebuilding large graphs where possible.",
            "Batch related canvas commands.",
            "Keep tables bounded with max_rows for long-running dashboards.",
            "Use pages to isolate heavy dashboards that do not need to be visible."
        ], None),
        ("Visual Design Guidelines", "Web Pallet dashboards work best when they are dense but calm. Use strong hierarchy, stable coordinates, concise labels, and consistent colors. Reserve bright colors for status changes and alerts.", [
            "Give controls and charts predictable positions.",
            "Avoid tiny chart rectangles with long axis labels.",
            "Use semantic status colors consistently.",
            "Keep terminal panes and tables readable at the target display size.",
            "Use ECharts dataZoom when the user needs to inspect a long series."
        ], None),
        ("Network And Safety", "Web Pallet is typically a local development and operator-display tool. Treat the bridge as a command surface: anyone who can connect to it can draw, define UI, and stream terminal text.", [
            "Bind to localhost unless remote clients are required.",
            "Be careful exposing bridge ports on shared networks.",
            "Do not stream secrets into terminal regions or tables.",
            "Review raw script_load usage before loading external scripts.",
            "Prefer explicit host and port settings in shared demos."
        ], None),
    ]
    for title, text, items, snippet in data:
        blocks = p(text) + bullets(*items)
        if snippet:
            blocks += code(snippet)
        PAGES.append(page(title, blocks, "Operations"))


def add_extension_reference_pages() -> None:
    data = [
        ("Extending Web Pallet", "Extension work usually starts in one of three places: a new Python helper that emits existing commands, a new browser command handler in pallet.html, or a new bridge coalescing rule for replay state.", [
            "Start with Python helpers when the browser can already render the needed primitive.",
            "Add browser handlers when a new visual or DOM capability is required.",
            "Add bridge memory rules when reconnect replay should preserve only compact state.",
            "Keep command payloads JSON-serializable and stable."
        ], None),
        ("Adding A Chart Helper", "A good helper hides repetitive option structure but leaves an escape hatch. Follow the ECharts helpers: accept clear Python data, build a normal option dictionary, merge extra_option, and return ChartHandle.", [], """
            def my_chart(pallet, *, id, x, y, width, height, data, extra_option=None):
                option = {
                    "tooltip": {"trigger": "item"},
                    "series": [{"type": "pie", "data": list(data)}],
                }
                option.update(extra_option or {})
                return pallet.chart(id=id, x=x, y=y, width=width, height=height, option=option)
            """),
        ("Testing Checklist", "Before sharing a dashboard or demo, run a browser smoke test and verify the reconnect path. Reload the browser after the script has drawn its state and confirm the bridge replays the expected current view.", [
            "Run the relevant example script from the repository root.",
            "Open pallet.html and connect to ws://localhost:8080.",
            "Check visible layout at the target browser size.",
            "Interact with controls and verify event callbacks.",
            "Reload the browser to check replay behavior.",
            "Stop the client and bridge cleanly."
        ], None),
        ("Pallet API Reference", "The general Pallet API covers lifecycle, raw commands, pages, batching, UI, tables, terminals, and drawing primitives.", [
            "Lifecycle: for_bridge, connect, close, status, command, commands.",
            "Metadata: command_metadata, capture_commands, coalesce_group, replace_group.",
            "Pages: set_page, show_page.",
            "Events: subscribe_events, on_ui_event, poll_event, run_event_loop.",
            "UI: define_grid, define_card, control, update_control, status_widget, table.",
            "Terminal: terminal_region, write_terminal, clear_terminal.",
            "Drawing: clear, fill_screen, line, hline, vline, rect, fill_rect, circle, fill_circle, arc, text, path."
        ], None),
        ("Graph API Reference", "The canvas graph library centers on Graph, GraphStyle, GaugeStyle, PolarChart, RadarChart, ArcGauge, BarGauge, and CircularMeter.", [
            "Series: add_series, add_bar_series, add_histogram, add_area_series, add_confidence_band, add_heatmap.",
            "Annotations: add_vline, add_hline, add_x_span, add_y_span, add_point_label.",
            "Updates: set_series, set_confidence_band, set_point, append_point, append_points, shift_series, trim_series.",
            "Styling: GraphStyle controls backgrounds, axes, grids, labels, title colors, tick targets, and palette behavior.",
            "Gauges: GaugeStyle plus thresholds, labels, units, bounds, and orientation."
        ], None),
        ("ECharts API Reference", "The ECharts layer centers on EChartsPallet, ChartHandle, LiveTimeChart, MultiAxisLineChart, Axis, and LineSeries.", [
            "Generic: chart, set_option, set_data, append_data, resize_chart, remove_chart.",
            "Base helpers: line_chart, bar_chart, pie_chart, gauge, update_gauge.",
            "Gallery helpers: progress_gauge, multi_ring_gauge, stacked_line_chart, area_line_chart, stepped_line_chart, bar_race_chart, doughnut_chart, rose_pie_chart, bubble_scatter_chart, heatmap_chart, radar_chart, candlestick_chart, funnel_chart, treemap_chart.",
            "Builders: multi_axis_line_chart, line_chart_2x2y, add_x_axis, add_y_axis, add_line, render, update_line, update_x_axis.",
            "Live: live_time_chart and LiveTimeChart.append."
        ], None),
        ("Glossary", "A few terms appear throughout the project. Keeping them straight makes it easier to reason about where a feature belongs.", [
            "Browser surface: pallet.html and its rendering layers.",
            "Bridge: the process connecting TCP clients to browser WebSocket clients.",
            "Page: a named visual workspace inside the browser.",
            "Group: a named collection of commands that can be replaced together.",
            "Card: an HTML overlay container inside a grid.",
            "ChartHandle: an ECharts object used for later updates.",
            "Replay: compact bridge state sent to a reconnecting browser."
        ], None),
        ("Release Checklist", "Use this checklist when preparing a reusable Web Pallet demo, dashboard, or helper module.", [
            "Document how to start the bridge and which page to show.",
            "Use stable ids for charts, controls, tables, terminals, and cards.",
            "Bound live data structures such as chart windows and table rows.",
            "Use coalesced updates for high-frequency chart changes.",
            "Test browser reload and reconnect replay.",
            "Keep secrets out of terminal and table output.",
            "Include a small example script that runs from the repository root."
        ], None),
    ]
    for title, text, items, snippet in data:
        blocks = p(text) + bullets(*items)
        if snippet:
            blocks += code(snippet)
        PAGES.append(page(title, blocks, "Extension And Reference"))


def build_pdf() -> None:
    add_runtime_pages()
    add_ui_pages()
    add_graph_pages()
    add_echarts_pages()
    add_operations_pages()
    add_extension_reference_pages()

    remove_titles = {"Two X / Two Y Helper", "Environment Defaults"}
    PAGES[:] = [item for item in PAGES if item["title"] not in remove_titles]
    assert len(PAGES) == 60, f"manual should be 60 pages, got {len(PAGES)}"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUT), pagesize=letter)
    c.setTitle(TITLE)
    c.setAuthor("OpenAI Codex")
    c.setSubject(SUBTITLE)

    for idx, item in enumerate(PAGES, start=1):
        if idx == 1:
            w, h = letter
            c.setFillColor(colors.HexColor("#0F172A"))
            c.rect(0, 0, w, h, stroke=0, fill=1)
            c.setFillColor(colors.HexColor("#67E8F9"))
            c.rect(42, h - 142, 128, 6, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 34)
            c.drawString(42, h - 192, TITLE)
            c.setFont("Helvetica", 16)
            c.drawString(42, h - 220, SUBTITLE)
            c.setFillColor(colors.HexColor("#CBD5E1"))
            c.setFont("Helvetica", 10)
            y = h - 270
            for block in item["blocks"]:  # type: ignore[index]
                y = draw_wrapped(c, block["text"], 42, y, w - 84, size=10.5, leading=15, color=colors.HexColor("#CBD5E1"))
                y -= 10
            c.setFillColor(colors.HexColor("#67E8F9"))
            c.setFont("Helvetica-Bold", 9)
            c.drawString(42, 64, "60-page generated manual")
            c.drawRightString(w - 42, 64, "Web Pallet")
            c.showPage()
        else:
            draw_normal_page(c, item, idx)
    c.save()


if __name__ == "__main__":
    build_pdf()
    print(OUT)
