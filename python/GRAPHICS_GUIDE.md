# Pallet Graphics Library Guide

The Pallet graphics library draws shapes, charts, gauges, and terminal regions in
`pallet.html` from Python. This guide covers the public API in `pallet.py` and
`pallet_graph_lib.py`.

## Quick start

Start the Python bridge from the repository root:

```powershell
python python/bridge.py
```

Open `pallet.html`, connect it to `ws://localhost:8080`, and run a graph:

```python
import math

from pallet import Pallet
from pallet_graph_lib import Graph

xs = [index * 0.2 for index in range(40)]

with Pallet.for_bridge("127.0.0.1", width=960, height=540) as pallet:
    graph = Graph(
        pallet,
        title="Sine and cosine",
        x_label="Radians",
        y_label="Amplitude",
    )
    graph.add_series(xs, [math.sin(x) for x in xs], label="sin")
    graph.add_series(xs, [math.cos(x) for x in xs], label="cos")
    graph.draw()
```

The `width` and `height` arguments are optional. Without them, the bridge uses
the drawing size reported by the browser.

## Run the included examples

List all available demonstrations:

```powershell
python python/pallet_graph_examples.py --list
```

Run one demonstration:

```powershell
python python/pallet_graph_examples.py --demo 31
```

Run every demonstration in sequence:

```powershell
python python/pallet_graph_examples.py
```

Use `--bridge-host`, `--bridge-port`, `--width`, `--height`, or `--page` when
the bridge is remote or a specific drawing page is required.

## Basic drawing primitives

`Pallet` exposes immediate-mode canvas commands:

```python
with Pallet.for_bridge("127.0.0.1") as pallet:
    pallet.clear("#F8FAFC")
    pallet.line(30, 30, 240, 80, "#2563EB", 4)
    pallet.rect(30, 110, 180, 90, "#0F172A", 2)
    pallet.fill_rect(250, 110, 180, 90, "#BAE6FD")
    pallet.circle(120, 300, 55, "#7C3AED", 3)
    pallet.fill_circle(300, 300, 55, "#F97316")
    pallet.arc(480, 280, 70, 20, 300, "#059669", 8)
    pallet.text(30, 390, "Hello, Pallet", color="#0F172A", size=2)
```

Paths support caps, joins, and custom dash arrays:

```python
pallet.path(
    [(40, 60), (140, 20), (240, 90), (340, 35)],
    color="#DC2626",
    width=4,
    line_cap="round",
    line_join="round",
    dash=[10, 6],
)
```

## Graph layout and axes

`Graph` automatically selects rounded numeric bounds and readable
1/2/2.5/5 × 10ⁿ tick intervals. Tick density adapts to the graph's pixel size.

```python
graph = Graph(
    pallet,
    x=40,
    y=30,
    width=700,
    height=420,
    title="Measurements",
    x_label="Time",
    y_label="Temperature",
    y2_label="Humidity",
)
```

Set explicit limits when the automatic range is not appropriate:

```python
graph = Graph(pallet, x_min=0, x_max=60, y_min=-10, y_max=50)
```

Logarithmic axes are available independently:

```python
graph = Graph(pallet, log_x=True, log_y=True)
graph.add_series([1, 10, 100, 1000], [1, 100, 10_000, 1_000_000])
graph.draw()
```

Values on logarithmic axes must be positive.

### Datetime axes

Passing `date` or `datetime` values automatically enables intelligent datetime
labels. Naive datetimes are interpreted as UTC.

```python
from datetime import datetime, timedelta, timezone

start = datetime(2026, 6, 19, 8, tzinfo=timezone.utc)
times = [start + timedelta(minutes=30 * index) for index in range(17)]
values = [42 + index * 0.5 for index in range(len(times))]

Graph(pallet, title="Sensor history", x_label="UTC").add_series(
    times, values, label="sensor"
).draw()
```

The formatter switches between seconds, times, days, months, and years based
on the displayed span.

### Dual Y axes

