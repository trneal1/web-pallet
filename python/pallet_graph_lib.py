#!/usr/bin/env python3
"""
pallet_graph_lib.py
===================
Graph renderer for ``pallet.html``.

The public API mirrors the TFT graph library closely:

    from pallet import Pallet
    from pallet_graph_lib import Graph

    with Pallet.for_bridge("192.168.1.50", width=960, height=540) as pallet:
        g = Graph(
            pallet,
            x=40,
            y=30,
            width=520,
            height=320,
            title="sin / cos",
            x_label="Radians",
            y_label="Amp",
        )
        g.add_series(xs, ys, label="sin")
        g.draw()
"""
from __future__ import annotations

import math
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import List, Optional, Sequence, Tuple


DEFAULT_COLOURS = [
    "#06B6D4",
    "#F97316",
    "#22C55E",
    "#EC4899",
    "#EAB308",
    "#818CF8",
    "#EF4444",
    "#14B8A6",
]

DEFAULT_HEATMAP_COLOURS = ["#EFF6FF", "#38BDF8", "#2563EB", "#7C2D12"]
_UNSET = object()


def _is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


@dataclass
class Series:
    x_data: List[float]
    y_data: List[Optional[float]]
    color: str = "#06B6D4"
    label: str = ""
    draw_line: bool = True
    draw_markers: bool = True
    marker_radius: int = 4
    y_axis: int = 1
    chart_type: str = "line"
    outline_color: Optional[str] = None
    bar_gap: float = 0.18
    z_data: Optional[List[List[float]]] = None
    color_map: Optional[List[str]] = None
    z_min: Optional[float] = None
    z_max: Optional[float] = None
    spline: bool = False
    spline_resolution: int = 12
    stack: Optional[str] = None
    upper_data: Optional[List[Optional[float]]] = None
    fill_color: Optional[str] = None
    line_width: float = 3.0
    line_style: str = "solid"
    dash_pattern: Optional[List[float]] = None
    line_cap: str = "round"

    def __post_init__(self) -> None:
        if self.chart_type == "heatmap":
            if len(self.x_data) < 2 or len(self.y_data) < 2:
                raise ValueError(f"Series {self.label!r}: heatmap edges must contain at least two values")
            if any(self.x_data[index] >= self.x_data[index + 1] for index in range(len(self.x_data) - 1)):
                raise ValueError(f"Series {self.label!r}: heatmap x edges must be strictly increasing")
            if any(self.y_data[index] >= self.y_data[index + 1] for index in range(len(self.y_data) - 1)):
                raise ValueError(f"Series {self.label!r}: heatmap y edges must be strictly increasing")
            if self.z_data is None:
                raise ValueError(f"Series {self.label!r}: heatmap z data must not be empty")
            if len(self.z_data) != len(self.y_data) - 1:
                raise ValueError(f"Series {self.label!r}: heatmap row count must match y bins")
            if any(len(row) != len(self.x_data) - 1 for row in self.z_data):
                raise ValueError(f"Series {self.label!r}: heatmap column count must match x bins")
        elif len(self.x_data) != len(self.y_data):
            raise ValueError(f"Series {self.label!r}: x/y lengths differ")
        if self.chart_type == "band":
            if self.upper_data is None or len(self.upper_data) != len(self.x_data):
                raise ValueError(f"Series {self.label!r}: confidence band lengths differ")
            if any(
                _is_finite_number(lower) and _is_finite_number(upper) and lower > upper
                for lower, upper in zip(self.y_data, self.upper_data)
            ):
                raise ValueError("Confidence band lower values must not exceed upper values")
        if not self.x_data:
            raise ValueError(f"Series {self.label!r}: data must not be empty")
        if self.y_axis not in (1, 2):
            raise ValueError("y_axis must be 1 or 2")
        if self.chart_type not in ("line", "bar", "area", "heatmap", "band"):
            raise ValueError("chart_type must be 'line', 'bar', 'area', 'heatmap', or 'band'")
        if self.spline_resolution <= 0:
            raise ValueError("spline_resolution must be positive")
        if self.stack is not None and self.chart_type not in ("bar", "area"):
            raise ValueError("stack is only supported for bar and area series")
        if self.line_width <= 0:
            raise ValueError("line_width must be positive")
        if self.line_style not in ("solid", "dashed", "dotted", "dashdot"):
            raise ValueError("line_style must be 'solid', 'dashed', 'dotted', or 'dashdot'")
        if self.line_cap not in ("butt", "round", "square"):
            raise ValueError("line_cap must be 'butt', 'round', or 'square'")
        if self.dash_pattern is not None and (not self.dash_pattern or any(value <= 0 for value in self.dash_pattern)):
            raise ValueError("dash_pattern values must be positive")


@dataclass
class Annotation:
    kind: str
    x: Optional[float] = None
    y: Optional[float] = None
    x2: Optional[float] = None
    y2: Optional[float] = None
    text: str = ""
    color: str = "#0F172A"
    fill: Optional[str] = None
    width: float = 2
    size: int = 1
    y_axis: int = 1


@dataclass
class GraphStyle:
    bg_color: str = "#F8FAFC"
    plot_bg_color: str = "#FFFFFF"
    axis_color: str = "#334155"
    grid_color: str = "#CBD5E1"
    minor_grid_color: str = "#E2E8F0"
    label_color: str = "#475569"
    title_color: str = "#0F172A"
    zero_color: str = "#94A3B8"
    y2_axis_color: str = "#C2410C"
    legend_bg_color: str = "#F8FAFC"
    grid_x: int = 5
    grid_y: int = 4
    title_size: int = 2
    label_size: int = 1
    axis_title_size: int = 1


@dataclass
class GaugeStyle:
    bg_color: str = "#F8FAFC"
    panel_color: str = "#FFFFFF"
    border_color: str = "#CBD5E1"
    track_color: str = "#E2E8F0"
    fill_color: str = "#06B6D4"
    warning_color: str = "#F59E0B"
    danger_color: str = "#EF4444"
    tick_color: str = "#94A3B8"
    needle_color: str = "#0F172A"
    center_color: str = "#FFFFFF"
    title_color: str = "#0F172A"
    label_color: str = "#475569"
    value_color: str = "#0F172A"
    value_size: int = 2
    label_size: int = 1


def _safe_log10(value: float) -> float:
    return math.log10(value) if value > 0 else float("-inf")


def _log_axis_range(values: List[float], explicit_min: Optional[float], explicit_max: Optional[float]) -> Tuple[float, float]:
    bad = [v for v in values if v <= 0]
    if bad:
        raise ValueError(f"Log-scale axis requires values > 0; found {bad[:5]}")
    lo = explicit_min if explicit_min is not None else min(values)
    hi = explicit_max if explicit_max is not None else max(values)
    lo_exp = math.floor(_safe_log10(lo))
    hi_exp = math.ceil(_safe_log10(hi))
    if lo_exp == hi_exp:
        hi_exp += 1
    return 10.0 ** lo_exp, 10.0 ** hi_exp


def _linear_axis_range(values: List[float], explicit_min: Optional[float], explicit_max: Optional[float], pad_frac: float = 0.05) -> Tuple[float, float]:
    lo = explicit_min if explicit_min is not None else min(values)
    hi = explicit_max if explicit_max is not None else max(values)
    if lo == hi:
        lo -= 1.0
        hi += 1.0
    span = hi - lo
    if explicit_min is None:
        lo -= span * pad_frac
    if explicit_max is None:
        hi += span * pad_frac
    return lo, hi


def _nice_number(value: float) -> float:
    if value <= 0 or not math.isfinite(value):
        return 1.0
    exponent = math.floor(math.log10(value))
    fraction = value / (10.0 ** exponent)
    nice_fraction = min((1.0, 2.0, 2.5, 5.0, 10.0), key=lambda candidate: abs(candidate - fraction))
    return nice_fraction * (10.0 ** exponent)


def _nice_axis_range(
    values: List[float],
    explicit_min: Optional[float],
    explicit_max: Optional[float],
    target_intervals: int,
) -> Tuple[float, float]:
    lo = explicit_min if explicit_min is not None else min(values)
    hi = explicit_max if explicit_max is not None else max(values)
    if lo > hi:
        raise ValueError("Axis minimum must be less than maximum")
    if lo == hi and explicit_min is not None and explicit_max is not None:
        raise ValueError("Axis minimum must be less than maximum")
    if lo == hi:
        delta = max(1.0, abs(lo) * 0.1)
        if explicit_min is None:
            lo -= delta
        if explicit_max is None:
            hi += delta
        if lo == hi:
            hi = lo + delta
    data_lo, data_hi = lo, hi
    for _ in range(4):
        step = _nice_number((hi - lo) / max(1, target_intervals))
        next_lo = math.floor(data_lo / step) * step if explicit_min is None else lo
        next_hi = math.ceil(data_hi / step) * step if explicit_max is None else hi
        if math.isclose(next_lo, lo, rel_tol=1e-12, abs_tol=abs(step) * 1e-12) and math.isclose(next_hi, hi, rel_tol=1e-12, abs_tol=abs(step) * 1e-12):
            break
        lo, hi = next_lo, next_hi
    digits = max(0, 14 - math.floor(math.log10(abs(step))))
    lo, hi = round(lo, digits), round(hi, digits)
    return (0.0 if lo == 0 else lo), (0.0 if hi == 0 else hi)


def _linear_ticks(lo: float, hi: float, target_intervals: int) -> List[float]:
    step = _nice_number((hi - lo) / max(1, target_intervals))
    first = math.ceil((lo - step * 1e-10) / step) * step
    ticks: List[float] = []
    value = first
    while value <= hi + step * 1e-10 and len(ticks) < 100:
        rounded = round(value, max(0, 14 - math.floor(math.log10(abs(step))) if step else 14))
        ticks.append(0.0 if rounded == 0 else rounded)
        value += step
    return ticks


def _fmt_num(value: float, log_scale: bool = False) -> str:
    if value == 0:
        return "0"
    if log_scale:
        exp = _safe_log10(value)
        if abs(exp - round(exp)) < 0.01:
            n = int(round(exp))
            return "1" if n == 0 else f"10^{n}"
    if value == int(value) and abs(value) < 10000:
        return str(int(value))
    mag = abs(value)
    if mag >= 1_000_000:
        return f"{value:.2g}"
    if mag >= 100:
        return f"{value:.0f}"
    if mag >= 10:
        return f"{value:.1f}"
    if mag >= 1:
        return f"{value:.2f}"
    return f"{value:.2g}"


