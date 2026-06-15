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
from dataclasses import dataclass
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


@dataclass
class Series:
    x_data: List[float]
    y_data: List[float]
    color: str = "#06B6D4"
    label: str = ""
    draw_line: bool = True
    draw_markers: bool = True
    marker_radius: int = 4
    y_axis: int = 1
    chart_type: str = "line"
    outline_color: Optional[str] = None
    bar_gap: float = 0.18

    def __post_init__(self) -> None:
        if len(self.x_data) != len(self.y_data):
            raise ValueError(f"Series {self.label!r}: x/y lengths differ")
        if not self.x_data:
            raise ValueError(f"Series {self.label!r}: data must not be empty")
        if self.y_axis not in (1, 2):
            raise ValueError("y_axis must be 1 or 2")
        if self.chart_type not in ("line", "bar", "area"):
            raise ValueError("chart_type must be 'line', 'bar', or 'area'")


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
        x_min: Optional[float] = None,
        x_max: Optional[float] = None,
        y_min: Optional[float] = None,
        y_max: Optional[float] = None,
        y2_min: Optional[float] = None,
        y2_max: Optional[float] = None,
        log_x: bool = False,
        log_y: bool = False,
        log_y2: bool = False,
        style: Optional[GraphStyle] = None,
        x: int = 0,
        y: int = 0,
        width: Optional[int] = None,
        height: Optional[int] = None,
        margin_left: Optional[int] = None,
        margin_bottom: Optional[int] = None,
        margin_top: Optional[int] = None,
        margin_right: Optional[int] = None,
    ) -> None:
        self._canvas = canvas
        self.title = title
        self.x_label = x_label
        self.y_label = y_label
        self.y2_label = y2_label
        self.x_min = x_min
        self.x_max = x_max
        self.y_min = y_min
        self.y_max = y_max
        self.y2_min = y2_min
        self.y2_max = y2_max
        self.log_x = log_x
        self.log_y = log_y
        self.log_y2 = log_y2
        self.style = style or GraphStyle()
        self._series: List[Series] = []

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

    def add_series(
        self,
        x_data: Sequence[float],
        y_data: Sequence[float],
        *,
        color: Optional[str] = None,
        label: str = "",
        draw_line: bool = True,
        draw_markers: bool = True,
        marker_radius: int = 4,
        y_axis: int = 1,
    ) -> "Graph":
        self._series.append(Series(
            list(x_data), list(y_data),
            color or DEFAULT_COLOURS[len(self._series) % len(DEFAULT_COLOURS)],
            label, draw_line, draw_markers, marker_radius, y_axis, "line",
        ))
        return self

    def add_bar_series(
        self,
        x_data: Sequence[float],
        y_data: Sequence[float],
        *,
        color: Optional[str] = None,
        outline_color: Optional[str] = None,
        label: str = "",
        bar_gap: float = 0.18,
        y_axis: int = 1,
    ) -> "Graph":
        self._series.append(Series(
            list(x_data), list(y_data),
            color or DEFAULT_COLOURS[len(self._series) % len(DEFAULT_COLOURS)],
            label, False, False, 0, y_axis, "bar", outline_color, bar_gap,
        ))
        return self

    def add_area_series(
        self,
        x_data: Sequence[float],
        y_data: Sequence[float],
        *,
        color: Optional[str] = None,
        outline_color: Optional[str] = None,
        label: str = "",
        draw_markers: bool = False,
        marker_radius: int = 4,
        y_axis: int = 1,
    ) -> "Graph":
        self._series.append(Series(
            list(x_data), list(y_data),
            color or DEFAULT_COLOURS[len(self._series) % len(DEFAULT_COLOURS)],
            label, True, draw_markers, marker_radius, y_axis, "area", outline_color,
        ))
        return self

    def draw(self) -> None:
        if not self._series:
            raise ValueError("No series added")

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
        y1_series = [s for s in self._series if s.y_axis == 1]
        y2_series = [s for s in self._series if s.y_axis == 2]
        bar_series = [s for s in self._series if s.chart_type == "bar"]
        all_x = [v for s in self._series for v in s.x_data]
        all_y1 = [v for s in y1_series for v in s.y_data] or [0, 1]
        all_y2 = [v for s in y2_series for v in s.y_data] or [0, 1]

        x_min, x_max = _log_axis_range(all_x, self.x_min, self.x_max) if self.log_x else _linear_axis_range(all_x, self.x_min, self.x_max)
        if bar_series and not self.log_x:
            pad = _bar_axis_padding(bar_series)
            if self.x_min is None:
                x_min = min(x_min, min(all_x) - pad)
            if self.x_max is None:
                x_max = max(x_max, max(all_x) + pad)
        y_min, y_max = _log_axis_range(all_y1, self.y_min, self.y_max) if self.log_y else _linear_axis_range(all_y1, self.y_min, self.y_max)
        y2_min, y2_max = _log_axis_range(all_y2, self.y2_min, self.y2_max) if self.log_y2 else _linear_axis_range(all_y2, self.y2_min, self.y2_max)

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

        for chart_type in ("area", "bar", "line"):
            for series in [s for s in self._series if s.chart_type == chart_type]:
                ym, yM, log_y = (y2_min, y2_max, self.log_y2) if series.y_axis == 2 else (y_min, y_max, self.log_y)
                if chart_type == "bar":
                    self._draw_bar(series, x_min, x_max, ym, yM, log_y, bar_series.index(series), len(bar_series))
                elif chart_type == "area":
                    self._draw_area(series, x_min, x_max, ym, yM, log_y)
                else:
                    self._draw_line_series(series, x_min, x_max, ym, yM, log_y)

        self._draw_axes(st, bool(y2_series), pw, ph)
        self._draw_legend(st, bool(y2_series))

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
            for i in range(1, st.grid_x):
                c.vline(self._px0 + round(pw * i / st.grid_x), self._py0, ph, st.grid_color)
        if self.log_y:
            for value, major in _log_decade_ticks(y_min, y_max):
                gy = self._map_y(value, y_min, y_max, 1)
                c.hline(self._px0, gy, pw, st.grid_color if major else st.minor_grid_color)
        else:
            for i in range(1, st.grid_y):
                c.hline(self._px0, self._py0 + round(ph * i / st.grid_y), pw, st.grid_color)

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
        ticks = [(v, True) for v in [x_min + (x_max - x_min) * i / st.grid_x for i in range(st.grid_x + 1)]]
        if self.log_x:
            ticks = [(v, major) for v, major in _log_decade_ticks(x_min, x_max) if major]
        for value, _ in ticks:
            px = self._map_x(value, x_min, x_max)
            self._canvas.vline(px, self._py1, 6, st.axis_color)
            label = _fmt_num(value, self.log_x)
            lx = max(self._gx0 + 2, min(px - len(label) * 4, self._gx1 - len(label) * self._CHAR_W - 2))
            self._canvas.text(lx, self._py1 + 10, label, color=st.label_color, size=1)

    def _draw_y_ticks(self, y_min: float, y_max: float, st: GraphStyle, axis: int) -> None:
        log_scale = self.log_y2 if axis == 2 else self.log_y
        ticks = [(v, True) for v in [y_min + (y_max - y_min) * i / st.grid_y for i in range(st.grid_y + 1)]]
        if log_scale:
            ticks = [(v, major) for v, major in _log_decade_ticks(y_min, y_max) if major]
        for value, _ in ticks:
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

    def _draw_line_series(self, series: Series, x_min: float, x_max: float, y_min: float, y_max: float, log_y: bool) -> None:
        points = self._series_points(series, x_min, x_max, y_min, y_max, log_y)
        if series.draw_line and len(points) >= 2:
            self._canvas.path(points, series.color, 3)
        if series.draw_markers:
            for x, y in points:
                self._canvas.fill_circle(x, y, series.marker_radius, series.color)

    def _draw_bar(self, series: Series, x_min: float, x_max: float, y_min: float, y_max: float, log_y: bool, bar_index: int, n_bars: int) -> None:
        n = len(series.x_data)
        cluster_w = (self._px1 - self._px0) / max(n, 1)
        bar_total = max(2, round(cluster_w * (1.0 - series.bar_gap)))
        bar_w = max(2, bar_total // max(n_bars, 1))
        zero = max(y_min, min(0.0, y_max))
        y_zero = self._map_y(zero, y_min, y_max, series.y_axis)
        for x_value, y_value in zip(series.x_data, series.y_data):
            if self.log_x and x_value <= 0:
                continue
            if log_y and y_value <= 0:
                continue
            x_center = self._map_x(x_value, x_min, x_max)
            x = x_center - bar_total // 2 + bar_index * bar_w
            y_top = self._map_y(y_value, y_min, y_max, series.y_axis)
            y = min(y_top, y_zero)
            h = max(1, abs(y_zero - y_top))
            clipped = self._clip_rect_to_plot(x, y, bar_w, h)
            if clipped is None:
                continue
            cx, cy, cw, ch = clipped
            self._canvas.fill_rect(cx, cy, cw, ch, series.color)
            self._canvas.rect(cx, cy, cw, ch, series.outline_color or series.color)

    def _draw_area(self, series: Series, x_min: float, x_max: float, y_min: float, y_max: float, log_y: bool) -> None:
        points = self._series_points(series, x_min, x_max, y_min, y_max, log_y)
        if len(points) < 2:
            return
        zero = max(y_min, min(0.0, y_max))
        y_zero = self._map_y(zero, y_min, y_max, series.y_axis)
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            if x0 == x1:
                self._plot_vline(x0, min(y0, y1, y_zero), max(y0, y1, y_zero), series.color)
                continue
            left, right = sorted((x0, x1))
            for x in range(left, right + 1):
                t = (x - x0) / (x1 - x0)
                y = round(y0 + t * (y1 - y0))
                self._plot_vline(x, min(y, y_zero), max(y, y_zero), series.color)
        self._canvas.path(points, series.outline_color or series.color, 3)
        if series.draw_markers:
            for x, y in points:
                self._canvas.fill_circle(x, y, series.marker_radius, series.outline_color or series.color)

    def _series_points(self, series: Series, x_min: float, x_max: float, y_min: float, y_max: float, log_y: bool) -> List[Tuple[int, int]]:
        points: List[Tuple[int, int]] = []
        for x_value, y_value in zip(series.x_data, series.y_data):
            if self.log_x and x_value <= 0:
                continue
            if log_y and y_value <= 0:
                continue
            x = max(self._px0, min(self._px1, self._map_x(x_value, x_min, x_max)))
            y = max(self._py0, min(self._py1, self._map_y(y_value, y_min, y_max, series.y_axis)))
            points.append((x, y))
        return points

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