```python
graph = Graph(
    pallet,
    x_label="Hour",
    y_label="°C",
    y2_label="% RH",
    y_min=0,
    y_max=40,
    y2_min=0,
    y2_max=100,
)
graph.add_series(hours, temperatures, label="temperature", y_axis=1)
graph.add_series(hours, humidity, label="humidity", y_axis=2)
graph.draw()
```

## Line and scatter graphs

Use `add_series()` for line graphs, scatter graphs, or both:

```python
graph.add_series(
    xs,
    ys,
    label="samples",
    color="#2563EB",
    draw_line=True,
    draw_markers=True,
    marker_radius=4,
)
```

For a scatter-only series, set `draw_line=False`. For a line without markers,
set `draw_markers=False`.

### Line styles

Named styles are `solid`, `dashed`, `dotted`, and `dashdot`:

```python
graph.add_series(
    xs,
    ys,
    color="#7C3AED",
    label="estimate",
    draw_markers=False,
    line_width=4,
    line_style="dashdot",
    line_cap="round",
)
```

Supply a custom pattern when the named styles are not sufficient:

```python
graph.add_series(xs, ys, dash_pattern=[12, 5, 3, 5])
```

### Spline fitting

Spline fitting produces a smooth interpolating curve through the original
points. Markers remain at the original samples.

```python
graph.add_series(xs, ys, spline=True, spline_resolution=16)
```

Two-point series fall back to a straight line.

### Missing-value gaps

Use `None` or `float("nan")` to create a visible gap. Lines, splines, areas,
and confidence bands do not connect across missing samples.

```python
ys = [1.0, 1.4, None, None, 2.1, 1.8, float("nan"), 1.2]
graph.add_series(range(len(ys)), ys, spline=True)
```

## Confidence bands

Confidence bands accept lower and upper values for each X coordinate:

```python
mean = [math.sin(x) for x in xs]
lower = [value - 0.2 for value in mean]
upper = [value + 0.2 for value in mean]

graph.add_confidence_band(
    xs,
    lower,
    upper,
    label="95% interval",
    color="#0284C7",
    fill="rgba(56, 189, 248, 0.20)",
)
graph.add_series(xs, mean, label="estimate", draw_markers=False)
graph.draw()
```

Lower values must not exceed upper values. A missing lower or upper sample
creates a gap in the band.

## Bar charts and histograms

### Grouped bars

Multiple unstacked bar series are grouped side by side automatically:

```python
quarters = [1, 2, 3, 4]
graph.add_bar_series(quarters, [120, 150, 130, 180], label="Product A")
graph.add_bar_series(quarters, [90, 110, 160, 140], label="Product B")
graph.draw()
```

### Stacked and grouped stacks

Series sharing the same `stack` name accumulate. Different stack names form
side-by-side groups:

```python
graph.add_bar_series(quarters, retail_a, label="A retail", stack="A")
graph.add_bar_series(quarters, online_a, label="A online", stack="A")
graph.add_bar_series(quarters, retail_b, label="B retail", stack="B")
graph.add_bar_series(quarters, online_b, label="B online", stack="B")
graph.draw()
```

Positive and negative values stack independently away from zero.

### Histograms

```python
graph.add_histogram(
    samples,
    bins=20,
    value_range=(-4, 4),
    density=False,
    cumulative=False,
    label="samples",
)
graph.draw()
```

`bins` may be a positive integer or an explicit sequence of increasing edges.

## Area charts

```python
graph.add_area_series(
    xs,
    ys,
    color="#BAE6FD",
    outline_color="#0284C7",
    label="load",
    line_style="dashed",
)
```

Stack areas by giving them the same stack name:

```python
graph.add_area_series(xs, received, label="RX", stack="traffic")
graph.add_area_series(xs, transmitted, label="TX", stack="traffic")
graph.draw()
```

## Heatmaps

