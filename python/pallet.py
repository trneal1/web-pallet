#!/usr/bin/env python3
"""
pallet.py
=========
Small drawing client for ``pallet.html`` through ``bridge.py``.

Run ``bridge.py`` first, open ``pallet.html`` in a browser, then connect this
client to the bridge TCP port. Each drawing primitive is sent as one JSON line.
"""
from __future__ import annotations

import json
import os
import select
import socket
from collections import deque
from contextlib import contextmanager
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

DEFAULT_BRIDGE_HOST = os.environ.get("PALLET_BRIDGE_HOST", "127.0.0.1")
DEFAULT_BRIDGE_PORT = int(os.environ.get("PALLET_BRIDGE_PORT", "9000"))
DEFAULT_WIDTH = 960
DEFAULT_HEIGHT = 540
_UNSET = object()


class TerminalRegion:
    """Convenience handle for a scrolling text region on the browser pallet."""

    def __init__(self, pallet: "Pallet", region_id: str) -> None:
        self.pallet = pallet
        self.id = region_id

    def write(self, text: Any, *, color: Optional[str] = None) -> dict[str, Any]:
        return self.pallet.write_terminal(self.id, text, color=color, newline=False)

    def writeln(self, text: Any = "", *, color: Optional[str] = None) -> dict[str, Any]:
        return self.pallet.write_terminal(self.id, text, color=color, newline=True)

    def clear(self) -> dict[str, Any]:
        return self.pallet.clear_terminal(self.id)


class UIControl:
    """Convenience handle for a browser-native interactive control."""

    def __init__(self, pallet: "Pallet", control_id: str) -> None:
        self.pallet = pallet
        self.id = control_id

    def set(self, value: Any = _UNSET, *, disabled: Optional[bool] = None, label: Optional[str] = None, **properties: Any) -> dict[str, Any]:
        return self.pallet.update_control(self.id, value=value, disabled=disabled, label=label, **properties)

    def on(self, callback: Callable[[dict[str, Any]], None]) -> "UIControl":
        self.pallet.on_ui_event(self.id, callback)
        return self


class StatusWidget:
    """Convenience handle for an updateable dashboard status widget."""

    def __init__(self, pallet: "Pallet", status_id: str) -> None:
        self.pallet = pallet
        self.id = status_id

    def set(
        self,
        value: Any = _UNSET,
        *,
        status: Optional[str] = None,
        label: Optional[str] = None,
        active: Optional[bool] = None,
        **properties: Any,
    ) -> dict[str, Any]:
        return self.pallet.update_status_widget(
            self.id, value=value, status=status, label=label, active=active, **properties
        )