def _log_decade_ticks(lo: float, hi: float) -> List[Tuple[float, bool]]:
    ticks: List[Tuple[float, bool]] = []
    for exp in range(math.floor(_safe_log10(lo)), math.ceil(_safe_log10(hi)) + 1):
        decade = 10.0 ** exp
        if lo <= decade <= hi:
            ticks.append((decade, True))
        for mult in (2, 5):
            value = mult * decade
            if lo < value < hi:
                ticks.append((value, False))
    return sorted(ticks, key=lambda item: item[0])


def _bar_axis_padding(series: List[Series]) -> float:
    x_values = sorted({x for item in series for x in item.x_data})
    if len(x_values) < 2:
        return 0.5
    spacings = [
        x_values[index + 1] - x_values[index]
        for index in range(len(x_values) - 1)
        if x_values[index + 1] > x_values[index]
    ]
    return min(spacings) / 2 if spacings else 0.5


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _value_fraction(value: float, minimum: float, maximum: float) -> float:
    if minimum == maximum:
        raise ValueError("Gauge minimum and maximum must differ")
    return _clamp((value - minimum) / (maximum - minimum), 0.0, 1.0)


def _format_value(value: float, units: str = "") -> str:
    if value == int(value) and abs(value) < 10000:
        text = str(int(value))
    elif abs(value) >= 100:
        text = f"{value:.0f}"
    elif abs(value) >= 10:
        text = f"{value:.1f}"
    else:
        text = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{text}{units}"


def _angle_point(cx: float, cy: float, radius: float, angle_deg: float) -> Tuple[int, int]:
    radians = math.radians(angle_deg)
    return round(cx + math.cos(radians) * radius), round(cy + math.sin(radians) * radius)


def _arc_points(cx: float, cy: float, radius: float, start_angle: float, end_angle: float, steps: int = 64) -> List[Tuple[int, int]]:
    if steps <= 0:
        return [_angle_point(cx, cy, radius, start_angle)]
    return [
        _angle_point(cx, cy, radius, start_angle + (end_angle - start_angle) * i / steps)
        for i in range(steps + 1)
    ]


def _draw_arc(canvas, cx: float, cy: float, radius: float, start_angle: float, end_angle: float, color: str, width: float, *, line_cap: str = "round") -> None:
    if hasattr(canvas, "arc"):
        canvas.arc(cx, cy, radius, start_angle, end_angle, color, width, line_cap=line_cap)
        return

    sweep_radians = abs(math.radians(end_angle - start_angle))
    steps = max(48, min(360, math.ceil(sweep_radians * max(1.0, radius) / 1.5)))
    points = _arc_points(cx, cy, radius, start_angle, end_angle, steps)
    try:
        canvas.path(points, color, width, line_cap=line_cap, line_join="round")
    except TypeError:
        canvas.path(points, color, width)