```python
matrix = [
    [0.1, 0.4, 0.8],
    [0.3, 0.7, 1.0],
]

graph.add_heatmap(
    matrix,
    x_edges=[0, 1, 2, 3],
    y_edges=[0, 1, 2],
    color_map=["#F8FAFC", "#67E8F9", "#2563EB", "#7F1D1D"],
    label="intensity",
)
graph.draw()
```

If edges are omitted, integer bin edges are generated automatically.

## Polar and radar charts

`RadarChart` is an alias of `PolarChart`.

```python
from pallet_graph_lib import RadarChart

chart = RadarChart(
    pallet,
    ["Speed", "Range", "Comfort", "Safety", "Value"],
    title="Vehicle comparison",
    maximum=10,
)
chart.add_series(
    [8, 6, 7, 9, 5],
    label="Model A",
    color="#2563EB",
    fill="rgba(37, 99, 235, 0.18)",
)
chart.add_series(
    [6, 9, 8, 7, 8],
    label="Model B",
    color="#EA580C",
    fill="rgba(234, 88, 12, 0.18)",
)
chart.draw()
```

At least three categories are required. `minimum`, `maximum`, `levels`, and
`start_angle` control the radial scale and layout.

## Annotations

Annotations are chainable and are drawn with the graph:

```python
graph.add_y_span(70, 100, fill="rgba(248, 113, 113, 0.20)", text="warning")
graph.add_x_span(4, 6, fill="rgba(250, 204, 21, 0.22)", text="event")
graph.add_hline(70, text="limit", color="#DC2626")
graph.add_vline(5, text="trigger", color="#A16207")
graph.add_point_label(8, 82, "peak")
graph.draw()
```

Datetime values may be used for X annotations on datetime graphs.

## Gauges and meters

```python
from pallet_graph_lib import ArcGauge, BarGauge, CircularMeter, GaugeStyle

style = GaugeStyle(fill_color="#0EA5E9")
thresholds = [(70, "#F59E0B"), (90, "#EF4444")]

ArcGauge(
    pallet,
    value=76,
    minimum=0,
    maximum=100,
    title="CPU",
    units="%",
    style=style,
    thresholds=thresholds,
).draw()
```

Other choices are `CircularMeter` and horizontal or vertical `BarGauge`.
Gauges support labels, units, thresholds, ticks, custom bounds, and reusable
`GaugeStyle` objects.

## Live updates

Give labelled series unique labels when updating them by name:

```python
graph.add_series(xs, ys, label="sensor")
graph.draw()

graph.set_point("sensor", 4, y=27.5)
graph.set_point("sensor", 5, y=None)  # create a gap
graph.append_point("sensor", 20, 31.2, max_points=100)
graph.append_points("sensor", [21, 22], [30.8, 29.7], max_points=100)
graph.shift_series("sensor", dx=1, dy=0.5)
graph.trim_series("sensor", 50)
```

Replace a complete series:

```python
graph.set_series("sensor", new_xs, new_ys)
```

Update a confidence band with all three arrays:

```python
graph.set_confidence_band("95% interval", new_xs, new_lower, new_upper)
```

Update methods accept `redraw_axes="auto"`, `True`, or `False`. The default
redraws axes only when the calculated range changes.

## Positioning multiple graphics

Graphs and gauges accept `x`, `y`, `width`, and `height`, allowing dashboard
layouts on one canvas:

```python
Graph(pallet, x=20, y=20, width=440, height=300, title="Left").add_series(
    xs, left_values
).draw()

Graph(pallet, x=480, y=20, width=440, height=300, title="Right").add_series(
    xs, right_values
).draw()
```

Ensure each graph is large enough for its margins and labels.

## Styling

Use `GraphStyle`, `GaugeStyle`, and `PolarStyle` to reuse visual themes:

```python
from pallet_graph_lib import GraphStyle

dark = GraphStyle(
    bg_color="#0F172A",
    plot_bg_color="#111827",
    axis_color="#CBD5E1",
    grid_color="#334155",
    minor_grid_color="#1F2937",
    label_color="#CBD5E1",
    title_color="#F8FAFC",
)

Graph(pallet, style=dark, title="Dark graph").add_series(xs, ys).draw()
```

