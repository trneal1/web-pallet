"""
echarts_graph_lib.py

Python-side helper library for driving Apache ECharts in the web pallet through
the existing TCP-to-WebSocket bridge.

This version provides three layers:

1. High-level helpers:
       pallet.gauge(...)
       pallet.line_chart(...)
       pallet.line_chart_2x2y(...)

2. Builder-style API:
       chart = pallet.multi_axis_line_chart(...)
       chart.add_line(...)
       chart.render()

3. Raw ECharts escape hatch:
       pallet.chart(id="raw", option={...})

Browser:
    Run bridge.py, open pallet.html, and connect it to ws://localhost:8080.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Deque, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from pallet import DEFAULT_BRIDGE_HOST, DEFAULT_BRIDGE_PORT, Pallet


JsonObject = Dict[str, Any]
UiEventHandler = Callable[[JsonObject], None]


def _clean_dict(data: JsonObject) -> JsonObject:
    return {k: v for k, v in data.items() if v is not None}


def _merge_dict(base: JsonObject, extra: Optional[JsonObject]) -> JsonObject:
    if not extra:
        return base
    out = dict(base)
    out.update(extra)
    return out


def _list(value: Optional[Sequence[Any]]) -> List[Any]:
    return list(value) if value is not None else []


@dataclass
class Axis:
    """Friendly Python description of an ECharts axis.

    name:
        Human-readable axis name, for example "Time" or "Voltage".

    data:
        Category labels for category axes. Use this for time strings,
        sample numbers, channel labels, etc.

    kind:
        "category", "value", "time", or "log".

    position:
        For x axes: "bottom" or "top".
        For y axes: "left" or "right".

    units:
        Optional units appended to the axis display name.

    offset:
        Pixel offset when multiple axes are on the same side.

    min/max:
        Optional numeric axis limits.

    extra:
        Optional raw ECharts axis fields when you need an escape hatch.
    """

    name: str
    data: Optional[Sequence[Any]] = None
    kind: str = "category"
    position: Optional[str] = None
    units: str = ""
    offset: Optional[int] = None
    min: Optional[float] = None
    max: Optional[float] = None
    inverse: bool = False
    extra: Optional[JsonObject] = None

    def label(self) -> str:
        if self.units:
            return f"{self.name} ({self.units})"
        return self.name

    def to_echarts(self) -> JsonObject:
        axis: JsonObject = {
            "type": self.kind,
            "name": self.label(),
        }
        if self.position:
            axis["position"] = self.position
        if self.data is not None:
            axis["data"] = list(self.data)
        if self.offset is not None:
            axis["offset"] = self.offset
        if self.min is not None:
            axis["min"] = self.min
        if self.max is not None:
            axis["max"] = self.max
        if self.inverse:
            axis["inverse"] = True
        if self.extra:
            axis.update(self.extra)
        return axis


@dataclass
class LineSeries:
    """Friendly Python description of a line series."""

    name: str
    data: Sequence[Any]
    x_axis: Union[str, int] = 0
    y_axis: Union[str, int] = 0
    smooth: bool = False
    area: bool = False
    show_symbols: bool = False
    step: Optional[Union[str, bool]] = None
    extra: Optional[JsonObject] = None

    def to_echarts(self, x_index: int, y_index: int) -> JsonObject:
        series: JsonObject = {
            "name": self.name,
            "type": "line",
            "xAxisIndex": x_index,
            "yAxisIndex": y_index,
            "smooth": self.smooth,
            "showSymbol": self.show_symbols,
            "data": list(self.data),
        }
        if self.area:
            series["areaStyle"] = {}
        if self.step is not None:
            series["step"] = self.step
        if self.extra:
            series.update(self.extra)
        return series


@dataclass
class ChartHandle:
    pallet: "EChartsPallet"
    id: str
    page: Optional[str] = None

    def set_option(
        self,
        option: JsonObject,
        *,
        merge: bool = True,
        lazy_update: bool = False,
        coalesce: bool = False,
        page: Optional[str] = None,
    ) -> None:
        self.pallet.set_option(
            self.id,
            option,
            merge=merge,
            lazy_update=lazy_update,
            coalesce=coalesce,
            page=self.page if page is None else page,
        )

    def set_data(self, data: Any, *, series_index: int = 0, page: Optional[str] = None) -> None:
        self.pallet.set_data(
            self.id,
            data,
            series_index=series_index,
            page=self.page if page is None else page,
        )

    def append_data(self, data: Any, *, series_index: int = 0, page: Optional[str] = None) -> None:
        self.pallet.append_data(
            self.id,
            data,
            series_index=series_index,
            page=self.page if page is None else page,
        )

    def resize(
        self,
        *,
        x: Optional[int] = None,
        y: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        page: Optional[str] = None,
    ) -> None:
        self.pallet.resize_chart(
            self.id,
            x=x,
            y=y,
            width=width,
            height=height,
            page=self.page if page is None else page,
        )

    def remove(self, *, page: Optional[str] = None) -> None:
        self.pallet.remove_chart(self.id, page=self.page if page is None else page)


@dataclass(frozen=True)
class TimeChartSeries:
    """One named series in a periodically updated time chart."""

    name: str
    kind: str = "line"
    smooth: bool = False
    color: Optional[str] = None
    extra: Optional[JsonObject] = None

    def to_echarts(self, data: Sequence[Any]) -> JsonObject:
        if self.kind not in ("line", "bar"):
            raise ValueError(f"Time series {self.name!r} kind must be 'line' or 'bar'")
        series: JsonObject = {
            "id": self.name,
            "name": self.name,
            "type": self.kind,
            "data": list(data),
        }
        if self.kind == "line":
            series.update({"smooth": self.smooth, "showSymbol": False})
        else:
            series["barMaxWidth"] = 28
        if self.color:
            series["color"] = self.color
        if self.extra:
            series.update(self.extra)
        return series


def _echarts_time_value(value: Union[datetime, int, float]) -> Union[int, float]:
    """Convert datetimes and Unix seconds to ECharts epoch milliseconds."""
    if isinstance(value, datetime):
        return int(value.timestamp() * 1000)
    if not isinstance(value, (int, float)):
        raise TypeError("time chart timestamps must be datetime, int, or float values")
    # time.time() values are seconds; existing millisecond timestamps pass through.
    return value * 1000 if abs(value) < 100_000_000_000 else value


class LiveTimeChart:
    """Handle for a mixed line/bar chart with a shifting time window."""

    def __init__(
        self,
        pallet: "EChartsPallet",
        *,
        id: str,
        series: Sequence[TimeChartSeries],
        max_points: int,
        page: Optional[str],
        time_format: str,
    ) -> None:
        if max_points < 2:
            raise ValueError("max_points must be at least 2")
        if not series:
            raise ValueError("at least one time chart series is required")
        names = [item.name for item in series]
        if len(names) != len(set(names)):
            raise ValueError("time chart series names must be unique")

        self.pallet = pallet
        self.id = id
        self.series = list(series)
        self.max_points = max_points
        self.page = page
        self.time_format = time_format
        self._times: Deque[Union[int, float]] = deque(maxlen=max_points)
        self._data: Dict[str, Deque[Optional[float]]] = {
            item.name: deque(maxlen=max_points) for item in self.series
        }

    def _append_local(
        self,
        timestamp: Union[datetime, int, float],
        values: Mapping[str, Optional[float]],
    ) -> None:
        unknown = set(values) - set(self._data)
        if unknown:
            raise KeyError(f"unknown time chart series: {', '.join(sorted(unknown))}")
        time_value = _echarts_time_value(timestamp)
        self._times.append(time_value)
        for item in self.series:
            self._data[item.name].append(values.get(item.name))

    def append(
        self,
        timestamp: Union[datetime, int, float],
        values: Mapping[str, Optional[float]],
    ) -> None:
        """Append one sample and update only this chart.

        Missing series values become gaps. Once ``max_points`` is reached, the
        oldest timestamp is dropped and the time axis shifts forward.
        """
        self._append_local(timestamp, values)
        self.pallet.send(_clean_dict({
            "type": "chart_option",
            "id": self.id,
            "option": {
                "series": [
                    {
                        "id": item.name,
                        "data": list(zip(self._times, self._data[item.name])),
                    }
                    for item in self.series
                ],
            },
            "lazyUpdate": False,
            "coalesce": True,
            "page": self.page,
        }))

    update = append

    def option_series(self) -> List[JsonObject]:
        return [
            item.to_echarts(list(zip(self._times, self._data[item.name])))
            for item in self.series
        ]


class MultiAxisLineChart:
    """Builder for line charts with any number of x/y axes.

    This hides the ECharts option structure. You define axes by name,
    attach lines to those named axes, and call render().
    """

    def __init__(
        self,
        pallet: "EChartsPallet",
        *,
        id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        title: str = "",
        titlebar: Optional[Union[str, bool]] = None,
        page: Optional[str] = None,
        group: Optional[str] = None,
        card: Optional[str] = None,
        animation: bool = True,
        tooltip: bool = True,
        data_zoom: bool = False,
        extra_option: Optional[JsonObject] = None,
    ) -> None:
        self.pallet = pallet
        self.id = id
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.title = title
        self.titlebar = titlebar if titlebar is not None else title
        self.page = page
        self.group = group
        self.card = card
        self.animation = animation
        self.tooltip = tooltip
        self.data_zoom = data_zoom
        self.extra_option = extra_option or {}
        self.x_axes: List[Axis] = []
        self.y_axes: List[Axis] = []
        self.lines: List[LineSeries] = []
        self.handle: Optional[ChartHandle] = None

    def add_x_axis(
        self,
        name: str,
        *,
        data: Optional[Sequence[Any]] = None,
        kind: str = "category",
        position: Optional[str] = None,
        units: str = "",
        offset: Optional[int] = None,
        min: Optional[float] = None,
        max: Optional[float] = None,
        extra: Optional[JsonObject] = None,
    ) -> "MultiAxisLineChart":
        if position is None:
            position = "bottom" if len(self.x_axes) == 0 else "top"
        self.x_axes.append(Axis(
            name=name, data=data, kind=kind, position=position, units=units,
            offset=offset, min=min, max=max, extra=extra
        ))
        return self

    def add_y_axis(
        self,
        name: str,
        *,
        kind: str = "value",
        position: Optional[str] = None,
        units: str = "",
        offset: Optional[int] = None,
        min: Optional[float] = None,
        max: Optional[float] = None,
        extra: Optional[JsonObject] = None,
    ) -> "MultiAxisLineChart":
        if position is None:
            position = "left" if len(self.y_axes) == 0 else "right"
        self.y_axes.append(Axis(
            name=name, kind=kind, position=position, units=units,
            offset=offset, min=min, max=max, extra=extra
        ))
        return self

    def add_line(
        self,
        name: str,
        data: Sequence[Any],
        *,
        x_axis: Union[str, int] = 0,
        y_axis: Union[str, int] = 0,
        smooth: bool = False,
        area: bool = False,
        show_symbols: bool = False,
        step: Optional[Union[str, bool]] = None,
        extra: Optional[JsonObject] = None,
    ) -> "MultiAxisLineChart":
        self.lines.append(LineSeries(
            name=name,
            data=data,
            x_axis=x_axis,
            y_axis=y_axis,
            smooth=smooth,
            area=area,
            show_symbols=show_symbols,
            step=step,
            extra=extra,
        ))
        return self

    def _axis_index(self, axes: Sequence[Axis], ref: Union[str, int]) -> int:
        if isinstance(ref, int):
            if ref < 0 or ref >= len(axes):
                raise IndexError(f"Axis index {ref} is out of range")
            return ref
        for idx, axis in enumerate(axes):
            if axis.name == ref or axis.label() == ref:
                return idx
        names = ", ".join(axis.name for axis in axes)
        raise KeyError(f"No axis named {ref!r}. Available axes: {names}")

    def option(self) -> JsonObject:
        if not self.x_axes:
            self.add_x_axis("X")
        if not self.y_axes:
            self.add_y_axis("Y")

        series = []
        for line in self.lines:
            x_idx = self._axis_index(self.x_axes, line.x_axis)
            y_idx = self._axis_index(self.y_axes, line.y_axis)
            series.append(line.to_echarts(x_idx, y_idx))

        option: JsonObject = {
            "animation": self.animation,
            "title": {"text": self.title} if self.title else {},
            "tooltip": {"trigger": "axis"} if self.tooltip else {},
            "legend": {"top": 30} if len(series) > 1 else {},
            "grid": {
                "left": 70,
                "right": 80,
                "top": 90 if self.title or len(series) > 1 else 55,
                "bottom": 75 if self.data_zoom else 55,
            },
            "xAxis": [axis.to_echarts() for axis in self.x_axes],
            "yAxis": [axis.to_echarts() for axis in self.y_axes],
            "series": series,
        }

        if self.data_zoom:
            option["dataZoom"] = [
                {"type": "inside"},
                {"type": "slider", "bottom": 20},
            ]

        option.update(self.extra_option)
        return option

    def render(self) -> ChartHandle:
        self.handle = self.pallet.chart(
            id=self.id,
            x=self.x,
            y=self.y,
            width=self.width,
            height=self.height,
            title=self.title,
            titlebar=self.titlebar,
            option=self.option(),
            page=self.page,
            group=self.group,
            card=self.card,
        )
        return self.handle

    def update_line(self, name: str, data: Sequence[Any], *, coalesce: bool = False) -> None:
        """Update one line by name after render()."""
        for idx, line in enumerate(self.lines):
            if line.name == name:
                line.data = data
                self.pallet.set_option(
                    self.id,
                    {"series": [{"name": name, "data": list(data)}]},
                    coalesce=coalesce,
                    page=self.page,
                )
                return
        raise KeyError(f"No line named {name!r}")

    def update_x_axis(self, name: str, data: Sequence[Any], *, coalesce: bool = False) -> None:
        """Update category labels for one x axis by name."""
        for idx, axis in enumerate(self.x_axes):
            if axis.name == name:
                axis.data = data
                x_axes = [{} for _ in self.x_axes]
                x_axes[idx] = {"name": axis.label(), "data": list(data)}
                self.pallet.set_option(
                    self.id,
                    {"xAxis": x_axes},
                    coalesce=coalesce,
                    page=self.page,
                )
                return
        raise KeyError(f"No x axis named {name!r}")


@dataclass
class EChartsPallet:
    """Compatibility API that now sends chart commands through ``bridge.py``.

    The historic class name is retained so existing chart programs keep
    working. ``start()`` connects to the bridge TCP port (9000 by default), and
    ``stop()`` closes that connection.
    """

    host: str = DEFAULT_BRIDGE_HOST
    port: int = DEFAULT_BRIDGE_PORT
    replay_on_connect: bool = True
    log_level: int = logging.INFO

    _bridge: Optional[Pallet] = field(default=None, init=False)
    _event_bridge: Optional[Pallet] = field(default=None, init=False)
    _event_thread: Optional[threading.Thread] = field(default=None, init=False)
    _event_stop: threading.Event = field(default_factory=threading.Event, init=False)
    _buffer: List[JsonObject] = field(default_factory=list, init=False)
    _event_handlers: List[UiEventHandler] = field(default_factory=list, init=False)
    _logger: logging.Logger = field(default_factory=lambda: logging.getLogger("echarts_pallet"), init=False)
    _last_status: Optional[JsonObject] = field(default=None, init=False)

    def start(self, *, wait: bool = True, timeout: float = 5.0) -> None:
        if self._bridge is not None:
            return
        logging.basicConfig(level=self.log_level)
        self._logger.setLevel(self.log_level)
        self._bridge = Pallet.for_bridge(self.host, self.port, timeout=timeout)
        hello = self._bridge.connect()
        self._last_status = hello
        self._logger.info("Connected to web pallet bridge at %s:%s", self.host, self.port)

    def stop(self, *, timeout: float = 5.0) -> None:
        self._event_stop.set()
        if self._event_bridge is not None:
            self._event_bridge.close()
            self._event_bridge = None
        if self._event_thread is not None and self._event_thread.is_alive():
            self._event_thread.join(timeout=timeout)
        self._event_thread = None
        if self._bridge is not None:
            self._bridge.close()
            self._bridge = None

    def run_until_interrupted(self) -> None:
        self.start()
        print(f"ECharts client connected to bridge at {self.host}:{self.port}")
        print("Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(0.25)
        except KeyboardInterrupt:
            self.stop()

    def _handle_incoming(self, event: JsonObject) -> None:
        if isinstance(event, dict) and event.get("type") == "__pallet_status":
            self._last_status = event

        for handler in list(self._event_handlers):
            try:
                handler(event)
            except Exception:
                self._logger.exception("Pallet event handler failed")

    def on_event(self, handler: UiEventHandler) -> None:
        self._event_handlers.append(handler)
        self._start_event_listener()

    def _start_event_listener(self) -> None:
        if self._event_thread is not None and self._event_thread.is_alive():
            return
        self._event_stop.clear()
        self._event_bridge = Pallet.for_bridge(self.host, self.port)
        self._event_bridge.connect()
        self._event_bridge.subscribe_events()

        def listen() -> None:
            assert self._event_bridge is not None
            while not self._event_stop.is_set():
                try:
                    event = self._event_bridge.poll_event(timeout=0.2)
                    if event is not None:
                        self._handle_incoming(event)
                except (ConnectionError, OSError):
                    if not self._event_stop.is_set():
                        self._logger.exception("Bridge event listener stopped")
                    return

        self._event_thread = threading.Thread(target=listen, name="EChartsPalletEvents", daemon=True)
        self._event_thread.start()

    @property
    def last_status(self) -> Optional[JsonObject]:
        return self._last_status

    @property
    def client_count(self) -> int:
        if self._bridge is None:
            return 0
        try:
            status = self._bridge.status()
            self._last_status = status
            return int(status.get("web_clients", 0))
        except (ConnectionError, OSError):
            return 0

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def send(self, command: Union[JsonObject, Sequence[JsonObject]], *, remember: bool = True) -> None:
        commands = list(command) if isinstance(command, list) else [command]  # type: ignore[list-item]

        if remember:
            for item in commands:
                if isinstance(item, dict):
                    self._remember(item)

        if self._bridge is None:
            self.start()
        assert self._bridge is not None
        if len(commands) == 1:
            self._bridge.command(commands[0])
        else:
            self._bridge.commands(commands)

    def _remember(self, command: JsonObject) -> None:
        ctype = command.get("type")
        if ctype == "clear":
            self._buffer.clear()
            self._buffer.append(command)
            return

        if ctype == "chart_data" and not command.get("append"):
            identity = (
                command.get("page"), command.get("id"), command.get("seriesId"),
                command.get("seriesName"), command.get("seriesIndex", 0),
            )
            for index in range(len(self._buffer) - 1, -1, -1):
                previous = self._buffer[index]
                if previous.get("type") == "chart_define" and (
                    previous.get("page"), previous.get("id")
                ) == identity[:2]:
                    break
                previous_identity = (
                    previous.get("page"), previous.get("id"), previous.get("seriesId"),
                    previous.get("seriesName"), previous.get("seriesIndex", 0),
                )
                if previous.get("type") == "chart_data" and previous_identity == identity:
                    self._buffer[index] = command
                    return

        if ctype == "chart_option" and command.get("coalesce"):
            identity = (command.get("page"), command.get("id"))
            for index in range(len(self._buffer) - 1, -1, -1):
                previous = self._buffer[index]
                if previous.get("type") == "chart_define" and (
                    previous.get("page"), previous.get("id")
                ) == identity:
                    break
                if previous.get("type") == "chart_option" and previous.get("coalesce") and (
                    previous.get("page"), previous.get("id")
                ) == identity:
                    self._buffer[index] = command
                    return

        self._buffer.append(command)

    def clear(self, *, color: str = "#0f172a", page: Optional[str] = None) -> None:
        self.send(_clean_dict({"type": "clear", "color": color, "page": page}))

    def show_page(self, page: Optional[str]) -> None:
        self.send({"type": "page_show", "page": page})

    def delete_page(self, page: str) -> None:
        self.send({"type": "page_delete", "page": page})

    def replace_group(self, group: str, commands: Sequence[JsonObject], *, page: Optional[str] = None) -> None:
        self.send(_clean_dict({
            "type": "group_replace",
            "group": group,
            "commands": list(commands),
            "page": page,
        }))

    def load_script(self, url: str, *, global_name: Optional[str] = None, remember: bool = True) -> None:
        self.send(_clean_dict({
            "type": "script_load",
            "url": url,
            "global": global_name,
        }), remember=remember)

    def define_grid(
        self,
        id: str = "default",
        *,
        x: int = 0,
        y: int = 0,
        width: Optional[int] = None,
        height: Optional[int] = None,
        columns: int = 2,
        gap: int = 12,
        padding: int = 12,
        page: Optional[str] = None,
        group: Optional[str] = None,
    ) -> None:
        """Define a DOM grid that can contain cards and card-hosted charts."""
        self.send(_clean_dict({
            "type": "ui_grid", "id": id, "x": x, "y": y,
            "width": width, "height": height, "columns": columns,
            "gap": gap, "padding": padding, "page": page, "group": group,
        }))

    def define_card(
        self,
        id: str,
        *,
        grid: str = "default",
        title: str = "",
        column_span: int = 1,
        row_span: int = 1,
        background: Optional[str] = None,
        color: Optional[str] = None,
        border: Optional[Union[str, bool]] = None,
        page: Optional[str] = None,
        group: Optional[str] = None,
    ) -> None:
        """Define a card before creating a chart with ``card=id``."""
        self.send(_clean_dict({
            "type": "ui_card", "id": id, "grid": grid, "title": title,
            "columnSpan": column_span, "rowSpan": row_span,
            "background": background, "color": color, "border": border,
            "page": page, "group": group,
        }))

    # ------------------------------------------------------------------
    # Generic chart commands
    # ------------------------------------------------------------------

    def chart(
        self,
        *,
        id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        option: JsonObject,
        title: Optional[str] = None,
        page: Optional[str] = None,
        group: Optional[str] = None,
        theme: Optional[str] = None,
        titlebar: Optional[Union[str, bool]] = None,
        background: Optional[str] = None,
        border: Optional[str] = None,
        card: Optional[str] = None,
    ) -> ChartHandle:
        if title and "title" not in option:
            option = dict(option)
            option["title"] = {"text": title}

        if titlebar is None:
            titlebar = title

        self.send(_clean_dict({
            "type": "chart_define",
            "id": id,
            "x": int(x),
            "y": int(y),
            "width": int(width),
            "height": int(height),
            "option": option,
            "page": page,
            "group": group,
            "theme": theme,
            "titlebar": titlebar,
            "background": background,
            "border": border,
            "card": card,
        }))

        return ChartHandle(self, id, page)

    def set_option(
        self,
        id: str,
        option: JsonObject,
        *,
        merge: bool = True,
        lazy_update: bool = False,
        coalesce: bool = False,
        page: Optional[str] = None,
    ) -> None:
        self.send(_clean_dict({
            "type": "chart_option",
            "id": id,
            "option": option,
            "merge": merge,
            "lazyUpdate": lazy_update,
            "coalesce": coalesce,
            "page": page,
        }))

    def set_data(self, id: str, data: Any, *, series_index: int = 0, page: Optional[str] = None) -> None:
        self.send(_clean_dict({
            "type": "chart_data",
            "id": id,
            "seriesIndex": series_index,
            "data": data,
            "page": page,
        }))

    def append_data(self, id: str, data: Any, *, series_index: int = 0, page: Optional[str] = None) -> None:
        self.send(_clean_dict({
            "type": "chart_append",
            "id": id,
            "seriesIndex": series_index,
            "data": data,
            "page": page,
        }))

    def resize_chart(
        self,
        id: str,
        *,
        x: Optional[int] = None,
        y: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        page: Optional[str] = None,
    ) -> None:
        self.send(_clean_dict({
            "type": "chart_resize",
            "id": id,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "page": page,
        }))

    def remove_chart(self, id: str, *, page: Optional[str] = None) -> None:
        self.send(_clean_dict({"type": "chart_remove", "id": id, "page": page}))

    # ------------------------------------------------------------------
    # High-level chart APIs
    # ------------------------------------------------------------------

    def live_time_chart(
        self,
        *,
        id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        series: Union[Mapping[str, str], Sequence[TimeChartSeries]],
        title: str = "",
        y_axis_name: str = "",
        max_points: int = 60,
        time_format: str = "%H:%M:%S",
        initial_data: Optional[
            Sequence[Tuple[Union[datetime, int, float], Mapping[str, Optional[float]]]]
        ] = None,
        page: Optional[str] = None,
        group: Optional[str] = None,
        card: Optional[str] = None,
        extra_option: Optional[JsonObject] = None,
    ) -> LiveTimeChart:
        """Create a periodically updated chart with a rolling time axis.

        ``series`` may be a mapping such as ``{"Actual": "bar", "Target":
        "line"}`` or a sequence of :class:`TimeChartSeries` objects. Multiple
        bar series are grouped side-by-side at each timestamp. Call
        ``handle.append(timestamp, values)`` to add a sample; after
        ``max_points`` samples, the oldest point is removed automatically.
        The time axis automatically chooses rounded label intervals appropriate
        for the visible window instead of labeling every incoming sample.

        ``group`` is the normal Pallet command group, allowing the chart to be
        managed together with other commands through ``replace_group``.
        """
        if isinstance(series, Mapping):
            series_specs = [TimeChartSeries(name=name, kind=kind) for name, kind in series.items()]
        else:
            series_specs = list(series)

        live_chart = LiveTimeChart(
            self,
            id=id,
            series=series_specs,
            max_points=max_points,
            page=page,
            time_format=time_format,
        )
        for timestamp, values in initial_data or []:
            live_chart._append_local(timestamp, values)

        option: JsonObject = {
            "title": {"text": title} if title else {},
            # Rolling categories must move atomically. Animating bars from their
            # previous category briefly leaves them offset from the new labels.
            "animationDurationUpdate": 0,
            "legend": {"top": 34} if len(series_specs) > 1 else {},
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "grid": {
                "left": 70,
                "right": 30,
                "top": 85 if title or len(series_specs) > 1 else 30,
                "bottom": 70,
            },
            "xAxis": {
                "type": "time",
                "name": "Time",
                "nameLocation": "middle",
                "nameGap": 45,
                "boundaryGap": (
                    ["8%", "8%"] if any(item.kind == "bar" for item in series_specs) else False
                ),
                "axisLabel": {"hideOverlap": True},
            },
            "yAxis": {"type": "value", "name": y_axis_name},
            "series": live_chart.option_series(),
        }
        option.update(extra_option or {})

        self.chart(
            id=id,
            x=x,
            y=y,
            width=width,
            height=height,
            option=option,
            title=title,
            page=page,
            group=group,
            card=card,
            titlebar=title,
        )
        return live_chart

    def multi_axis_line_chart(
        self,
        *,
        id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        title: str = "",
        x_axes: Optional[Sequence[Axis]] = None,
        y_axes: Optional[Sequence[Axis]] = None,
        lines: Optional[Sequence[LineSeries]] = None,
        page: Optional[str] = None,
        group: Optional[str] = None,
        card: Optional[str] = None,
        data_zoom: bool = False,
        render: bool = False,
        extra_option: Optional[JsonObject] = None,
    ) -> MultiAxisLineChart:
        """Create a multi-axis line chart builder.

        Set render=True to send it immediately, or call .render() later.
        """
        builder = MultiAxisLineChart(
            self,
            id=id,
            x=x,
            y=y,
            width=width,
            height=height,
            title=title,
            page=page,
            group=group,
            card=card,
            data_zoom=data_zoom,
            extra_option=extra_option,
        )

        for axis in x_axes or []:
            builder.x_axes.append(axis)
        for axis in y_axes or []:
            builder.y_axes.append(axis)
        for line in lines or []:
            builder.lines.append(line)

        if render:
            builder.render()

        return builder

    def line_chart_2x2y(
        self,
        *,
        id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        title: str,
        bottom_x: Sequence[Any],
        top_x: Sequence[Any],
        left_series: Sequence[Any],
        right_series: Sequence[Any],
        bottom_x_name: str = "Time",
        top_x_name: str = "Sample",
        left_y_name: str = "Left",
        right_y_name: str = "Right",
        left_y_units: str = "",
        right_y_units: str = "",
        left_series_name: Optional[str] = None,
        right_series_name: Optional[str] = None,
        smooth: bool = True,
        data_zoom: bool = False,
        page: Optional[str] = None,
        group: Optional[str] = None,
        card: Optional[str] = None,
    ) -> ChartHandle:
        """Compact helper for the common two-X/two-Y line chart case."""

        builder = self.multi_axis_line_chart(
            id=id, x=x, y=y, width=width, height=height,
            title=title, page=page, group=group, card=card, data_zoom=data_zoom,
        )

        builder.add_x_axis(bottom_x_name, data=bottom_x, position="bottom")
        builder.add_x_axis(top_x_name, data=top_x, position="top")

        builder.add_y_axis(left_y_name, units=left_y_units, position="left")
        builder.add_y_axis(right_y_name, units=right_y_units, position="right")

        builder.add_line(
            left_series_name or left_y_name,
            left_series,
            x_axis=bottom_x_name,
            y_axis=left_y_name,
            smooth=smooth,
        )

        builder.add_line(
            right_series_name or right_y_name,
            right_series,
            x_axis=top_x_name,
            y_axis=right_y_name,
            smooth=smooth,
        )

        return builder.render()

    def line_chart(
        self,
        *,
        id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        x_data: Sequence[Any],
        y_data: Union[Sequence[Any], Sequence[Sequence[Any]]],
        title: str = "",
        series_names: Optional[Sequence[str]] = None,
        smooth: bool = False,
        area: bool = False,
        y_axis_name: Optional[str] = None,
        x_axis_name: Optional[str] = None,
        page: Optional[str] = None,
        group: Optional[str] = None,
        card: Optional[str] = None,
        extra_option: Optional[JsonObject] = None,
    ) -> ChartHandle:
        if not y_data:
            y_series: List[Sequence[Any]] = [[]]
        elif isinstance(y_data[0], (list, tuple)):  # type: ignore[index]
            y_series = list(y_data)  # type: ignore[assignment]
        else:
            y_series = [y_data]  # type: ignore[list-item]

        names = list(series_names or [])
        series = []
        for idx, values in enumerate(y_series):
            series.append(_clean_dict({
                "name": names[idx] if idx < len(names) else f"Series {idx + 1}",
                "type": "line",
                "smooth": smooth,
                "showSymbol": False,
                "areaStyle": {} if area else None,
                "data": list(values),
            }))

        option: JsonObject = {
            "title": {"text": title} if title else {},
            "tooltip": {"trigger": "axis"},
            "legend": {"top": 28} if len(series) > 1 else {},
            "grid": {"left": 48, "right": 24, "top": 60 if title or len(series) > 1 else 24, "bottom": 42},
            "xAxis": {
                "type": "category",
                "name": x_axis_name or "",
                "boundaryGap": False,
                "data": list(x_data),
            },
            "yAxis": {
                "type": "value",
                "name": y_axis_name or "",
            },
            "series": series,
        }
        option.update(extra_option or {})

        return self.chart(
            id=id, x=x, y=y, width=width, height=height,
            option=option, title=title, page=page, group=group, card=card, titlebar=title,
        )

    def gauge(
        self,
        *,
        id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        value: float,
        title: str = "",
        name: str = "Value",
        min: float = 0,
        max: float = 100,
        units: str = "",
        page: Optional[str] = None,
        group: Optional[str] = None,
        card: Optional[str] = None,
        extra_series: Optional[JsonObject] = None,
        extra_option: Optional[JsonObject] = None,
    ) -> ChartHandle:
        detail_formatter = "{value}" + units

        series: JsonObject = {
            "type": "gauge",
            "min": min,
            "max": max,
            "progress": {"show": True},
            "axisLine": {"lineStyle": {"width": 14}},
            "detail": {
                "valueAnimation": True,
                "formatter": detail_formatter,
                "fontSize": 28,
            },
            "data": [{"value": value, "name": name}],
        }
        if extra_series:
            series.update(extra_series)

        option: JsonObject = {
            "title": {"text": title} if title else {},
            "tooltip": {"formatter": "{a} <br/>{b}: {c}" + units},
            "series": [series],
        }
        option.update(extra_option or {})

        return self.chart(
            id=id, x=x, y=y, width=width, height=height,
            option=option, title=title, page=page, group=group, card=card, titlebar=title,
        )

    def update_gauge(
        self,
        id: str,
        value: float,
        *,
        name: str = "Value",
        series_index: int = 0,
        page: Optional[str] = None,
    ) -> None:
        self.set_data(id, [{"value": value, "name": name}], series_index=series_index, page=page)

    def bar_chart(
        self,
        *,
        id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        categories: Sequence[Any],
        values: Sequence[Any],
        title: str = "",
        horizontal: bool = False,
        series_name: str = "Value",
        page: Optional[str] = None,
        group: Optional[str] = None,
        card: Optional[str] = None,
    ) -> ChartHandle:
        if horizontal:
            option = {
                "title": {"text": title} if title else {},
                "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
                "grid": {"left": 90, "right": 24, "top": 60 if title else 24, "bottom": 30},
                "xAxis": {"type": "value"},
                "yAxis": {"type": "category", "data": list(categories)},
                "series": [{"name": series_name, "type": "bar", "data": list(values)}],
            }
        else:
            option = {
                "title": {"text": title} if title else {},
                "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
                "grid": {"left": 48, "right": 24, "top": 60 if title else 24, "bottom": 42},
                "xAxis": {"type": "category", "data": list(categories)},
                "yAxis": {"type": "value"},
                "series": [{"name": series_name, "type": "bar", "data": list(values)}],
            }

        return self.chart(id=id, x=x, y=y, width=width, height=height,
                          option=option, title=title, page=page, group=group, card=card,
                          titlebar=title)

    def pie_chart(
        self,
        *,
        id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        data: Sequence[Union[Tuple[str, float], JsonObject]],
        title: str = "",
        series_name: str = "Share",
        radius: Union[str, Sequence[str]] = "65%",
        page: Optional[str] = None,
        group: Optional[str] = None,
        card: Optional[str] = None,
    ) -> ChartHandle:
        normalized = []
        for item in data:
            if isinstance(item, dict):
                normalized.append(item)
            else:
                name, value = item
                normalized.append({"name": name, "value": value})

        option = {
            "title": {"text": title, "left": "center"} if title else {},
            "tooltip": {"trigger": "item"},
            "legend": {"bottom": 0},
            "series": [{
                "name": series_name,
                "type": "pie",
                "radius": radius,
                "center": ["50%", "48%"],
                "data": normalized,
            }],
        }
        return self.chart(id=id, x=x, y=y, width=width, height=height,
                          option=option, title=title, page=page, group=group, card=card,
                          titlebar=title)


    # ------------------------------------------------------------------
    # ECharts example-gallery style helpers
    # ------------------------------------------------------------------

    def progress_gauge(
        self,
        *,
        id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        value: float,
        title: str = "",
        name: str = "Value",
        min: float = 0,
        max: float = 100,
        units: str = "",
        ring_width: int = 18,
        page: Optional[str] = None,
        group: Optional[str] = None,
        card: Optional[str] = None,
    ) -> ChartHandle:
        """Progress-ring gauge, similar to the ECharts Progress Gauge example."""
        return self.gauge(
            id=id, x=x, y=y, width=width, height=height,
            title=title, name=name, value=value, min=min, max=max, units=units,
            page=page, group=group, card=card,
            extra_series={
                "progress": {"show": True, "roundCap": True, "width": ring_width},
                "pointer": {"show": False},
                "axisLine": {"roundCap": True, "lineStyle": {"width": ring_width}},
                "axisTick": {"show": False},
                "splitLine": {"show": False},
                "axisLabel": {"show": False},
                "detail": {
                    "valueAnimation": True,
                    "formatter": "{value}" + units,
                    "fontSize": 34,
                    "offsetCenter": [0, "10%"],
                },
                "title": {"offsetCenter": [0, "45%"], "fontSize": 16},
            },
        )

    def multi_ring_gauge(
        self,
        *,
        id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        gauges: Sequence[Dict[str, Any]],
        title: str = "",
        min: float = 0,
        max: float = 100,
        units: str = "%",
        page: Optional[str] = None,
        group: Optional[str] = None,
        card: Optional[str] = None,
    ) -> ChartHandle:
        """Multiple concentric progress gauges.

        gauges example:
            [
                {"name": "CPU", "value": 70},
                {"name": "RAM", "value": 55},
                {"name": "Disk", "value": 82},
            ]
        """
        count = max(1, len(gauges))
        series = []
        for index, item in enumerate(gauges):
            radius = f"{90 - index * 18}%"
            series.append({
                "name": item.get("name", f"Gauge {index + 1}"),
                "type": "gauge",
                "min": item.get("min", min),
                "max": item.get("max", max),
                "radius": radius,
                "startAngle": 90,
                "endAngle": -270,
                "progress": {"show": True, "roundCap": True, "width": item.get("width", 10)},
                "pointer": {"show": False},
                "axisLine": {"roundCap": True, "lineStyle": {"width": item.get("width", 10)}},
                "axisTick": {"show": False},
                "splitLine": {"show": False},
                "axisLabel": {"show": False},
                "detail": {
                    "show": index == 0,
                    "valueAnimation": True,
                    "formatter": "{value}" + units,
                    "fontSize": 26,
                },
                "data": [{"value": item.get("value", 0), "name": item.get("name", "")}],
            })
        option = {
            "title": {"text": title} if title else {},
            "tooltip": {"trigger": "item"},
            "series": series,
        }
        return self.chart(id=id, x=x, y=y, width=width, height=height,
                          option=option, title=title, page=page, group=group, card=card,
                          titlebar=title)

    def stacked_line_chart(
        self,
        *,
        id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        x_data: Sequence[Any],
        series: Dict[str, Sequence[Any]],
        title: str = "",
        area: bool = True,
        smooth: bool = False,
        page: Optional[str] = None,
        group: Optional[str] = None,
        card: Optional[str] = None,
    ) -> ChartHandle:
        """Stacked line / stacked area chart helper."""
        echarts_series = []
        for name, values in series.items():
            item = {
                "name": name,
                "type": "line",
                "stack": "total",
                "smooth": smooth,
                "showSymbol": False,
                "data": list(values),
            }
            if area:
                item["areaStyle"] = {}
            echarts_series.append(item)

        option = {
            "title": {"text": title} if title else {},
            "tooltip": {"trigger": "axis"},
            "legend": {"top": 30},
            "grid": {"left": 55, "right": 28, "top": 80, "bottom": 45},
            "xAxis": {"type": "category", "boundaryGap": False, "data": list(x_data)},
            "yAxis": {"type": "value"},
            "series": echarts_series,
        }
        return self.chart(id=id, x=x, y=y, width=width, height=height,
                          option=option, title=title, page=page, group=group, card=card,
                          titlebar=title)

    def area_line_chart(
        self,
        *,
        id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        x_data: Sequence[Any],
        y_data: Sequence[Any],
        title: str = "",
        name: str = "Value",
        smooth: bool = True,
        page: Optional[str] = None,
        group: Optional[str] = None,
        card: Optional[str] = None,
    ) -> ChartHandle:
        """Area line chart helper."""
        return self.line_chart(
            id=id, x=x, y=y, width=width, height=height,
            x_data=x_data, y_data=y_data, title=title,
            series_names=[name], smooth=smooth, area=True,
            page=page, group=group, card=card,
        )

    def stepped_line_chart(
        self,
        *,
        id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        x_data: Sequence[Any],
        y_data: Sequence[Any],
        title: str = "",
        name: str = "Value",
        step: Union[str, bool] = "middle",
        page: Optional[str] = None,
        group: Optional[str] = None,
        card: Optional[str] = None,
    ) -> ChartHandle:
        """Step line chart helper."""
        option = {
            "title": {"text": title} if title else {},
            "tooltip": {"trigger": "axis"},
            "grid": {"left": 55, "right": 28, "top": 65 if title else 35, "bottom": 45},
            "xAxis": {"type": "category", "data": list(x_data)},
            "yAxis": {"type": "value"},
            "series": [{"name": name, "type": "line", "step": step, "data": list(y_data)}],
        }
        return self.chart(id=id, x=x, y=y, width=width, height=height,
                          option=option, title=title, page=page, group=group, card=card,
                          titlebar=title)

    def bar_race_chart(
        self,
        *,
        id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        categories: Sequence[Any],
        values: Sequence[Any],
        title: str = "",
        series_name: str = "Value",
        realtime_sort: bool = True,
        page: Optional[str] = None,
        group: Optional[str] = None,
        card: Optional[str] = None,
    ) -> ChartHandle:
        """Bar-race style horizontal bar chart.

        Update with:
            pallet.set_option(id, {"yAxis": {"data": categories}, "series": [{"data": values}]})
        """
        option = {
            "title": {"text": title} if title else {},
            "grid": {"left": 95, "right": 40, "top": 65 if title else 35, "bottom": 35},
            "xAxis": {"type": "value", "max": "dataMax"},
            "yAxis": {
                "type": "category",
                "data": list(categories),
                "inverse": True,
                "animationDuration": 300,
                "animationDurationUpdate": 300,
            },
            "series": [{
                "name": series_name,
                "type": "bar",
                "realtimeSort": realtime_sort,
                "data": list(values),
                "label": {"show": True, "position": "right", "valueAnimation": True},
            }],
            "animationDuration": 0,
            "animationDurationUpdate": 700,
            "animationEasing": "linear",
            "animationEasingUpdate": "linear",
        }
        return self.chart(id=id, x=x, y=y, width=width, height=height,
                          option=option, title=title, page=page, group=group, card=card,
                          titlebar=title)

    def doughnut_chart(
        self,
        *,
        id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        data: Sequence[Union[Tuple[str, float], JsonObject]],
        title: str = "",
        series_name: str = "Share",
        inner_radius: str = "45%",
        outer_radius: str = "70%",
        page: Optional[str] = None,
        group: Optional[str] = None,
        card: Optional[str] = None,
    ) -> ChartHandle:
        """Doughnut/ring pie chart helper."""
        return self.pie_chart(
            id=id, x=x, y=y, width=width, height=height,
            data=data, title=title, series_name=series_name,
            radius=[inner_radius, outer_radius],
            page=page, group=group, card=card,
        )

    def rose_pie_chart(
        self,
        *,
        id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        data: Sequence[Union[Tuple[str, float], JsonObject]],
        title: str = "",
        rose_type: str = "radius",
        page: Optional[str] = None,
        group: Optional[str] = None,
        card: Optional[str] = None,
    ) -> ChartHandle:
        """Nightingale/rose pie chart helper."""
        normalized = []
        for item in data:
            if isinstance(item, dict):
                normalized.append(item)
            else:
                name, value = item
                normalized.append({"name": name, "value": value})

        option = {
            "title": {"text": title, "left": "center"} if title else {},
            "tooltip": {"trigger": "item"},
            "legend": {"bottom": 0},
            "series": [{
                "type": "pie",
                "radius": [20, "70%"],
                "center": ["50%", "48%"],
                "roseType": rose_type,
                "data": normalized,
            }],
        }
        return self.chart(id=id, x=x, y=y, width=width, height=height,
                          option=option, title=title, page=page, group=group, card=card,
                          titlebar=title)

    def bubble_scatter_chart(
        self,
        *,
        id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        points: Sequence[Union[Tuple[float, float, float], Sequence[float]]],
        title: str = "",
        x_name: str = "X",
        y_name: str = "Y",
        size_name: str = "Size",
        page: Optional[str] = None,
        group: Optional[str] = None,
        card: Optional[str] = None,
    ) -> ChartHandle:
        """Bubble scatter chart. Each point is (x, y, size)."""
        option = {
            "title": {"text": title} if title else {},
            "tooltip": {
                "trigger": "item",
                "formatter": "{a}<br/>" + x_name + ": {@[0]}<br/>" + y_name + ": {@[1]}<br/>" + size_name + ": {@[2]}",
            },
            "grid": {"left": 55, "right": 28, "top": 65 if title else 35, "bottom": 50},
            "xAxis": {"type": "value", "name": x_name},
            "yAxis": {"type": "value", "name": y_name},
            "series": [{
                "name": title or "Bubble",
                "type": "scatter",
                "data": [list(p) for p in points],
                "symbolSize": "function (data) { return Math.max(6, Math.sqrt(data[2]) * 4); }",
            }],
        }
        return self.chart(id=id, x=x, y=y, width=width, height=height,
                          option=option, title=title, page=page, group=group, card=card,
                          titlebar=title)

    def heatmap_chart(
        self,
        *,
        id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        x_labels: Sequence[Any],
        y_labels: Sequence[Any],
        values: Sequence[Union[Tuple[int, int, float], Sequence[float]]],
        title: str = "",
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        page: Optional[str] = None,
        group: Optional[str] = None,
        card: Optional[str] = None,
    ) -> ChartHandle:
        """Heatmap chart helper.

        values are triples:
            (x_index, y_index, value)
        """
        numeric_values = [float(v[2]) for v in values] if values else [0]
        if min_value is None:
            min_value = min(numeric_values)
        if max_value is None:
            max_value = max(numeric_values)

        option = {
            "title": {"text": title} if title else {},
            "tooltip": {"position": "top"},
            "grid": {"left": 80, "right": 30, "top": 65 if title else 35, "bottom": 80},
            "xAxis": {"type": "category", "data": list(x_labels), "splitArea": {"show": True}},
            "yAxis": {"type": "category", "data": list(y_labels), "splitArea": {"show": True}},
            "visualMap": {
                "min": min_value,
                "max": max_value,
                "calculable": True,
                "orient": "horizontal",
                "left": "center",
                "bottom": 15,
            },
            "series": [{
                "name": title or "Heatmap",
                "type": "heatmap",
                "data": [list(v) for v in values],
                "label": {"show": True},
                "emphasis": {"itemStyle": {"shadowBlur": 10}},
            }],
        }
        return self.chart(id=id, x=x, y=y, width=width, height=height,
                          option=option, title=title, page=page, group=group, card=card,
                          titlebar=title)

    def radar_chart(
        self,
        *,
        id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        indicators: Sequence[Union[str, Dict[str, Any]]],
        series: Dict[str, Sequence[float]],
        title: str = "",
        page: Optional[str] = None,
        group: Optional[str] = None,
        card: Optional[str] = None,
    ) -> ChartHandle:
        """Radar chart helper."""
        normalized_indicators = []
        for item in indicators:
            if isinstance(item, dict):
                normalized_indicators.append(item)
            else:
                normalized_indicators.append({"name": str(item)})
        option = {
            "title": {"text": title} if title else {},
            "tooltip": {},
            "legend": {"bottom": 0},
            "radar": {"indicator": normalized_indicators},
            "series": [{
                "type": "radar",
                "data": [{"name": name, "value": list(values)} for name, values in series.items()],
            }],
        }
        return self.chart(id=id, x=x, y=y, width=width, height=height,
                          option=option, title=title, page=page, group=group, card=card,
                          titlebar=title)

    def candlestick_chart(
        self,
        *,
        id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        categories: Sequence[Any],
        ohlc: Sequence[Sequence[float]],
        title: str = "",
        page: Optional[str] = None,
        group: Optional[str] = None,
        card: Optional[str] = None,
    ) -> ChartHandle:
        """Candlestick chart helper. ohlc rows are [open, close, low, high]."""
        option = {
            "title": {"text": title} if title else {},
            "tooltip": {"trigger": "axis"},
            "grid": {"left": 65, "right": 35, "top": 65 if title else 35, "bottom": 70},
            "xAxis": {"type": "category", "data": list(categories), "scale": True},
            "yAxis": {"scale": True},
            "dataZoom": [{"type": "inside"}, {"type": "slider"}],
            "series": [{"type": "candlestick", "data": [list(row) for row in ohlc]}],
        }
        return self.chart(id=id, x=x, y=y, width=width, height=height,
                          option=option, title=title, page=page, group=group, card=card,
                          titlebar=title)

    def funnel_chart(
        self,
        *,
        id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        data: Sequence[Union[Tuple[str, float], JsonObject]],
        title: str = "",
        page: Optional[str] = None,
        group: Optional[str] = None,
        card: Optional[str] = None,
    ) -> ChartHandle:
        """Funnel chart helper."""
        normalized = []
        for item in data:
            if isinstance(item, dict):
                normalized.append(item)
            else:
                name, value = item
                normalized.append({"name": name, "value": value})
        option = {
            "title": {"text": title} if title else {},
            "tooltip": {"trigger": "item", "formatter": "{b}: {c}"},
            "legend": {"bottom": 0},
            "series": [{
                "type": "funnel",
                "left": "10%",
                "top": 60,
                "bottom": 60,
                "width": "80%",
                "sort": "descending",
                "label": {"show": True, "position": "inside"},
                "data": normalized,
            }],
        }
        return self.chart(id=id, x=x, y=y, width=width, height=height,
                          option=option, title=title, page=page, group=group, card=card,
                          titlebar=title)

    def treemap_chart(
        self,
        *,
        id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        data: Sequence[JsonObject],
        title: str = "",
        page: Optional[str] = None,
        group: Optional[str] = None,
        card: Optional[str] = None,
    ) -> ChartHandle:
        """Treemap chart helper."""
        option = {
            "title": {"text": title} if title else {},
            "tooltip": {"trigger": "item"},
            "series": [{
                "type": "treemap",
                "data": list(data),
                "breadcrumb": {"show": True},
                "label": {"show": True, "formatter": "{b}"},
            }],
        }
        return self.chart(id=id, x=x, y=y, width=width, height=height,
                          option=option, title=title, page=page, group=group, card=card,
                          titlebar=title)


# Backward compatibility for programs written before the bridge-based rename.
EChartsPalletServer = EChartsPallet


def demo_2x2y() -> None:
    """Demo for the simplified two-X/two-Y API."""
    pallet = EChartsPallet()
    pallet.start()
    pallet.clear(color="#0f172a")

    pallet.line_chart_2x2y(
        id="dual_axis",
        x=30,
        y=30,
        width=1050,
        height=540,
        title="Temperature and Voltage",
        bottom_x=["0s", "1s", "2s", "3s", "4s", "5s"],
        top_x=[0, 1, 2, 3, 4, 5],
        left_series=[72, 72.5, 73.0, 73.4, 73.2, 73.8],
        right_series=[3.20, 3.23, 3.25, 3.24, 3.28, 3.30],
        bottom_x_name="Time",
        top_x_name="Sample",
        left_y_name="Temperature",
        left_y_units="°F",
        right_y_name="Voltage",
        right_y_units="V",
        data_zoom=True,
    )

    pallet.gauge(
        id="load",
        x=30,
        y=600,
        width=360,
        height=300,
        title="Load",
        value=42,
        units="%",
    )

    print("Open echarts_web_pallet.html and connect to ws://localhost:8080")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(0.25)
    except KeyboardInterrupt:
        pallet.stop()


if __name__ == "__main__":
    demo_2x2y()