class BarGauge:
    _CHAR_W = 8

    def __init__(
        self,
        canvas,
        *,
        value: float,
        minimum: float = 0.0,
        maximum: float = 100.0,
        title: str = "",
        label: str = "",
        units: str = "",
        x: int = 0,
        y: int = 0,
        width: Optional[int] = None,
        height: int = 96,
        orientation: str = "horizontal",
        style: Optional[GaugeStyle] = None,
        thresholds: Optional[Sequence[Tuple[float, str]]] = None,
        show_value: bool = True,
        show_ticks: bool = True,
    ) -> None:
        if orientation not in ("horizontal", "vertical"):
            raise ValueError("orientation must be 'horizontal' or 'vertical'")
        self._canvas = canvas
        self.value = value
        self.minimum = minimum
        self.maximum = maximum
        self.title = title
        self.label = label
        self.units = units
        self.x = round(x)
        self.y = round(y)
        self.width = round(width if width is not None else canvas.width - x)
        self.height = round(height)
        self.orientation = orientation
        self.style = style or GaugeStyle()
        self.thresholds = list(thresholds or [])
        self.show_value = show_value
        self.show_ticks = show_ticks
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Gauge width and height must be positive")

    def draw(self) -> None:
        batch_started = False
        if hasattr(self._canvas, "begin_batch") and hasattr(self._canvas, "end_batch"):
            self._canvas.begin_batch()
            batch_started = True
        try:
            self._draw()
        finally:
            if batch_started:
                self._canvas.end_batch()

    def _draw(self) -> None:
        c = self._canvas
        st = self.style
        frac = _value_fraction(self.value, self.minimum, self.maximum)
        c.fill_rect(self.x, self.y, self.width, self.height, st.panel_color)
        c.rect(self.x, self.y, self.width, self.height, st.border_color)
        if self.title:
            c.text(self.x + 12, self.y + 8, self.title, color=st.title_color, size=1)

        if self.orientation == "horizontal":
            tx = self.x + 14
            ty = self.y + max(34, self.height // 2 - 8)
            tw = max(20, self.width - 28)
            th = max(14, min(24, self.height - 58))
            c.fill_rect(tx, ty, tw, th, st.track_color)
            self._draw_threshold_bands(tx, ty, tw, th)
            c.fill_rect(tx, ty, max(1, round(tw * frac)), th, self._value_color(frac))
            c.rect(tx, ty, tw, th, st.border_color)
            if self.show_ticks:
                for i in range(6):
                    px = tx + round(tw * i / 5)
                    c.vline(px, ty + th + 4, 8, st.tick_color)
            self._draw_text(tx, ty + th + 16, tw)
        else:
            tx = self.x + self.width // 2 - max(12, self.width // 8)
            ty = self.y + 36
            tw = max(18, min(34, self.width - 28))
            th = max(30, self.height - 76)
            c.fill_rect(tx, ty, tw, th, st.track_color)
            self._draw_threshold_bands(tx, ty, tw, th)
            fill_h = max(1, round(th * frac))
            c.fill_rect(tx, ty + th - fill_h, tw, fill_h, self._value_color(frac))
            c.rect(tx, ty, tw, th, st.border_color)
            if self.show_ticks:
                for i in range(6):
                    py = ty + round(th * i / 5)
                    c.hline(tx + tw + 4, py, 8, st.tick_color)
            self._draw_text(self.x + 8, self.y + self.height - 32, self.width - 16)

    def _draw_threshold_bands(self, x: int, y: int, width: int, height: int) -> None:
        for threshold, color in self.thresholds:
            t = _value_fraction(threshold, self.minimum, self.maximum)
            if self.orientation == "horizontal":
                bx = x + round(width * t)
                self._canvas.fill_rect(bx, y, max(1, x + width - bx), height, color)
            else:
                by = y + round(height * (1.0 - t))
                self._canvas.fill_rect(x, y, width, max(1, by - y), color)

    def _value_color(self, frac: float) -> str:
        color = self.style.fill_color
        for threshold, threshold_color in self.thresholds:
            if frac >= _value_fraction(threshold, self.minimum, self.maximum):
                color = threshold_color
        return color

    def _draw_text(self, x: int, y: int, width: int) -> None:
        st = self.style
        if self.label:
            self._canvas.text(x, y, self.label, color=st.label_color, size=st.label_size)
        if self.show_value:
            text = _format_value(self.value, self.units)
            self._canvas.text(
                x + max(0, width - len(text) * self._CHAR_W * st.value_size),
                y,
                text,
                color=st.value_color,
                size=st.value_size,
            )


class ArcGauge:
    _CHAR_W = 8

    def __init__(
        self,
        canvas,
        *,
        value: float,
        minimum: float = 0.0,
        maximum: float = 100.0,
        title: str = "",
        label: str = "",
        units: str = "",
        x: int = 0,
        y: int = 0,
        width: Optional[int] = None,
        height: int = 220,
        start_angle: float = 135.0,
        end_angle: float = 405.0,
        style: Optional[GaugeStyle] = None,
        thresholds: Optional[Sequence[Tuple[float, str]]] = None,
        show_value: bool = True,
        show_ticks: bool = True,
        needle: bool = True,
    ) -> None:
        self._canvas = canvas
        self.value = value
        self.minimum = minimum
        self.maximum = maximum
        self.title = title
        self.label = label
        self.units = units
        self.x = round(x)
        self.y = round(y)
        self.width = round(width if width is not None else canvas.width - x)
        self.height = round(height)
        self.start_angle = start_angle
        self.end_angle = end_angle
        self.style = style or GaugeStyle()
        self.thresholds = list(thresholds or [])
        self.show_value = show_value
        self.show_ticks = show_ticks
        self.needle = needle
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Gauge width and height must be positive")

    def draw(self) -> None:
        batch_started = False
        if hasattr(self._canvas, "begin_batch") and hasattr(self._canvas, "end_batch"):
            self._canvas.begin_batch()
            batch_started = True
        try:
            self._draw()
        finally:
            if batch_started:
                self._canvas.end_batch()

    def _draw(self) -> None:
        c = self._canvas
        st = self.style
        frac = _value_fraction(self.value, self.minimum, self.maximum)
        cx = self.x + self.width / 2
        cy = self.y + self.height - 34
        radius = max(20, min(self.width * 0.42, self.height - 68))
        sweep = self.end_angle - self.start_angle
        value_angle = self.start_angle + sweep * frac

        c.fill_rect(self.x, self.y, self.width, self.height, st.panel_color)
        c.rect(self.x, self.y, self.width, self.height, st.border_color)
        if self.title:
            c.text(self.x + 12, self.y + 8, self.title, color=st.title_color, size=1)

        _draw_arc(c, cx, cy, radius, self.start_angle, self.end_angle, st.track_color, 14, line_cap="butt")
        self._draw_threshold_arcs(cx, cy, radius)
        _draw_arc(c, cx, cy, radius, self.start_angle, value_angle, self._value_color(frac), 14)
        if self.show_ticks:
            self._draw_ticks(cx, cy, radius)
        if self.needle:
            nx, ny = _angle_point(cx, cy, radius - 16, value_angle)
            c.line(cx, cy, nx, ny, st.needle_color, 3)
            c.fill_circle(cx, cy, 7, st.needle_color)
            c.fill_circle(cx, cy, 4, st.center_color)
        self._draw_text(cx)

    def _draw_threshold_arcs(self, cx: float, cy: float, radius: float) -> None:
        sweep = self.end_angle - self.start_angle
        for threshold, color in self.thresholds:
            t = _value_fraction(threshold, self.minimum, self.maximum)
            angle = self.start_angle + sweep * t
            _draw_arc(self._canvas, cx, cy, radius, angle, self.end_angle, color, 14, line_cap="butt")

    def _draw_ticks(self, cx: float, cy: float, radius: float) -> None:
        for i in range(7):
            angle = self.start_angle + (self.end_angle - self.start_angle) * i / 6
            x0, y0 = _angle_point(cx, cy, radius - 6, angle)
            x1, y1 = _angle_point(cx, cy, radius + 8, angle)
            self._canvas.line(x0, y0, x1, y1, self.style.tick_color, 2)

    def _value_color(self, frac: float) -> str:
        color = self.style.fill_color
        for threshold, threshold_color in self.thresholds:
            if frac >= _value_fraction(threshold, self.minimum, self.maximum):
                color = threshold_color
        return color

    def _draw_text(self, cx: float) -> None:
        st = self.style
        if self.show_value:
            text = _format_value(self.value, self.units)
            self._canvas.text(cx - len(text) * self._CHAR_W * st.value_size // 2, self.y + self.height - 58, text, color=st.value_color, size=st.value_size)
        if self.label:
            self._canvas.text(cx - len(self.label) * self._CHAR_W // 2, self.y + self.height - 30, self.label, color=st.label_color, size=st.label_size)


class CircularMeter:
    _CHAR_W = 8

    def __init__(
        self,
        canvas,
        *,
        value: float,
        minimum: float = 0.0,
        maximum: float = 100.0,
        title: str = "",
        label: str = "",
        units: str = "",
        x: int = 0,
        y: int = 0,
        width: Optional[int] = None,
        height: Optional[int] = None,
        style: Optional[GaugeStyle] = None,
        thresholds: Optional[Sequence[Tuple[float, str]]] = None,
        show_value: bool = True,
        show_ticks: bool = True,
        start_angle: float = -90.0,
    ) -> None:
        self._canvas = canvas
        self.value = value
        self.minimum = minimum
        self.maximum = maximum
        self.title = title
        self.label = label
        self.units = units
        self.x = round(x)
        self.y = round(y)
        self.width = round(width if width is not None else canvas.width - x)
        self.height = round(height if height is not None else self.width)
        self.style = style or GaugeStyle()
        self.thresholds = list(thresholds or [])
        self.show_value = show_value
        self.show_ticks = show_ticks
        self.start_angle = start_angle
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Meter width and height must be positive")

    def draw(self) -> None:
        batch_started = False
        if hasattr(self._canvas, "begin_batch") and hasattr(self._canvas, "end_batch"):
            self._canvas.begin_batch()
            batch_started = True
        try:
            self._draw()
        finally:
            if batch_started:
                self._canvas.end_batch()

    def _draw(self) -> None:
        c = self._canvas
        st = self.style
        frac = _value_fraction(self.value, self.minimum, self.maximum)
        cx = self.x + self.width / 2
        cy = self.y + self.height / 2 + (8 if self.title else 0)
        radius = max(18, min(self.width, self.height - 18) * 0.33)
        c.fill_rect(self.x, self.y, self.width, self.height, st.panel_color)
        c.rect(self.x, self.y, self.width, self.height, st.border_color)
        if self.title:
            c.text(self.x + 12, self.y + 8, self.title, color=st.title_color, size=1)

        _draw_arc(c, cx, cy, radius, self.start_angle, self.start_angle + 360, st.track_color, 14, line_cap="butt")
        self._draw_threshold_arcs(cx, cy, radius)
        _draw_arc(c, cx, cy, radius, self.start_angle, self.start_angle + 360 * frac, self._value_color(frac), 14)
        c.fill_circle(cx, cy, max(4, radius - 18), st.panel_color)
        if self.show_ticks:
            for i in range(12):
                angle = self.start_angle + i * 30
                x0, y0 = _angle_point(cx, cy, radius - 5, angle)
                x1, y1 = _angle_point(cx, cy, radius + 5, angle)
                c.line(x0, y0, x1, y1, st.tick_color, 1)
        if self.show_value:
            text = _format_value(self.value, self.units)
            c.text(cx - len(text) * self._CHAR_W * st.value_size // 2, cy - 18, text, color=st.value_color, size=st.value_size)
        if self.label:
            c.text(cx - len(self.label) * self._CHAR_W // 2, cy + 14, self.label, color=st.label_color, size=st.label_size)

    def _draw_threshold_arcs(self, cx: float, cy: float, radius: float) -> None:
        for threshold, color in self.thresholds:
            t = _value_fraction(threshold, self.minimum, self.maximum)
            start = self.start_angle + 360 * t
            _draw_arc(self._canvas, cx, cy, radius, start, self.start_angle + 360, color, 14, line_cap="butt")

    def _value_color(self, frac: float) -> str:
        color = self.style.fill_color
        for threshold, threshold_color in self.thresholds:
            if frac >= _value_fraction(threshold, self.minimum, self.maximum):
                color = threshold_color
        return color


class Graph:
    _CHAR_W = 8
    _CHAR_H = 14

    def __init__(
        self,
        canvas,
        *,
        title: str = "",
        x_label: str = "X",
        y_label: str = "Y",
        y2_label: str = "",
        x_min: Optional[float | date | datetime] = None,
        x_max: Optional[float | date | datetime] = None,
        y_min: Optional[float] = None,
        y_max: Optional[float] = None,
        y2_min: Optional[float] = None,
        y2_max: Optional[float] = None,
        log_x: bool = False,
        log_y: bool = False,
        log_y2: bool = False,
        datetime_x: bool = False,
        style: Optional[GraphStyle] = None,
        x: int = 0,
        y: int = 0,
        width: Optional[int] = None,
        height: Optional[int] = None,
        margin_left: Optional[int] = None,
        margin_bottom: Optional[int] = None,
        margin_top: Optional[int] = None,
        margin_right: Optional[int] = None,
        graph_id: Optional[str] = None,
        coalesce: bool = False,
    ) -> None:
        self._canvas = canvas
        self.title = title
        self.x_label = x_label
        self.y_label = y_label
        self.y2_label = y2_label
        self._datetime_x = datetime_x or isinstance(x_min, (date, datetime)) or isinstance(x_max, (date, datetime))
        self.x_min = self._datetime_value(x_min) if x_min is not None else None
        self.x_max = self._datetime_value(x_max) if x_max is not None else None
        self.y_min = y_min
        self.y_max = y_max
        self.y2_min = y2_min
        self.y2_max = y2_max
        self.log_x = log_x
        self.log_y = log_y
        self.log_y2 = log_y2
        if self._datetime_x and self.log_x:
            raise ValueError("datetime_x cannot be combined with log_x")
        self.style = style or GraphStyle()
        self._series: List[Series] = []
        self._annotations: List[Annotation] = []
        self.graph_id = graph_id or f"graph-{id(self):x}"
        self.coalesce = coalesce
        self._last_ranges: Optional[Tuple[float, float, float, float, float, float]] = None

        graph_width = width if width is not None else canvas.width - x
        graph_height = height if height is not None else canvas.height - y
        if graph_width <= 0 or graph_height <= 0:
            raise ValueError("Graph width and height must be positive")

        self._gx0 = round(x)
        self._gy0 = round(y)
        self._gw = round(graph_width)
        self._gh = round(graph_height)
        self._gx1 = self._gx0 + self._gw - 1
        self._gy1 = self._gy0 + self._gh - 1

        self._ml = margin_left if margin_left is not None else 72
        self._mb = margin_bottom if margin_bottom is not None else 58
        self._mt = margin_top if margin_top is not None else (44 if title else 22)
        self._mr = margin_right if margin_right is not None else (76 if y2_label else 34)
        self._px0 = self._gx0 + self._ml
        self._py0 = self._gy0 + self._mt
        self._px1 = self._gx1 - self._mr
        self._py1 = self._gy1 - self._mb
        if self._px1 - self._px0 < 40 or self._py1 - self._py0 < 40:
            raise ValueError("Plot area is too small for the selected canvas size")

    @staticmethod
    def _datetime_value(value: float | date | datetime) -> float:
        if isinstance(value, datetime):
            moment = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
            return moment.timestamp()
        if isinstance(value, date):
            return datetime(value.year, value.month, value.day, tzinfo=timezone.utc).timestamp()
        return float(value)

    def _coerce_x_data(self, values: Sequence[float | date | datetime]) -> List[float]:
        if any(isinstance(value, (date, datetime)) for value in values):
            if self.log_x:
                raise ValueError("datetime X data cannot be combined with log_x")
            self._datetime_x = True
        return [self._datetime_value(value) for value in values]

    def add_series(
        self,
        x_data: Sequence[float | date | datetime],
        y_data: Sequence[Optional[float]],
        *,
        color: Optional[str] = None,
        label: str = "",
        draw_line: bool = True,
        draw_markers: bool = True,
        marker_radius: int = 4,
        y_axis: int = 1,
        spline: bool = False,
        spline_resolution: int = 12,
        line_width: float = 3.0,
        line_style: str = "solid",
        dash_pattern: Optional[Sequence[float]] = None,
        line_cap: str = "round",
    ) -> "Graph":
        self._series.append(Series(
            self._coerce_x_data(x_data), list(y_data),
            color or DEFAULT_COLOURS[len(self._series) % len(DEFAULT_COLOURS)],
            label, draw_line, draw_markers, marker_radius, y_axis, "line",
            spline=spline, spline_resolution=spline_resolution,
            line_width=line_width, line_style=line_style,
            dash_pattern=list(dash_pattern) if dash_pattern is not None else None,
            line_cap=line_cap,
        ))
        return self

    def add_bar_series(
        self,
        x_data: Sequence[float | date | datetime],
        y_data: Sequence[float],
        *,
        color: Optional[str] = None,
        outline_color: Optional[str] = None,
        label: str = "",
        bar_gap: float = 0.18,
        y_axis: int = 1,
        stack: Optional[str] = None,
    ) -> "Graph":
        self._series.append(Series(
            self._coerce_x_data(x_data), list(y_data),
            color or DEFAULT_COLOURS[len(self._series) % len(DEFAULT_COLOURS)],
            label, False, False, 0, y_axis, "bar", outline_color, bar_gap,
            stack=stack,
        ))
        return self

    def add_histogram(
        self,
        data: Sequence[float],
        *,
        bins: int | Sequence[float] = 10,
        value_range: Optional[Tuple[float, float]] = None,
        density: bool = False,
        cumulative: bool = False,
        color: Optional[str] = None,
        outline_color: Optional[str] = None,
        label: str = "",
        bar_gap: float = 0.06,
        y_axis: int = 1,
    ) -> "Graph":
        values = [float(value) for value in data]
        if not values:
            raise ValueError("Histogram data must not be empty")

        if isinstance(bins, int):
            if bins <= 0:
                raise ValueError("Histogram bins must be positive")
            lo = min(values) if value_range is None else float(value_range[0])
            hi = max(values) if value_range is None else float(value_range[1])
            if lo >= hi:
                raise ValueError("Histogram value_range minimum must be less than maximum")
            step = (hi - lo) / bins
            edges = [lo + step * index for index in range(bins + 1)]
        else:
            edges = [float(edge) for edge in bins]
            if len(edges) < 2:
                raise ValueError("Histogram bin edges must contain at least two values")
            if any(edges[index] >= edges[index + 1] for index in range(len(edges) - 1)):
                raise ValueError("Histogram bin edges must be strictly increasing")

        counts = [0.0 for _ in range(len(edges) - 1)]
        first, last = edges[0], edges[-1]
        for value in values:
            if value < first or value > last:
                continue
            if value == last:
                counts[-1] += 1
                continue
            index = self._histogram_bin_index(edges, value)
            if index is not None:
                counts[index] += 1

        if cumulative:
            running = 0.0
            for index, count in enumerate(counts):
                running += count
                counts[index] = running

        if density:
            total = sum(counts)
            if total > 0:
                counts = [
                    count / (total * (edges[index + 1] - edges[index]))
                    for index, count in enumerate(counts)
                ]

        centers = [(edges[index] + edges[index + 1]) / 2 for index in range(len(edges) - 1)]
        return self.add_bar_series(
            centers,
            counts,
            color=color,
            outline_color=outline_color,
            label=label,
            bar_gap=bar_gap,
            y_axis=y_axis,
        )

    @staticmethod
    def _histogram_bin_index(edges: Sequence[float], value: float) -> Optional[int]:
        lo = 0
        hi = len(edges) - 2
        while lo <= hi:
            mid = (lo + hi) // 2
            if edges[mid] <= value < edges[mid + 1]:
                return mid
            if value < edges[mid]:
                hi = mid - 1
            else:
                lo = mid + 1
        return None

    def add_area_series(
        self,
        x_data: Sequence[float | date | datetime],
        y_data: Sequence[Optional[float]],
        *,
        color: Optional[str] = None,
        outline_color: Optional[str] = None,
        label: str = "",
        draw_markers: bool = False,
        marker_radius: int = 4,
        y_axis: int = 1,
        stack: Optional[str] = None,
        line_width: float = 3.0,
        line_style: str = "solid",
        dash_pattern: Optional[Sequence[float]] = None,
        line_cap: str = "round",
    ) -> "Graph":
        self._series.append(Series(
            self._coerce_x_data(x_data), list(y_data),
            color or DEFAULT_COLOURS[len(self._series) % len(DEFAULT_COLOURS)],
            label, True, draw_markers, marker_radius, y_axis, "area", outline_color,
            stack=stack,
            line_width=line_width, line_style=line_style,
            dash_pattern=list(dash_pattern) if dash_pattern is not None else None,
            line_cap=line_cap,
        ))
        return self

    def add_confidence_band(
        self,
        x_data: Sequence[float | date | datetime],
        lower_data: Sequence[Optional[float]],
        upper_data: Sequence[Optional[float]],
        *,
        color: Optional[str] = None,
        fill: str = "rgba(14, 165, 233, 0.18)",
        label: str = "",
        y_axis: int = 1,
        line_width: float = 1.5,
        line_style: str = "solid",
        dash_pattern: Optional[Sequence[float]] = None,
        line_cap: str = "round",
    ) -> "Graph":
        if len(x_data) != len(lower_data) or len(x_data) != len(upper_data):
            raise ValueError("Confidence band x/lower/upper lengths differ")
        for lower, upper in zip(lower_data, upper_data):
            if _is_finite_number(lower) and _is_finite_number(upper) and lower > upper:
                raise ValueError("Confidence band lower values must not exceed upper values")
        stroke = color or DEFAULT_COLOURS[len(self._series) % len(DEFAULT_COLOURS)]
        self._series.append(Series(
            self._coerce_x_data(x_data),
            list(lower_data),
            stroke,
            label,
            True,
            False,
            0,
            y_axis,
            "band",
            upper_data=list(upper_data),
            fill_color=fill,
            line_width=line_width,
            line_style=line_style,
            dash_pattern=list(dash_pattern) if dash_pattern is not None else None,
            line_cap=line_cap,
        ))
        return self

    def add_heatmap(
        self,
        z_data: Sequence[Sequence[float]],
        *,
        x_edges: Optional[Sequence[float]] = None,
        y_edges: Optional[Sequence[float]] = None,
        z_min: Optional[float] = None,
        z_max: Optional[float] = None,
        color_map: Optional[Sequence[str]] = None,
        outline_color: Optional[str] = None,
        label: str = "",
        y_axis: int = 1,
    ) -> "Graph":
        matrix = [[float(value) for value in row] for row in z_data]
        if not matrix or not matrix[0]:
            raise ValueError("Heatmap z_data must not be empty")
        columns = len(matrix[0])
        if any(len(row) != columns for row in matrix):
            raise ValueError("Heatmap rows must all have the same length")
        colors = list(color_map or DEFAULT_HEATMAP_COLOURS)
        if not colors:
            raise ValueError("Heatmap color_map must not be empty")
        xs = list(x_edges) if x_edges is not None else [float(index) for index in range(columns + 1)]
        ys = list(y_edges) if y_edges is not None else [float(index) for index in range(len(matrix) + 1)]
        self._series.append(Series(
            xs,
            ys,
            colors[0],
            label,
            False,
            False,
            0,
            y_axis,
            "heatmap",
            outline_color,
            0.0,
            matrix,
            colors,
            z_min,
            z_max,
        ))
        return self

    def add_vline(self, x: float, *, text: str = "", color: str = "#0F172A", width: float = 2, size: int = 1) -> "Graph":
        self._annotations.append(Annotation("vline", x=self._datetime_value(x), text=text, color=color, width=width, size=size))
        return self

    def add_hline(
        self,
        y: float,
        *,
        text: str = "",
        color: str = "#0F172A",
        width: float = 2,
        size: int = 1,
        y_axis: int = 1,
    ) -> "Graph":
        self._annotations.append(Annotation("hline", y=y, text=text, color=color, width=width, size=size, y_axis=y_axis))
        return self

    def add_x_span(self, x_min: float, x_max: float, *, fill: str = "rgba(250, 204, 21, 0.22)", text: str = "") -> "Graph":
        self._annotations.append(Annotation("xspan", x=self._datetime_value(x_min), x2=self._datetime_value(x_max), fill=fill, text=text))
        return self

    def add_y_span(
        self,
        y_min: float,
        y_max: float,
        *,
        fill: str = "rgba(250, 204, 21, 0.22)",
        text: str = "",
        y_axis: int = 1,
    ) -> "Graph":
        self._annotations.append(Annotation("yspan", y=y_min, y2=y_max, fill=fill, text=text, y_axis=y_axis))
        return self

    def add_point_label(
        self,
        x: float,
        y: float,
        text: str,
        *,
        color: str = "#0F172A",
        fill: Optional[str] = "#FFFFFF",
        size: int = 1,
        y_axis: int = 1,
    ) -> "Graph":
        self._annotations.append(Annotation("point", x=self._datetime_value(x), y=y, text=text, color=color, fill=fill, size=size, y_axis=y_axis))
        return self

    def draw(self, *, coalesce: Optional[bool] = None) -> None:
        if not self._series:
            raise ValueError("No series added")

        use_coalesce = self.coalesce if coalesce is None else coalesce
        if use_coalesce and hasattr(self._canvas, "coalesce_group"):
            with self._canvas.coalesce_group(self._graph_group()):
                self._draw()
            return

        batch_started = False
        if hasattr(self._canvas, "begin_batch") and hasattr(self._canvas, "end_batch"):
            self._canvas.begin_batch()
            batch_started = True

        try:
            self._draw()
        finally:
            if batch_started:
                self._canvas.end_batch()

    def _draw(self) -> None:
        st = self.style
        x_min, x_max, y_min, y_max, y2_min, y2_max = self._calculate_ranges()
        self._last_ranges = (x_min, x_max, y_min, y_max, y2_min, y2_max)
        y2_series = [s for s in self._series if s.y_axis == 2]

        c = self._canvas
        pw = self._px1 - self._px0 + 1
        ph = self._py1 - self._py0 + 1
        c.fill_rect(self._gx0, self._gy0, self._gw, self._gh, st.bg_color)
        c.fill_rect(self._px0, self._py0, pw, ph, st.plot_bg_color)
        self._draw_title(st, pw)
        self._draw_grid(x_min, x_max, y_min, y_max, st)
        self._draw_zero_lines(x_min, x_max, y_min, y_max, st)
        self._draw_ticks(x_min, x_max, y_min, y_max, y2_min, y2_max, st, bool(y2_series))
        self._draw_axis_labels(st, pw, bool(y2_series))

        self._draw_span_annotations(x_min, x_max, y_min, y_max, y2_min, y2_max)

        for chart_type in ("heatmap", "band", "area", "bar", "line"):
            for index, series in [(i, s) for i, s in enumerate(self._series) if s.chart_type == chart_type]:
                ym, yM, log_y = (y2_min, y2_max, self.log_y2) if series.y_axis == 2 else (y_min, y_max, self.log_y)
                with self._series_command_context(index):
                    if chart_type == "heatmap":
                        self._draw_heatmap(series, x_min, x_max, ym, yM)
                    elif chart_type == "band":
                        self._draw_confidence_band(series, x_min, x_max, ym, yM, log_y)
                    elif chart_type == "bar":
                        axis_bars = [item for item in self._series if item.chart_type == "bar" and item.y_axis == series.y_axis]
                        self._draw_bar(series, x_min, x_max, ym, yM, log_y, axis_bars)
                    elif chart_type == "area":
                        self._draw_area(series, x_min, x_max, ym, yM, log_y)
                    else:
                        self._draw_line_series(series, x_min, x_max, ym, yM, log_y)

        self._draw_line_annotations(x_min, x_max, y_min, y_max, y2_min, y2_max)
        self._draw_axes(st, bool(y2_series), pw, ph)
        self._draw_legend(st, bool(y2_series))

    def _calculate_ranges(self) -> Tuple[float, float, float, float, float, float]:
        y1_series = [s for s in self._series if s.y_axis == 1]
        y2_series = [s for s in self._series if s.y_axis == 2]
        bar_series = [s for s in self._series if s.chart_type == "bar"]
        all_x = [v for s in self._series for v in s.x_data]
        all_y1 = self._range_y_values(y1_series)
        all_y2 = self._range_y_values(y2_series)

        x_target = self._x_target_intervals()
        y_target = self._y_target_intervals()
        if self.log_x:
            x_min, x_max = _log_axis_range(all_x, self.x_min, self.x_max)
        elif self._datetime_x:
            x_min, x_max = _linear_axis_range(all_x, self.x_min, self.x_max)
        else:
            x_range_values = list(all_x)
            if bar_series:
                pad = _bar_axis_padding(bar_series)
                x_range_values.extend((min(all_x) - pad, max(all_x) + pad))
            x_min, x_max = _nice_axis_range(x_range_values, self.x_min, self.x_max, x_target)
        if bar_series and not self.log_x and self._datetime_x:
            pad = _bar_axis_padding(bar_series)
            if self.x_min is None:
                x_min = min(x_min, min(all_x) - pad)
            if self.x_max is None:
                x_max = max(x_max, max(all_x) + pad)
        y_min, y_max = _log_axis_range(all_y1, self.y_min, self.y_max) if self.log_y else _nice_axis_range(all_y1, self.y_min, self.y_max, y_target)
        y2_min, y2_max = _log_axis_range(all_y2, self.y2_min, self.y2_max) if self.log_y2 else _nice_axis_range(all_y2, self.y2_min, self.y2_max, y_target)
        return x_min, x_max, y_min, y_max, y2_min, y2_max

    def _x_target_intervals(self) -> int:
        available = max(1, (self._px1 - self._px0) // 82)
        return max(1, min(self.style.grid_x, available))

    def _y_target_intervals(self) -> int:
        available = max(1, (self._py1 - self._py0) // 44)
        return max(1, min(self.style.grid_y, available))

    def _x_tick_values(self, x_min: float, x_max: float) -> List[float]:
        target = self._x_target_intervals()
        if self._datetime_x:
            return self._datetime_ticks(x_min, x_max, target)
        if self.log_x:
            return [value for value, major in _log_decade_ticks(x_min, x_max) if major]
        return _linear_ticks(x_min, x_max, target)

    def _y_tick_values(self, y_min: float, y_max: float, axis: int) -> List[float]:
        log_scale = self.log_y2 if axis == 2 else self.log_y
        if log_scale:
            return [value for value, major in _log_decade_ticks(y_min, y_max) if major]
        return _linear_ticks(y_min, y_max, self._y_target_intervals())

    @staticmethod
    def _range_y_values(series: Sequence[Series]) -> List[float]:
        values = [
            value for item in series if item.stack is None
            for value in item.y_data if _is_finite_number(value)
        ]
        values.extend(
            value for item in series if item.upper_data is not None
            for value in item.upper_data if _is_finite_number(value)
        )
        stacks: dict[Tuple[str, str, float], List[float]] = {}
        for item in series:
            if item.stack is None:
                continue
            for x_value, y_value in zip(item.x_data, item.y_data):
                if not _is_finite_number(y_value):
                    continue
                totals = stacks.setdefault((item.chart_type, item.stack, x_value), [0.0, 0.0])
                totals[0 if y_value >= 0 else 1] += y_value
        values.extend(total for totals in stacks.values() for total in totals)
        if stacks:
            values.append(0.0)
        return values or [0, 1]

    def _series_command_context(self, index: int):
        if hasattr(self._canvas, "command_metadata"):
            return self._canvas.command_metadata(group=self._series_group(index))
        return nullcontext()

    def _series_group(self, index: int) -> str:
        return f"pallet-graph:{self.graph_id}:series:{index}"

    def _graph_group(self) -> str:
        return f"pallet-graph:{self.graph_id}:graph"

    def _series_index(self, series: int | str | Series) -> int:
        if isinstance(series, int):
            if -len(self._series) <= series < len(self._series):
                return series % len(self._series)
            raise IndexError("series index out of range")
        if isinstance(series, Series):
            return self._series.index(series)
        for index, item in enumerate(self._series):
            if item.label == series:
                return index
        raise ValueError(f"Unknown series {series!r}")

    def set_series(
        self,
        series: int | str | Series,
        x_data: Sequence[float | date | datetime],
        y_data: Sequence[Optional[float]],
        *,
        redraw_axes: str | bool = "auto",
    ) -> None:
        index = self._series_index(series)
        target = self._series[index]
        if target.chart_type == "band":
            raise ValueError("Use set_confidence_band() to update a confidence band")
        old_x, old_y = target.x_data, target.y_data
        target.x_data = self._coerce_x_data(x_data)
        target.y_data = list(y_data)
        try:
            target.__post_init__()
            self._replace_series_or_redraw(index, redraw_axes)
        except Exception:
            target.x_data, target.y_data = old_x, old_y
            raise

    def set_confidence_band(
        self,
        series: int | str | Series,
        x_data: Sequence[float | date | datetime],
        lower_data: Sequence[Optional[float]],
        upper_data: Sequence[Optional[float]],
        *,
        redraw_axes: str | bool = "auto",
    ) -> None:
        if len(x_data) != len(lower_data) or len(x_data) != len(upper_data):
            raise ValueError("Confidence band x/lower/upper lengths differ")
        index = self._series_index(series)
        target = self._series[index]
        if target.chart_type != "band":
            raise ValueError("Target series is not a confidence band")
        old_x, old_lower, old_upper = target.x_data, target.y_data, target.upper_data
        target.x_data = self._coerce_x_data(x_data)
        target.y_data = list(lower_data)
        target.upper_data = list(upper_data)
        try:
            target.__post_init__()
            self._replace_series_or_redraw(index, redraw_axes)
        except Exception:
            target.x_data, target.y_data, target.upper_data = old_x, old_lower, old_upper
            raise

    def set_point(
        self,
        series: int | str | Series,
        point_index: int,
        *,
        x: Optional[float | date | datetime] = None,
        y: object = _UNSET,
        redraw_axes: str | bool = "auto",
    ) -> None:
        index = self._series_index(series)
        target = self._series[index]
        if not -len(target.x_data) <= point_index < len(target.x_data):
            raise IndexError("point index out of range")
        point_index %= len(target.x_data)
        old_x, old_y = target.x_data[point_index], target.y_data[point_index]
        if x is not None:
            target.x_data[point_index] = self._datetime_value(x)
        if y is not _UNSET:
            target.y_data[point_index] = y
        try:
            target.__post_init__()
            self._replace_series_or_redraw(index, redraw_axes)
        except Exception:
            target.x_data[point_index], target.y_data[point_index] = old_x, old_y
            raise

    def append_point(
        self,
        series: int | str | Series,
        x: float | date | datetime,
        y: Optional[float],
        *,
        max_points: Optional[int] = None,
        redraw_axes: str | bool = "auto",
    ) -> None:
        index = self._series_index(series)
        target = self._series[index]
        if target.chart_type == "band":
            raise ValueError("Use set_confidence_band() to update a confidence band")
        old_x, old_y = target.x_data[:], target.y_data[:]
        try:
            target.x_data.append(self._datetime_value(x))
            target.y_data.append(y)
            self._trim_series_to_max_points(target, max_points)
            target.__post_init__()
            self._replace_series_or_redraw(index, redraw_axes)
        except Exception:
            target.x_data, target.y_data = old_x, old_y
            raise

    def append_points(
        self,
        series: int | str | Series,
        x_data: Sequence[float | date | datetime],
        y_data: Sequence[Optional[float]],
        *,
        max_points: Optional[int] = None,
        redraw_axes: str | bool = "auto",
    ) -> None:
        if len(x_data) != len(y_data):
            raise ValueError("x/y lengths differ")
        index = self._series_index(series)
        target = self._series[index]
        if target.chart_type == "band":
            raise ValueError("Use set_confidence_band() to update a confidence band")
        old_x, old_y = target.x_data[:], target.y_data[:]
        try:
            target.x_data.extend(self._coerce_x_data(x_data))
            target.y_data.extend(y_data)
            self._trim_series_to_max_points(target, max_points)
            target.__post_init__()
            self._replace_series_or_redraw(index, redraw_axes)
        except Exception:
            target.x_data, target.y_data = old_x, old_y
            raise

    def shift_series(
        self,
        series: int | str | Series,
        *,
        dx: float = 0.0,
        dy: float = 0.0,
        redraw_axes: str | bool = "auto",
    ) -> None:
        index = self._series_index(series)
        target = self._series[index]
        old_x, old_y = target.x_data[:], target.y_data[:]
        old_upper = target.upper_data[:] if target.upper_data is not None else None
        target.x_data = [value + dx for value in target.x_data]
        target.y_data = [value + dy if _is_finite_number(value) else value for value in target.y_data]
        if target.upper_data is not None:
            target.upper_data = [value + dy if _is_finite_number(value) else value for value in target.upper_data]
        try:
            target.__post_init__()
            self._replace_series_or_redraw(index, redraw_axes)
        except Exception:
            target.x_data, target.y_data = old_x, old_y
            target.upper_data = old_upper
            raise

    def trim_series(
        self,
        series: int | str | Series,
        max_points: int,
        *,
        redraw_axes: str | bool = "auto",
    ) -> None:
        index = self._series_index(series)
        target = self._series[index]
        old_x, old_y = target.x_data[:], target.y_data[:]
        old_upper = target.upper_data[:] if target.upper_data is not None else None
        self._trim_series_to_max_points(target, max_points)
        try:
            target.__post_init__()
            self._replace_series_or_redraw(index, redraw_axes)
        except Exception:
            target.x_data, target.y_data = old_x, old_y
            target.upper_data = old_upper
            raise

    @staticmethod
    def _trim_series_to_max_points(series: Series, max_points: Optional[int]) -> None:
        if max_points is None:
            return
        if max_points <= 0:
            raise ValueError("max_points must be positive")
        if len(series.x_data) <= max_points:
            return
        series.x_data = series.x_data[-max_points:]
        series.y_data = series.y_data[-max_points:]
        if series.upper_data is not None:
            series.upper_data = series.upper_data[-max_points:]

    def _replace_series_or_redraw(self, index: int, redraw_axes: str | bool) -> None:
        if redraw_axes not in ("auto", True, False):
            raise ValueError("redraw_axes must be 'auto', True, or False")
        if self.coalesce:
            self.draw(coalesce=True)
            return
        if redraw_axes is True or self._last_ranges is None:
            self.draw()
            return

        next_ranges = self._calculate_ranges()
        if redraw_axes == "auto" and next_ranges != self._last_ranges:
            self.draw()
            return

        if not all(hasattr(self._canvas, name) for name in ("capture_commands", "replace_group")):
            self.draw()
            return

        x_min, x_max, y_min, y_max, y2_min, y2_max = self._last_ranges
        target = self._series[index]
        if target.stack is not None:
            self.draw()
            return
        ym, yM, log_y = (y2_min, y2_max, self.log_y2) if target.y_axis == 2 else (y_min, y_max, self.log_y)
        group = self._series_group(index)

        with self._canvas.capture_commands() as commands:
            with self._series_command_context(index):
                if target.chart_type == "heatmap":
                    self._draw_heatmap(target, x_min, x_max, ym, yM)
                elif target.chart_type == "band":
                    self._draw_confidence_band(target, x_min, x_max, ym, yM, log_y)
                elif target.chart_type == "bar":
                    axis_bars = [item for item in self._series if item.chart_type == "bar" and item.y_axis == target.y_axis]
                    self._draw_bar(target, x_min, x_max, ym, yM, log_y, axis_bars)
                elif target.chart_type == "area":
                    self._draw_area(target, x_min, x_max, ym, yM, log_y)
                else:
                    self._draw_line_series(target, x_min, x_max, ym, yM, log_y)
        self._canvas.replace_group(group, commands)

    def _draw_span_annotations(
        self,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
        y2_min: float,
        y2_max: float,
    ) -> None:
        for annotation in self._annotations:
            if annotation.kind == "xspan" and annotation.x is not None and annotation.x2 is not None:
                left = self._map_x(max(min(annotation.x, annotation.x2), x_min), x_min, x_max)
                right = self._map_x(min(max(annotation.x, annotation.x2), x_max), x_min, x_max)
                if right <= self._px0 or left >= self._px1:
                    continue
                x = max(self._px0, min(left, right))
                width = min(self._px1, max(left, right)) - x
                if width > 0:
                    self._canvas.fill_rect(x, self._py0, width, self._py1 - self._py0 + 1, annotation.fill or annotation.color)
                    if annotation.text:
                        self._canvas.text(x + 4, self._py0 + 6, annotation.text, color=annotation.color, size=annotation.size)
            elif annotation.kind == "yspan" and annotation.y is not None and annotation.y2 is not None:
                lo, hi = (y2_min, y2_max) if annotation.y_axis == 2 else (y_min, y_max)
                top = self._map_y(min(max(annotation.y, annotation.y2), hi), lo, hi, annotation.y_axis)
                bottom = self._map_y(max(min(annotation.y, annotation.y2), lo), lo, hi, annotation.y_axis)
                if bottom <= self._py0 or top >= self._py1:
                    continue
                y = max(self._py0, min(top, bottom))
                height = min(self._py1, max(top, bottom)) - y
                if height > 0:
                    self._canvas.fill_rect(self._px0, y, self._px1 - self._px0 + 1, height, annotation.fill or annotation.color)
                    if annotation.text:
                        self._canvas.text(self._px0 + 6, y + 4, annotation.text, color=annotation.color, size=annotation.size)

    def _draw_line_annotations(
        self,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
        y2_min: float,
        y2_max: float,
    ) -> None:
        for annotation in self._annotations:
            if annotation.kind == "vline" and annotation.x is not None:
                if annotation.x < x_min or annotation.x > x_max:
                    continue
                x = self._map_x(annotation.x, x_min, x_max)
                self._canvas.vline(x, self._py0, self._py1 - self._py0 + 1, annotation.color, annotation.width)
                if annotation.text:
                    self._canvas.text(min(x + 5, self._px1 - len(annotation.text) * self._CHAR_W), self._py0 + 8, annotation.text, color=annotation.color, size=annotation.size)
            elif annotation.kind == "hline" and annotation.y is not None:
                lo, hi = (y2_min, y2_max) if annotation.y_axis == 2 else (y_min, y_max)
                if annotation.y < lo or annotation.y > hi:
                    continue
                y = self._map_y(annotation.y, lo, hi, annotation.y_axis)
                self._canvas.hline(self._px0, y, self._px1 - self._px0 + 1, annotation.color, annotation.width)
                if annotation.text:
                    self._canvas.text(self._px0 + 6, max(self._py0 + 2, y - 18), annotation.text, color=annotation.color, size=annotation.size)
            elif annotation.kind == "point" and annotation.x is not None and annotation.y is not None:
                lo, hi = (y2_min, y2_max) if annotation.y_axis == 2 else (y_min, y_max)
                if annotation.x < x_min or annotation.x > x_max or annotation.y < lo or annotation.y > hi:
                    continue
                x = self._map_x(annotation.x, x_min, x_max)
                y = self._map_y(annotation.y, lo, hi, annotation.y_axis)
                self._canvas.fill_circle(x, y, 4, annotation.color)
                if annotation.text:
                    label_w = len(annotation.text) * self._CHAR_W * annotation.size + 8
                    label_h = self._CHAR_H * annotation.size + 6
                    lx = min(max(self._px0 + 2, x + 8), self._px1 - label_w - 2)
                    ly = min(max(self._py0 + 2, y - label_h - 4), self._py1 - label_h - 2)
                    if annotation.fill:
                        self._canvas.fill_rect(lx, ly, label_w, label_h, annotation.fill)
                        self._canvas.rect(lx, ly, label_w, label_h, annotation.color)
                    self._canvas.text(lx + 4, ly + 2, annotation.text, color=annotation.color, size=annotation.size)

    def _draw_title(self, st: GraphStyle, pw: int) -> None:
        if self.title:
            tx = max(self._gx0 + 4, self._px0 + (pw - len(self.title) * self._CHAR_W * 2) // 2)
            self._canvas.text(tx, self._gy0 + 10, self.title, color=st.title_color, size=2)

    def _draw_grid(self, x_min: float, x_max: float, y_min: float, y_max: float, st: GraphStyle) -> None:
        c = self._canvas
        pw = self._px1 - self._px0 + 1
        ph = self._py1 - self._py0 + 1
        if self.log_x:
            for value, major in _log_decade_ticks(x_min, x_max):
                gx = self._map_x(value, x_min, x_max)
                c.vline(gx, self._py0, ph, st.grid_color if major else st.minor_grid_color)
        else:
            for value in self._x_tick_values(x_min, x_max):
                gx = self._map_x(value, x_min, x_max)
                if self._px0 < gx < self._px1:
                    c.vline(gx, self._py0, ph, st.grid_color)
        if self.log_y:
            for value, major in _log_decade_ticks(y_min, y_max):
                gy = self._map_y(value, y_min, y_max, 1)
                c.hline(self._px0, gy, pw, st.grid_color if major else st.minor_grid_color)
        else:
            for value in self._y_tick_values(y_min, y_max, 1):
                gy = self._map_y(value, y_min, y_max, 1)
                if self._py0 < gy < self._py1:
                    c.hline(self._px0, gy, pw, st.grid_color)

    def _draw_zero_lines(self, x_min: float, x_max: float, y_min: float, y_max: float, st: GraphStyle) -> None:
        if not self.log_y and y_min < 0 < y_max:
            self._canvas.hline(self._px0, self._map_y(0, y_min, y_max, 1), self._px1 - self._px0 + 1, st.zero_color, 2)
        if not self.log_x and x_min < 0 < x_max:
            self._canvas.vline(self._map_x(0, x_min, x_max), self._py0, self._py1 - self._py0 + 1, st.zero_color, 2)

    def _draw_axes(self, st: GraphStyle, has_y2: bool, pw: int, ph: int) -> None:
        c = self._canvas
        c.rect(self._px0, self._py0, pw, ph, st.axis_color, 2)
        if has_y2:
            c.vline(self._px1, self._py0, ph, st.y2_axis_color, 2)

    def _draw_ticks(self, x_min: float, x_max: float, y_min: float, y_max: float, y2_min: float, y2_max: float, st: GraphStyle, has_y2: bool) -> None:
        self._draw_x_ticks(x_min, x_max, st)
        self._draw_y_ticks(y_min, y_max, st, 1)
        if has_y2:
            self._draw_y_ticks(y2_min, y2_max, st, 2)

    def _draw_x_ticks(self, x_min: float, x_max: float, st: GraphStyle) -> None:
        for value in self._x_tick_values(x_min, x_max):
            px = self._map_x(value, x_min, x_max)
            self._canvas.vline(px, self._py1, 6, st.axis_color)
            label = self._format_datetime_tick(value, x_max - x_min) if self._datetime_x else _fmt_num(value, self.log_x)
            lx = max(self._gx0 + 2, min(px - len(label) * 4, self._gx1 - len(label) * self._CHAR_W - 2))
            self._canvas.text(lx, self._py1 + 10, label, color=st.label_color, size=1)

    @staticmethod
    def _datetime_ticks(lo: float, hi: float, intervals: int) -> List[float]:
        target = max(1.0, (hi - lo) / max(1, intervals))
        steps = [
            1, 5, 15, 30, 60, 5 * 60, 15 * 60, 30 * 60,
            3600, 3 * 3600, 6 * 3600, 12 * 3600,
            86400, 2 * 86400, 7 * 86400, 14 * 86400,
            30 * 86400, 90 * 86400, 180 * 86400, 365 * 86400,
        ]
        step = min(steps, key=lambda candidate: abs(math.log(candidate / target)))
        first = math.ceil(lo / step) * step
        ticks = []
        value = first
        while value <= hi and len(ticks) < 100:
            ticks.append(value)
            value += step
        return ticks or [lo, hi]

    @staticmethod
    def _format_datetime_tick(value: float, span: float) -> str:
        moment = datetime.fromtimestamp(value, tz=timezone.utc)
        if span < 120:
            return moment.strftime("%H:%M:%S")
        if span < 2 * 86400:
            return moment.strftime("%H:%M")
        if span < 90 * 86400:
            return moment.strftime("%b %d")
        if span < 2 * 365 * 86400:
            return moment.strftime("%b %Y")
        return moment.strftime("%Y")

    def _draw_y_ticks(self, y_min: float, y_max: float, st: GraphStyle, axis: int) -> None:
        log_scale = self.log_y2 if axis == 2 else self.log_y
        for value in self._y_tick_values(y_min, y_max, axis):
            py = self._map_y(value, y_min, y_max, axis)
            label = _fmt_num(value, log_scale)
            if axis == 1:
                self._canvas.hline(self._px0 - 6, py, 6, st.axis_color)
                self._canvas.text(max(self._gx0 + 2, self._px0 - len(label) * 8 - 10), py - 7, label, color=st.label_color, size=1)
            else:
                self._canvas.hline(self._px1, py, 6, st.y2_axis_color)
                self._canvas.text(self._px1 + 10, py - 7, label, color=st.y2_axis_color, size=1)

    def _draw_axis_labels(self, st: GraphStyle, pw: int, has_y2: bool) -> None:
        if self.x_label:
            self._canvas.text(self._px0 + (pw - len(self.x_label) * self._CHAR_W) // 2, self._gy1 - 28, self.x_label, color=st.title_color, size=1)
        if self.y_label:
            self._canvas.text(self._gx0 + 8, self._py0 - 26, self.y_label, color=st.title_color, size=1)
        if has_y2 and self.y2_label:
            self._canvas.text(self._px1 - len(self.y2_label) * self._CHAR_W, self._py0 - 26, self.y2_label, color=st.y2_axis_color, size=1)

    def _draw_heatmap(self, series: Series, x_min: float, x_max: float, y_min: float, y_max: float) -> None:
        if series.z_data is None:
            return
        values = [value for row in series.z_data for value in row]
        z_min = min(values) if series.z_min is None else series.z_min
        z_max = max(values) if series.z_max is None else series.z_max
        if z_min == z_max:
            z_max = z_min + 1.0

        for row_index, row in enumerate(series.z_data):
            y0 = series.y_data[row_index]
            y1 = series.y_data[row_index + 1]
            if y1 < y_min or y0 > y_max:
                continue
            top = self._map_y(min(y1, y_max), y_min, y_max, series.y_axis)
            bottom = self._map_y(max(y0, y_min), y_min, y_max, series.y_axis)
            for column_index, value in enumerate(row):
                x0 = series.x_data[column_index]
                x1 = series.x_data[column_index + 1]
                if x1 < x_min or x0 > x_max:
                    continue
                left = self._map_x(max(x0, x_min), x_min, x_max)
                right = self._map_x(min(x1, x_max), x_min, x_max)
                x = max(self._px0, min(left, right))
                y = max(self._py0, min(top, bottom))
                width = min(self._px1, max(left, right)) - x + 1
                height = min(self._py1, max(top, bottom)) - y + 1
                if width <= 0 or height <= 0:
                    continue
                self._canvas.fill_rect(x, y, width, height, self._heatmap_color(value, z_min, z_max, series.color_map))
                if series.outline_color:
                    self._canvas.rect(x, y, width, height, series.outline_color)

    def _heatmap_color(self, value: float, z_min: float, z_max: float, color_map: Optional[List[str]]) -> str:
        colors = color_map or DEFAULT_HEATMAP_COLOURS
        if len(colors) == 1:
            return colors[0]
        t = _clamp((value - z_min) / (z_max - z_min), 0.0, 1.0)
        scaled = t * (len(colors) - 1)
        index = min(len(colors) - 2, int(math.floor(scaled)))
        frac = scaled - index
        return self._interpolate_color(colors[index], colors[index + 1], frac)

    @staticmethod
    def _interpolate_color(start: str, end: str, frac: float) -> str:
        sr, sg, sb = Graph._hex_to_rgb(start)
        er, eg, eb = Graph._hex_to_rgb(end)
        return "#{:02X}{:02X}{:02X}".format(
            round(sr + (er - sr) * frac),
            round(sg + (eg - sg) * frac),
            round(sb + (eb - sb) * frac),
        )

    @staticmethod
    def _hex_to_rgb(color: str) -> Tuple[int, int, int]:
        value = color.strip()
        if not value.startswith("#"):
            raise ValueError("Heatmap color_map colors must be #RGB or #RRGGBB hex strings")
        value = value[1:]
        if len(value) == 3:
            value = "".join(ch * 2 for ch in value)
        if len(value) != 6:
            raise ValueError("Heatmap color_map colors must be #RGB or #RRGGBB hex strings")
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)

    def _draw_line_series(self, series: Series, x_min: float, x_max: float, y_min: float, y_max: float, log_y: bool) -> None:
        segments = self._series_segments(series, x_min, x_max, y_min, y_max, log_y)
        for points in segments:
            if series.draw_line and len(points) >= 2:
                line_points = self._spline_points(points, series.spline_resolution) if series.spline else points
                self._draw_styled_path(line_points, series, series.color)
            if not series.draw_markers:
                continue
            for x, y in points:
                self._canvas.fill_circle(x, y, series.marker_radius, series.color)

    @staticmethod
    def _dash_for_series(series: Series) -> List[float]:
        if series.dash_pattern is not None:
            return series.dash_pattern
        return {
            "solid": [],
            "dashed": [9.0, 6.0],
            "dotted": [2.0, 5.0],
            "dashdot": [9.0, 5.0, 2.0, 5.0],
        }[series.line_style]

    def _draw_styled_path(self, points: Sequence[Tuple[int, int]], series: Series, color: str) -> None:
        try:
            self._canvas.path(
                points,
                color,
                series.line_width,
                line_cap=series.line_cap,
                line_join="round",
                dash=self._dash_for_series(series),
            )
        except TypeError:
            self._canvas.path(points, color, series.line_width)

    def _spline_points(self, points: Sequence[Tuple[int, int]], resolution: int) -> List[Tuple[int, int]]:
        """Return a Catmull-Rom spline that passes through each plotted point."""
        if len(points) < 3:
            return list(points)

        result: List[Tuple[int, int]] = [points[0]]
        for index in range(len(points) - 1):
            p0 = points[max(0, index - 1)]
            p1 = points[index]
            p2 = points[index + 1]
            p3 = points[min(len(points) - 1, index + 2)]
            for step in range(1, resolution + 1):
                t = step / resolution
                t2 = t * t
                t3 = t2 * t
                x = 0.5 * (
                    2 * p1[0]
                    + (-p0[0] + p2[0]) * t
                    + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                    + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3
                )
                y = 0.5 * (
                    2 * p1[1]
                    + (-p0[1] + p2[1]) * t
                    + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                    + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3
                )
                point = (
                    max(self._px0, min(self._px1, round(x))),
                    max(self._py0, min(self._py1, round(y))),
                )
                if point != result[-1]:
                    result.append(point)
        return result

    def _draw_bar(
        self,
        series: Series,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
        log_y: bool,
        bar_series: Sequence[Series],
    ) -> None:
        n = len(series.x_data)
        cluster_w = (self._px1 - self._px0) / max(n, 1)
        bar_total = max(2, round(cluster_w * (1.0 - series.bar_gap)))
        lane_keys: List[Tuple[str, object]] = []
        for item in bar_series:
            key = ("stack", item.stack) if item.stack is not None else ("series", id(item))
            if key not in lane_keys:
                lane_keys.append(key)
        target_key = ("stack", series.stack) if series.stack is not None else ("series", id(series))
        lane_index = lane_keys.index(target_key)
        bar_w = max(2, bar_total // max(len(lane_keys), 1))
        for x_value, y_value in zip(series.x_data, series.y_data):
            if not _is_finite_number(y_value):
                continue
            if self.log_x and x_value <= 0:
                continue
            if log_y and y_value <= 0:
                continue
            baseline = self._stack_baseline(series, x_value, y_value)
            x_center = self._map_x(x_value, x_min, x_max)
            x = x_center - bar_total // 2 + lane_index * bar_w
            y_base = self._map_y(max(y_min, min(y_max, baseline)), y_min, y_max, series.y_axis)
            y_top = self._map_y(max(y_min, min(y_max, baseline + y_value)), y_min, y_max, series.y_axis)
            y = min(y_top, y_base)
            h = max(1, abs(y_base - y_top))
            clipped = self._clip_rect_to_plot(x, y, bar_w, h)
            if clipped is None:
                continue
            cx, cy, cw, ch = clipped
            self._canvas.fill_rect(cx, cy, cw, ch, series.color)
            self._canvas.rect(cx, cy, cw, ch, series.outline_color or series.color)

    def _stack_baseline(self, series: Series, x_value: float, y_value: float) -> float:
        if series.stack is None:
            return 0.0
        baseline = 0.0
        for previous in self._series:
            if previous is series:
                break
            if previous.chart_type != series.chart_type or previous.y_axis != series.y_axis or previous.stack != series.stack:
                continue
            for previous_x, previous_y in zip(previous.x_data, previous.y_data):
                if not _is_finite_number(previous_y):
                    continue
                if previous_x == x_value and (previous_y >= 0) == (y_value >= 0):
                    baseline += previous_y
                    break
        return baseline

    def _draw_area(self, series: Series, x_min: float, x_max: float, y_min: float, y_max: float, log_y: bool) -> None:
        segments: List[Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]] = []
        upper: List[Tuple[int, int]] = []
        lower: List[Tuple[int, int]] = []
        for x_value, y_value in zip(series.x_data, series.y_data):
            valid = _is_finite_number(y_value) and not (self.log_x and x_value <= 0) and not (log_y and y_value <= 0)
            if not valid:
                if upper:
                    segments.append((upper, lower))
                    upper, lower = [], []
                continue
            baseline = self._stack_baseline(series, x_value, y_value)
            x = max(self._px0, min(self._px1, self._map_x(x_value, x_min, x_max)))
            lower_value = max(y_min, min(y_max, baseline))
            upper_value = max(y_min, min(y_max, baseline + y_value))
            lower_y = max(self._py0, min(self._py1, self._map_y(lower_value, y_min, y_max, series.y_axis)))
            upper_y = max(self._py0, min(self._py1, self._map_y(upper_value, y_min, y_max, series.y_axis)))
            lower.append((x, lower_y))
            upper.append((x, upper_y))
        if upper:
            segments.append((upper, lower))
        for upper, lower in segments:
            self._draw_filled_segment(upper, lower, series.color)
            if len(upper) >= 2:
                self._draw_styled_path(upper, series, series.outline_color or series.color)
            if series.draw_markers:
                for x, y in upper:
                    self._canvas.fill_circle(x, y, series.marker_radius, series.outline_color or series.color)

    def _draw_confidence_band(self, series: Series, x_min: float, x_max: float, y_min: float, y_max: float, log_y: bool) -> None:
        if series.upper_data is None:
            return
        segments: List[Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]] = []
        upper_points: List[Tuple[int, int]] = []
        lower_points: List[Tuple[int, int]] = []
        for x_value, lower_value, upper_value in zip(series.x_data, series.y_data, series.upper_data):
            valid = (
                _is_finite_number(lower_value)
                and _is_finite_number(upper_value)
                and not (self.log_x and x_value <= 0)
                and not (log_y and (lower_value <= 0 or upper_value <= 0))
            )
            if not valid:
                if upper_points:
                    segments.append((upper_points, lower_points))
                    upper_points, lower_points = [], []
                continue
            x = max(self._px0, min(self._px1, self._map_x(x_value, x_min, x_max)))
            lower_y = max(self._py0, min(self._py1, self._map_y(lower_value, y_min, y_max, series.y_axis)))
            upper_y = max(self._py0, min(self._py1, self._map_y(upper_value, y_min, y_max, series.y_axis)))
            lower_points.append((x, lower_y))
            upper_points.append((x, upper_y))
        if upper_points:
            segments.append((upper_points, lower_points))
        for upper_points, lower_points in segments:
            self._draw_filled_segment(upper_points, lower_points, series.fill_color or series.color)
            if len(upper_points) >= 2:
                self._draw_styled_path(upper_points, series, series.color)
                self._draw_styled_path(lower_points, series, series.color)

    def _draw_filled_segment(
        self,
        upper: Sequence[Tuple[int, int]],
        lower: Sequence[Tuple[int, int]],
        color: str,
    ) -> None:
        if len(upper) < 2:
            return
        for ((x0, y0), (x1, y1)), ((_, base0), (_, base1)) in zip(zip(upper, upper[1:]), zip(lower, lower[1:])):
            if x0 == x1:
                self._plot_vline(x0, min(y0, y1, base0, base1), max(y0, y1, base0, base1), color)
                continue
            left, right = sorted((x0, x1))
            for x in range(left, right + 1):
                t = (x - x0) / (x1 - x0)
                y = round(y0 + t * (y1 - y0))
                base = round(base0 + t * (base1 - base0))
                self._plot_vline(x, min(y, base), max(y, base), color)

    def _series_segments(self, series: Series, x_min: float, x_max: float, y_min: float, y_max: float, log_y: bool) -> List[List[Tuple[int, int]]]:
        segments: List[List[Tuple[int, int]]] = []
        points: List[Tuple[int, int]] = []
        for x_value, y_value in zip(series.x_data, series.y_data):
            valid = _is_finite_number(y_value) and not (self.log_x and x_value <= 0) and not (log_y and y_value <= 0)
            if not valid:
                if points:
                    segments.append(points)
                    points = []
                continue
            x = max(self._px0, min(self._px1, self._map_x(x_value, x_min, x_max)))
            y = max(self._py0, min(self._py1, self._map_y(y_value, y_min, y_max, series.y_axis)))
            points.append((x, y))
        if points:
            segments.append(points)
        return segments

    def _clip_rect_to_plot(self, x: float, y: float, width: float, height: float) -> Optional[Tuple[int, int, int, int]]:
        left = max(self._px0 + 1, round(x))
        top = max(self._py0 + 1, round(y))
        right = min(self._px1 - 1, round(x + width))
        bottom = min(self._py1 - 1, round(y + height))
        if right <= left or bottom <= top:
            return None
        return left, top, right - left, bottom - top

    def _plot_vline(self, x: float, y0: float, y1: float, color: str) -> None:
        px = round(x)
        if px <= self._px0 or px >= self._px1:
            return
        top = max(self._py0 + 1, round(min(y0, y1)))
        bottom = min(self._py1 - 1, round(max(y0, y1)))
        if bottom < top:
            return
        self._canvas.vline(px, top, bottom - top + 1, color)

    def _draw_legend(self, st: GraphStyle, has_y2: bool) -> None:
        labelled = [s for s in self._series if s.label]
        if not labelled:
            return
        max_len = max(len(s.label) for s in labelled)
        box_w = 28 + max_len * self._CHAR_W + (28 if has_y2 else 0)
        box_h = 22 * len(labelled) + 10
        x = self._px1 - box_w - 10
        y = self._py0 + 10
        if x < self._px0 + 12:
            return
        self._canvas.fill_rect(x, y, box_w, box_h, st.legend_bg_color)
        self._canvas.rect(x, y, box_w, box_h, st.axis_color)
        for index, series in enumerate(labelled):
            iy = y + 8 + index * 22
            self._canvas.fill_rect(x + 8, iy + 3, 14, 8, series.color)
            suffix = f" Y{series.y_axis}" if has_y2 else ""
            self._canvas.text(x + 28, iy, series.label + suffix, color=st.label_color, size=1)

    def _map_x(self, value: float, x_min: float, x_max: float) -> int:
        if self.log_x:
            lo, hi = _safe_log10(x_min), _safe_log10(x_max)
            t = (_safe_log10(value) - lo) / (hi - lo)
        else:
            t = (value - x_min) / (x_max - x_min)
        return round(self._px0 + t * (self._px1 - self._px0))

    def _map_y(self, value: float, y_min: float, y_max: float, axis: int) -> int:
        log_scale = self.log_y2 if axis == 2 else self.log_y
        if log_scale:
            lo, hi = _safe_log10(y_min), _safe_log10(y_max)
            t = (_safe_log10(value) - lo) / (hi - lo)
        else:
            t = (value - y_min) / (y_max - y_min)
        return round(self._py1 - t * (self._py1 - self._py0))


@dataclass
class PolarStyle:
    bg_color: str = "#F8FAFC"
    plot_bg_color: str = "#FFFFFF"
    grid_color: str = "#CBD5E1"
    axis_color: str = "#94A3B8"
    label_color: str = "#475569"
    title_color: str = "#0F172A"
    legend_bg_color: str = "#F8FAFC"


@dataclass
class PolarSeries:
    values: List[float]
    color: str
    label: str = ""
    fill: Optional[str] = None
    draw_markers: bool = True
    marker_radius: int = 4


class PolarChart:
    """Radar chart drawn in polar coordinates over evenly spaced category axes."""

    _CHAR_W = 8

    def __init__(
        self,
        canvas,
        categories: Sequence[str],
        *,
        title: str = "",
        minimum: float = 0.0,
        maximum: Optional[float] = None,
        levels: int = 5,
        start_angle: float = -90.0,
        style: Optional[PolarStyle] = None,
        x: int = 0,
        y: int = 0,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> None:
        if len(categories) < 3:
            raise ValueError("PolarChart requires at least three categories")
        if levels <= 0:
            raise ValueError("levels must be positive")
        self._canvas = canvas
        self.categories = [str(category) for category in categories]
        self.title = title
        self.minimum = float(minimum)
        self.maximum = float(maximum) if maximum is not None else None
        self.levels = levels
        self.start_angle = start_angle
        self.style = style or PolarStyle()
        self.x = round(x)
        self.y = round(y)
        self.width = round(width if width is not None else canvas.width - x)
        self.height = round(height if height is not None else canvas.height - y)
        self._series: List[PolarSeries] = []
        if self.width <= 0 or self.height <= 0:
            raise ValueError("PolarChart width and height must be positive")

    def add_series(
        self,
        values: Sequence[float],
        *,
        color: Optional[str] = None,
        fill: Optional[str] = None,
        label: str = "",
        draw_markers: bool = True,
        marker_radius: int = 4,
    ) -> "PolarChart":
        if len(values) != len(self.categories):
            raise ValueError("Polar series length must match categories")
        converted = [float(value) for value in values]
        self._series.append(PolarSeries(
            converted,
            color or DEFAULT_COLOURS[len(self._series) % len(DEFAULT_COLOURS)],
            label,
            fill,
            draw_markers,
            marker_radius,
        ))
        return self

    def draw(self) -> None:
        if not self._series:
            raise ValueError("No polar series added")
        maximum = self.maximum
        if maximum is None:
            maximum = max(value for series in self._series for value in series.values)
        if maximum <= self.minimum:
            raise ValueError("PolarChart maximum must be greater than minimum")

        c = self._canvas
        st = self.style
        c.fill_rect(self.x, self.y, self.width, self.height, st.bg_color)
        title_space = 36 if self.title else 14
        legend_space = 28 * len([series for series in self._series if series.label])
        cx = self.x + self.width / 2
        cy = self.y + title_space + (self.height - title_space - legend_space) / 2
        radius = max(20.0, min(self.width * 0.36, (self.height - title_space - legend_space) * 0.38))
        c.fill_circle(cx, cy, radius, st.plot_bg_color)
        if self.title:
            c.text(self.x + max(8, (self.width - len(self.title) * self._CHAR_W * 2) // 2), self.y + 8, self.title, color=st.title_color, size=2)

        angles = [self.start_angle + 360.0 * index / len(self.categories) for index in range(len(self.categories))]
        for level in range(1, self.levels + 1):
            ring = [self._point(cx, cy, radius * level / self.levels, angle) for angle in angles]
            c.path(ring + [ring[0]], st.grid_color, 1)
        for category, angle in zip(self.categories, angles):
            endpoint = self._point(cx, cy, radius, angle)
            c.line(cx, cy, endpoint[0], endpoint[1], st.axis_color)
            lx, ly = self._point(cx, cy, radius + 16, angle)
            lx -= len(category) * self._CHAR_W // 2
            ly -= 7
            c.text(lx, ly, category, color=st.label_color, size=1)

        for series in self._series:
            points = [
                self._point(cx, cy, radius * _clamp((value - self.minimum) / (maximum - self.minimum), 0.0, 1.0), angle)
                for value, angle in zip(series.values, angles)
            ]
            if series.fill:
                self._fill_polygon(points, series.fill)
            c.path(points + [points[0]], series.color, 3)
            if series.draw_markers:
                for px, py in points:
                    c.fill_circle(px, py, series.marker_radius, series.color)
        self._draw_legend(cy + radius + 24)

    @staticmethod
    def _point(cx: float, cy: float, radius: float, angle: float) -> Tuple[int, int]:
        radians = math.radians(angle)
        return round(cx + math.cos(radians) * radius), round(cy + math.sin(radians) * radius)

    def _fill_polygon(self, points: Sequence[Tuple[int, int]], color: str) -> None:
        min_y = min(point[1] for point in points)
        max_y = max(point[1] for point in points)
        edges = list(zip(points, points[1:] + points[:1]))
        for y in range(min_y, max_y + 1):
            intersections = []
            for (x0, y0), (x1, y1) in edges:
                if y0 == y1 or y < min(y0, y1) or y >= max(y0, y1):
                    continue
                intersections.append(round(x0 + (y - y0) * (x1 - x0) / (y1 - y0)))
            intersections.sort()
            for left, right in zip(intersections[::2], intersections[1::2]):
                self._canvas.hline(left, y, right - left + 1, color)

    def _draw_legend(self, y: float) -> None:
        labelled = [series for series in self._series if series.label]
        for index, series in enumerate(labelled):
            row_y = round(y + index * 22)
            self._canvas.fill_rect(self.x + 12, row_y + 3, 14, 8, series.color)
            self._canvas.text(self.x + 34, row_y, series.label, color=self.style.label_color, size=1)


RadarChart = PolarChart