`grid_x` and `grid_y` are maximum target interval counts. The renderer may use
fewer ticks on small graphs to avoid label collisions.

## Interactive dashboards

Pallet can layer responsive HTML controls and tables over the drawing canvas.
Run the complete example with:

```powershell
python python/pallet_ui_examples.py
```

### Responsive grids and cards

```python
pallet.define_grid(
    "dashboard",
    columns=3,
    min_column_width=280,
    gap=16,
    padding=16,
)
pallet.define_card("controls", grid="dashboard", title="Controls")
pallet.define_card("results", grid="dashboard", title="Results", column_span=2)
```

Responsive grids automatically reduce the column count when space is limited.
Set `responsive=False` to keep the requested column count fixed. Grids and
cards also accept positioning, sizing, background, color, and border options.

### Controls and callbacks

Supported control kinds are `button`, `toggle`, `slider`, `select`, `text`, and
`number`.

```python
def level_changed(event):
    print(event["id"], event["event"], event["value"])

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
    on_event=level_changed,
)

pallet.control(
    "mode",
    card="controls",
    kind="select",
    label="Mode",
    options=["auto", "manual", "safe"],
    value="auto",
)

level.set(75)
```

`live=True` makes sliders emit `input` events while moving. Otherwise controls
emit a `change` event after the value is committed; buttons emit `click`.

Callbacks run while polling events:

```python
pallet.on_ui_event("*", lambda event: print(event))

while True:
    event = pallet.poll_event(timeout=1.0)
```

Alternatively, use `pallet.run_event_loop()`. Browser events include `id`,
`event`, `value`, `kind`, and the active page when applicable.

### Live data tables

```python
table = pallet.table(
    "sensors",
    [
        {"key": "id", "label": "#", "align": "right"},
        {"key": "name", "label": "Sensor"},
        {"key": "value", "label": "Value", "align": "right"},
    ],
    card="results",
    key_field="id",
    rows=[{"id": 1, "name": "A", "value": 42.1}],
    filterable=True,
    selectable=True,
    max_rows=500,
)

table.upsert({"id": 1, "name": "A", "value": 43.7})
table.upsert([{"id": 2, "name": "B", "value": 18.2}])
table.remove(1)
table.set_rows(new_rows)
table.clear()
```

Click column headers to sort. Filterable tables include a live search field.
Selectable rows emit `row_click` events containing the row key and value.
`max_rows` drops the oldest keyed rows as new rows arrive.

## Common pitfalls

- Call `draw()` after adding at least one series.
- Keep X and Y array lengths equal.
- Use positive values on logarithmic axes.
- Do not combine datetime X values with `log_x=True`.
- Keep heatmap edges strictly increasing.
- Keep confidence-band lower values at or below upper values.
- Use `None` or `NaN` for intentional gaps, not an arbitrary string.
- Use unique labels if series will be updated by name.

## Compact API reference

### Graph series

- `add_series(x, y, ...)`
- `add_bar_series(x, y, ...)`
- `add_histogram(data, ...)`
- `add_area_series(x, y, ...)`
- `add_confidence_band(x, lower, upper, ...)`
- `add_heatmap(z, ...)`

### Graph annotations

- `add_vline(x, ...)`
- `add_hline(y, ...)`
- `add_x_span(x_min, x_max, ...)`
- `add_y_span(y_min, y_max, ...)`
- `add_point_label(x, y, text, ...)`

### Graph updates

- `set_series(series, x, y, ...)`
- `set_confidence_band(series, x, lower, upper, ...)`
- `set_point(series, index, ...)`
- `append_point(series, x, y, ...)`
- `append_points(series, x, y, ...)`
- `shift_series(series, ...)`
- `trim_series(series, max_points, ...)`

Series selectors may be an integer index, a unique label, or a `Series`
instance.