class DataTable:
    """Convenience handle for keyed live table updates."""

    def __init__(self, pallet: "Pallet", table_id: str) -> None:
        self.pallet = pallet
        self.id = table_id

    def set_rows(self, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        return self.pallet.update_table(self.id, "set", rows=rows)

    def upsert(self, rows: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        items = [rows] if isinstance(rows, Mapping) else rows
        return self.pallet.update_table(self.id, "upsert", rows=items)

    def remove(self, keys: Any | Sequence[Any]) -> dict[str, Any]:
        items = list(keys) if isinstance(keys, (list, tuple, set)) else [keys]
        return self.pallet.update_table(self.id, "remove", keys=items)

    def clear(self) -> dict[str, Any]:
        return self.pallet.update_table(self.id, "clear")

    def on_row_click(self, callback: Callable[[dict[str, Any]], None]) -> "DataTable":
        self.pallet.on_ui_event(self.id, callback)
        return self


class Pallet:
    """TCP drawing client for the browser pallet.

    The method names intentionally mirror the ESP TFT terminal primitives so
    existing graph code is easy to port.
    """

    def __init__(
        self,
        host: str = DEFAULT_BRIDGE_HOST,
        port: int = DEFAULT_BRIDGE_PORT,
        *,
        width: Optional[int] = None,
        height: Optional[int] = None,
        timeout: float = 5.0,
        wait_for_ack: bool = True,
        page: Optional[str | int] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.width = width if width is not None else DEFAULT_WIDTH
        self.height = height if height is not None else DEFAULT_HEIGHT
        self._auto_width = width is None
        self._auto_height = height is None
        self.timeout = timeout
        self.wait_for_ack = wait_for_ack
        self.page = None if page is None else str(page)
        self.browser_status: dict[str, Any] = {}
        self.viewport_width: Optional[int] = None
        self.viewport_height: Optional[int] = None
        self.content_width: Optional[int] = None
        self.content_height: Optional[int] = None
        self.scroll_x: Optional[int] = None
        self.scroll_y: Optional[int] = None
        self.buffer_width: Optional[int] = None
        self.buffer_height: Optional[int] = None
        self.screen_width: Optional[int] = None
        self.screen_height: Optional[int] = None
        self.screen_avail_width: Optional[int] = None
        self.screen_avail_height: Optional[int] = None
        self.device_pixel_ratio: Optional[float] = None
        self._sock: Optional[socket.socket] = None
        self._file = None
        self._batch: Optional[list[dict[str, Any]]] = None
        self._metadata_stack: list[dict[str, Any]] = []
        self._event_queue: deque[dict[str, Any]] = deque()
        self._event_callbacks: dict[str, list[Callable[[dict[str, Any]], None]]] = {}
        self._events_subscribed = False

    @classmethod
    def for_bridge(
        cls,
        host: str = DEFAULT_BRIDGE_HOST,
        port: int = DEFAULT_BRIDGE_PORT,
        **kwargs: Any,
    ) -> "Pallet":
        return cls(host, port, **kwargs)

    def __enter__(self) -> "Pallet":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def connect(self) -> dict[str, Any]:
        if self._sock is not None:
            return {"status": "already_connected"}

        try:
            self._sock = socket.create_connection((self.host, self.port), self.timeout)
        except OSError as exc:
            raise ConnectionError(
                f"could not connect to bridge TCP server at {self.host}:{self.port}: {exc}"
            ) from exc
        self._file = self._sock.makefile("r", encoding="utf-8", newline="\n")

        # Ask for status before waiting for a response.  Current bridges send
        # an unsolicited greeting first, while older bridges wait for the TCP
        # client to send its first command.  Sending the request up front
        # supports both protocols and avoids a command-first/response-first
        # deadlock between mixed deployments.
        payload = json.dumps(
            {"type": "__pallet_get_status"}, separators=(",", ":")
        ).encode("utf-8") + b"\n"
        self._sock.sendall(payload)

        try:
            hello = self._read_response()
            if hello.get("status") in {"connected", "no_web_clients"}:
                # Consume the response to the status request after the modern
                # bridge's unsolicited greeting, so it cannot be mistaken for
                # the acknowledgement of the first drawing command.
                hello = self._read_response()
        except ConnectionError:
            self.close()
            raise
        except (OSError, TimeoutError) as exc:
            self.close()
            raise ConnectionError(
                f"connected to {self.host}:{self.port}, but the service did not "
                "complete the web pallet bridge handshake"
            ) from exc
        self._apply_browser_status(hello)
        return hello

    def status(self) -> dict[str, Any]:
        response = self.command({"type": "__pallet_get_status"})
        self._apply_browser_status(response)
        return response

    def _apply_browser_status(self, status: dict[str, Any]) -> None:
        self.browser_status = status
        self.viewport_width = self._positive_int(status.get("viewport_width"))
        self.viewport_height = self._positive_int(status.get("viewport_height"))
        self.content_width = self._positive_int(status.get("content_width"))
        self.content_height = self._positive_int(status.get("content_height"))
        self.scroll_x = self._nonnegative_int(status.get("scroll_x"))
        self.scroll_y = self._nonnegative_int(status.get("scroll_y"))
        self.buffer_width = self._positive_int(status.get("buffer_width"))
        self.buffer_height = self._positive_int(status.get("buffer_height"))
        self.screen_width = self._positive_int(status.get("screen_width"))
        self.screen_height = self._positive_int(status.get("screen_height"))
        self.screen_avail_width = self._positive_int(status.get("screen_avail_width"))
        self.screen_avail_height = self._positive_int(status.get("screen_avail_height"))
        self.device_pixel_ratio = status.get("device_pixel_ratio")

        logical_width = self.viewport_width
        logical_height = self.viewport_height
        if self._auto_width and logical_width:
            self.width = logical_width
        if self._auto_height and logical_height:
            self.height = logical_height

    @staticmethod
    def _positive_int(value: Any) -> Optional[int]:
        if isinstance(value, (int, float)) and value > 0:
            return round(value)
        return None

    @staticmethod
    def _nonnegative_int(value: Any) -> Optional[int]:
        if isinstance(value, (int, float)) and value >= 0:
            return round(value)
        return None

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        self._events_subscribed = False

    def command(self, command: dict[str, Any]) -> dict[str, Any]:
        command = self._apply_command_metadata(command)
        command = self._apply_page(command)
        if self._batch is not None:
            self._batch.append(command)
            return {"status": "queued"}

        if self._sock is None:
            self.connect()

        assert self._sock is not None
        payload = json.dumps(command, separators=(",", ":")).encode("utf-8") + b"\n"
        self._sock.sendall(payload)
        return self._read_response() if self.wait_for_ack else {"status": "sent"}

    def commands(self, commands: Iterable[dict[str, Any]]) -> dict[str, Any]:
        if self._sock is None:
            self.connect()

        assert self._sock is not None
        payload = json.dumps(
            [self._apply_page(self._apply_command_metadata(command)) for command in commands],
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        self._sock.sendall(payload)
        return self._read_response() if self.wait_for_ack else {"status": "sent"}

    def _apply_command_metadata(self, command: dict[str, Any]) -> dict[str, Any]:
        if not self._metadata_stack:
            return command
        merged: dict[str, Any] = {}
        for metadata in self._metadata_stack:
            merged.update(metadata)
        return {**merged, **command}

    @contextmanager
    def command_metadata(self, **metadata: Any):
        self._metadata_stack.append({key: value for key, value in metadata.items() if value is not None})
        try:
            yield
        finally:
            self._metadata_stack.pop()

    @contextmanager
    def capture_commands(self):
        if self._batch is not None:
            raise RuntimeError("Cannot capture commands while a drawing batch is active")
        captured: list[dict[str, Any]] = []
        self._batch = captured
        try:
            yield captured
        finally:
            self._batch = None

    @contextmanager
    def coalesce_group(self, group: str):
        with self.capture_commands() as commands:
            yield commands
        self.replace_group(group, commands)

    def replace_group(self, group: str, commands: Iterable[dict[str, Any]]) -> dict[str, Any]:
        return self.command({
            "type": "__pallet_replace_group",
            "group": str(group),
            "commands": list(commands),
        })

    def _apply_page(self, command: dict[str, Any]) -> dict[str, Any]:
        if self.page is None or "page" in command or "palletPage" in command:
            return command
        return {**command, "page": self.page}

    def set_page(self, page: Optional[str | int]) -> None:
        self.page = None if page is None else str(page)

    def show_page(self, page: Optional[str | int] = None) -> dict[str, Any]:
        command: dict[str, Any] = {"type": "__pallet_show_page"}
        if page is not None:
            command["page"] = str(page)
        return self.command(command)

    def begin_batch(self) -> None:
        if self._batch is not None:
            raise RuntimeError("A drawing batch is already active")
        self._batch = []

    def end_batch(self) -> dict[str, Any]:
        if self._batch is None:
            raise RuntimeError("No drawing batch is active")
        batch = self._batch
        self._batch = None
        if not batch:
            return {"status": "empty"}
        return self.commands(batch)

    def _read_response(self) -> dict[str, Any]:
        while True:
            message = self._read_json_line()
            if message.get("status") != "event":
                return message
            event = message.get("event")
            if isinstance(event, dict):
                self._event_queue.append(event)

    def _read_json_line(self) -> dict[str, Any]:
        if self._file is None:
            return {}
        while True:
            line = self._file.readline()
            if not line:
                raise ConnectionError("bridge closed the TCP connection")
            if not line.strip():
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError as exc:
                preview = line[:200].rstrip("\r\n")
                raise ConnectionError(
                    f"service at {self.host}:{self.port} returned a non-JSON "
                    f"bridge response: {preview!r}"
                ) from exc

    def subscribe_events(self) -> dict[str, Any]:
        if self._events_subscribed:
            return {"status": "already_subscribed"}
        response = self.command({"type": "__pallet_subscribe_events"})
        self._events_subscribed = response.get("events") == "subscribed" or response.get("status") == "sent"
        return response

    def on_ui_event(self, control_id: str, callback: Callable[[dict[str, Any]], None]) -> None:
        if not callable(callback):
            raise TypeError("callback must be callable")
        self._event_callbacks.setdefault(str(control_id), []).append(callback)
        self.subscribe_events()

    def _dispatch_event(self, event: dict[str, Any]) -> None:
        event_id = str(event.get("id", ""))
        for callback in [*self._event_callbacks.get(event_id, []), *self._event_callbacks.get("*", [])]:
            callback(event)

    def poll_event(self, timeout: Optional[float] = 0.0) -> Optional[dict[str, Any]]:
        if self._event_queue:
            event = self._event_queue.popleft()
            self._dispatch_event(event)
            return event
        if not self._events_subscribed:
            self.subscribe_events()
        if self._sock is None:
            return None
        ready, _, _ = select.select([self._sock], [], [], timeout)
        if not ready:
            return None
        while True:
            message = self._read_json_line()
            if message.get("status") != "event":
                continue
            event = message.get("event")
            if isinstance(event, dict):
                self._dispatch_event(event)
                return event

    def run_event_loop(self, *, timeout: Optional[float] = None, until: Optional[Callable[[], bool]] = None) -> None:
        while until is None or not until():
            self.poll_event(timeout)

    def define_grid(
        self,
        grid_id: str = "default",
        *,
        x: float = 0,
        y: float = 0,
        width: Optional[float] = None,
        height: Optional[float] = None,
        columns: int = 2,
        min_column_width: int = 240,
        gap: int = 12,
        padding: int = 12,
        responsive: bool = True,
        background: str = "transparent",
    ) -> dict[str, Any]:
        command: dict[str, Any] = {
            "type": "ui_grid", "id": str(grid_id), "x": round(x), "y": round(y),
            "columns": columns, "minColumnWidth": min_column_width, "gap": gap,
            "padding": padding, "responsive": responsive, "background": background,
        }
        if width is not None:
            command["width"] = round(width)
        if height is not None:
            command["height"] = round(height)
        return self.command(command)

    def define_card(
        self,
        card_id: str,
        *,
        grid: str = "default",
        title: str = "",
        column_span: int = 1,
        row_span: int = 1,
        background: Optional[str] = None,
        color: Optional[str] = None,
        border: Optional[str | bool] = None,
    ) -> dict[str, Any]:
        command: dict[str, Any] = {
            "type": "ui_card", "id": str(card_id), "grid": str(grid), "title": title,
            "columnSpan": column_span, "rowSpan": row_span,
        }
        if background is not None:
            command["background"] = background
        if color is not None:
            command["color"] = color
        if border is not None:
            command["border"] = border
        return self.command(command)

    def control(
        self,
        control_id: str,
        *,
        kind: str = "button",
        label: str = "",
        value: Any = None,
        card: Optional[str] = None,
        grid: Optional[str] = None,
        options: Optional[Sequence[Any]] = None,
        minimum: Optional[float] = None,
        maximum: Optional[float] = None,
        step: Optional[float] = None,
        placeholder: Optional[str] = None,
        disabled: bool = False,
        live: bool = False,
        on_event: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> UIControl:
        self.define_control(
            control_id, kind=kind, label=label, value=value, card=card, grid=grid,
            options=options, minimum=minimum, maximum=maximum, step=step,
            placeholder=placeholder, disabled=disabled, live=live,
        )
        handle = UIControl(self, str(control_id))
        if on_event is not None:
            handle.on(on_event)
        return handle

    def define_control(
        self,
        control_id: str,
        *,
        kind: str = "button",
        label: str = "",
        value: Any = None,
        card: Optional[str] = None,
        grid: Optional[str] = None,
        options: Optional[Sequence[Any]] = None,
        minimum: Optional[float] = None,
        maximum: Optional[float] = None,
        step: Optional[float] = None,
        placeholder: Optional[str] = None,
        disabled: bool = False,
        live: bool = False,
    ) -> dict[str, Any]:
        if kind not in {"button", "toggle", "slider", "select", "text", "number"}:
            raise ValueError("kind must be button, toggle, slider, select, text, or number")
        command: dict[str, Any] = {
            "type": "ui_control", "id": str(control_id), "kind": kind,
            "label": label, "value": value, "disabled": disabled, "live": live,
        }
        if card is not None:
            command["card"] = str(card)
        if grid is not None:
            command["grid"] = str(grid)
        if options is not None:
            command["options"] = list(options)
        if minimum is not None:
            command["min"] = minimum
        if maximum is not None:
            command["max"] = maximum
        if step is not None:
            command["step"] = step
        if placeholder is not None:
            command["placeholder"] = placeholder
        return self.command(command)

    def update_control(
        self,
        control_id: str,
        *,
        value: Any = _UNSET,
        disabled: Optional[bool] = None,
        label: Optional[str] = None,
        **properties: Any,
    ) -> dict[str, Any]:
        command: dict[str, Any] = {"type": "ui_control_update", "id": str(control_id)}
        if value is not _UNSET:
            command["value"] = value
        if disabled is not None:
            command["disabled"] = disabled
        if label is not None:
            command["label"] = label
        command.update(properties)
        return self.command(command)

    def status_widget(
        self,
        status_id: str,
        *,
        kind: str = "badge",
        label: str = "",
        value: Any = None,
        status: str = "info",
        card: Optional[str] = None,
        grid: Optional[str] = None,
        units: str = "",
        minimum: float = 0,
        maximum: float = 100,
        color: Optional[str] = None,
        active: bool = True,
        message: Optional[str] = None,
    ) -> StatusWidget:
        self.define_status_widget(
            status_id, kind=kind, label=label, value=value, status=status,
            card=card, grid=grid, units=units, minimum=minimum, maximum=maximum,
            color=color, active=active, message=message,
        )
        return StatusWidget(self, str(status_id))

    def define_status_widget(
        self,
        status_id: str,
        *,
        kind: str = "badge",
        label: str = "",
        value: Any = None,
        status: str = "info",
        card: Optional[str] = None,
        grid: Optional[str] = None,
        units: str = "",
        minimum: float = 0,
        maximum: float = 100,
        color: Optional[str] = None,
        active: bool = True,
        message: Optional[str] = None,
    ) -> dict[str, Any]:
        if kind not in {"badge", "led", "progress", "kpi", "alert", "spinner"}:
            raise ValueError("kind must be badge, led, progress, kpi, alert, or spinner")
        if status not in {"info", "success", "warning", "danger", "neutral"}:
            raise ValueError("status must be info, success, warning, danger, or neutral")
        if kind == "progress" and maximum <= minimum:
            raise ValueError("progress maximum must be greater than minimum")
        command: dict[str, Any] = {
            "type": "ui_status", "id": str(status_id), "kind": kind,
            "label": label, "value": value, "status": status, "units": units,
            "min": minimum, "max": maximum, "active": active,
        }
        if card is not None:
            command["card"] = str(card)
        if grid is not None:
            command["grid"] = str(grid)
        if color is not None:
            command["color"] = color
        if message is not None:
            command["message"] = message
        return self.command(command)

    def update_status_widget(
        self,
        status_id: str,
        *,
        value: Any = _UNSET,
        status: Optional[str] = None,
        label: Optional[str] = None,
        active: Optional[bool] = None,
        **properties: Any,
    ) -> dict[str, Any]:
        if status is not None and status not in {"info", "success", "warning", "danger", "neutral"}:
            raise ValueError("status must be info, success, warning, danger, or neutral")
        command: dict[str, Any] = {"type": "ui_status_update", "id": str(status_id)}
        if value is not _UNSET:
            command["value"] = value
        if status is not None:
            command["status"] = status
        if label is not None:
            command["label"] = label
        if active is not None:
            command["active"] = active
        command.update(properties)
        return self.command(command)

    def table(
        self,
        table_id: str,
        columns: Sequence[str | Mapping[str, Any]],
        *,
        rows: Sequence[Mapping[str, Any]] = (),
        card: Optional[str] = None,
        grid: Optional[str] = None,
        title: str = "",
        key_field: str = "id",
        filterable: bool = True,
        selectable: bool = False,
        max_rows: int = 0,
        height: Optional[int] = None,
        on_row_click: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> DataTable:
        self.define_table(
            table_id, columns, rows=rows, card=card, grid=grid, title=title,
            key_field=key_field, filterable=filterable, selectable=selectable,
            max_rows=max_rows, height=height,
        )
        handle = DataTable(self, str(table_id))
        if on_row_click is not None:
            handle.on_row_click(on_row_click)
        return handle

    def define_table(
        self,
        table_id: str,
        columns: Sequence[str | Mapping[str, Any]],
        *,
        rows: Sequence[Mapping[str, Any]] = (),
        card: Optional[str] = None,
        grid: Optional[str] = None,
        title: str = "",
        key_field: str = "id",
        filterable: bool = True,
        selectable: bool = False,
        max_rows: int = 0,
        height: Optional[int] = None,
    ) -> dict[str, Any]:
        command: dict[str, Any] = {
            "type": "ui_table", "id": str(table_id), "columns": list(columns),
            "rows": list(rows), "title": title, "keyField": key_field,
            "filterable": filterable, "selectable": selectable, "maxRows": max_rows,
        }
        if card is not None:
            command["card"] = str(card)
        if grid is not None:
            command["grid"] = str(grid)
        if height is not None:
            command["height"] = height
        return self.command(command)

    def update_table(self, table_id: str, action: str = "set", **payload: Any) -> dict[str, Any]:
        if action not in {"set", "upsert", "remove", "clear"}:
            raise ValueError("action must be set, upsert, remove, or clear")
        return self.command({"type": "ui_table_update", "id": str(table_id), "action": action, **payload})

    def clear(self, color: str = "white") -> dict[str, Any]:
        return self.command({"type": "clear", "color": color})

    def terminal_region(
        self,
        region_id: str = "default",
        *,
        x: float = 0,
        y: float = 0,
        width: Optional[float] = None,
        height: Optional[float] = None,
        title: str = "",
        background: str = "#020617",
        color: str = "#E5E7EB",
        border: Optional[str] = "#334155",
        font: str = "14px ui-monospace, SFMono-Regular, Consolas, monospace",
        padding: int = 8,
        line_height: int = 18,
        scrollback: int = 1000,
    ) -> TerminalRegion:
        self.define_terminal_region(
            region_id,
            x=x,
            y=y,
            width=width,
            height=height,
            title=title,
            background=background,
            color=color,
            border=border,
            font=font,
            padding=padding,
            line_height=line_height,
            scrollback=scrollback,
        )
        return TerminalRegion(self, region_id)

    def define_terminal_region(
        self,
        region_id: str = "default",
        *,
        x: float = 0,
        y: float = 0,
        width: Optional[float] = None,
        height: Optional[float] = None,
        title: str = "",
        background: str = "#020617",
        color: str = "#E5E7EB",
        border: Optional[str] = "#334155",
        font: str = "14px ui-monospace, SFMono-Regular, Consolas, monospace",
        padding: int = 8,
        line_height: int = 18,
        scrollback: int = 1000,
    ) -> dict[str, Any]:
        return self.command({
            "type": "terminal_define",
            "id": str(region_id),
            "x": round(x),
            "y": round(y),
            "width": round(width if width is not None else self.width - x),
            "height": round(height if height is not None else self.height - y),
            "title": title,
            "background": background,
            "color": color,
            "border": False if border is None else border,
            "font": font,
            "padding": padding,
            "lineHeight": line_height,
            "scrollback": scrollback,
        })

    def write_terminal(
        self,
        region_id: str,
        text: Any,
        *,
        color: Optional[str] = None,
        newline: bool = False,
    ) -> dict[str, Any]:
        command = {
            "type": "terminal_write",
            "id": str(region_id),
            "text": str(text),
            "newline": bool(newline),
        }
        if color is not None:
            command["color"] = color
        return self.command(command)

    def clear_terminal(self, region_id: str = "default") -> dict[str, Any]:
        return self.command({
            "type": "terminal_clear",
            "id": str(region_id),
        })

    def fill_screen(self, color: str = "white") -> dict[str, Any]:
        return self.clear(color)

    def line(self, x1: float, y1: float, x2: float, y2: float, color: str = "black", width: float = 1) -> dict[str, Any]:
        return self.command({
            "type": "line",
            "x1": round(x1),
            "y1": round(y1),
            "x2": round(x2),
            "y2": round(y2),
            "color": color,
            "width": width,
        })

    def hline(self, x: float, y: float, length: float, color: str = "black", width: float = 1) -> dict[str, Any]:
        return self.line(x, y, x + length - 1, y, color, width)

    def vline(self, x: float, y: float, length: float, color: str = "black", width: float = 1) -> dict[str, Any]:
        return self.line(x, y, x, y + length - 1, color, width)

    def rect(self, x: float, y: float, width: float, height: float, color: str = "black", line_width: float = 1) -> dict[str, Any]:
        return self.command({
            "type": "rect",
            "x": round(x),
            "y": round(y),
            "width": round(width),
            "height": round(height),
            "color": color,
            "lineWidth": line_width,
            "stroke": True,
        })

    def fill_rect(self, x: float, y: float, width: float, height: float, color: str) -> dict[str, Any]:
        return self.command({
            "type": "rect",
            "x": round(x),
            "y": round(y),
            "width": round(width),
            "height": round(height),
            "fill": color,
            "stroke": False,
        })

    def circle(self, x: float, y: float, radius: float, color: str = "black", line_width: float = 1) -> dict[str, Any]:
        return self.command({
            "type": "circle",
            "x": round(x),
            "y": round(y),
            "radius": round(radius),
            "color": color,
            "lineWidth": line_width,
            "stroke": True,
        })

    def fill_circle(self, x: float, y: float, radius: float, color: str) -> dict[str, Any]:
        return self.command({
            "type": "circle",
            "x": round(x),
            "y": round(y),
            "radius": round(radius),
            "fill": color,
            "stroke": False,
        })

    def arc(
        self,
        x: float,
        y: float,
        radius: float,
        start_angle: float,
        end_angle: float,
        color: str = "black",
        width: float = 1,
        *,
        line_cap: str = "round",
    ) -> dict[str, Any]:
        return self.command({
            "type": "arc",
            "x": round(x),
            "y": round(y),
            "radius": round(radius),
            "startAngle": start_angle,
            "endAngle": end_angle,
            "color": color,
            "width": width,
            "lineCap": line_cap,
        })

    def text(
        self,
        x: float,
        y: float,
        text: str,
        *,
        color: str = "black",
        size: int = 1,
        font: Optional[str] = None,
    ) -> dict[str, Any]:
        px = max(8, round(12 * size))
        return self.command({
            "type": "text",
            "x": round(x),
            "y": round(y + px),
            "text": str(text),
            "color": color,
            "font": font or f"{px}px sans-serif",
        })

    def path(
        self,
        points: Iterable[tuple[float, float]],
        color: str = "black",
        width: float = 1,
        *,
        line_cap: str = "butt",
        line_join: str = "round",
        dash: Optional[Iterable[float]] = None,
    ) -> dict[str, Any]:
        return self.command({
            "type": "path",
            "points": [{"x": round(x), "y": round(y)} for x, y in points],
            "color": color,
            "width": width,
            "lineCap": line_cap,
            "lineJoin": line_join,
            "dash": [float(value) for value in (dash or [])],
        })
